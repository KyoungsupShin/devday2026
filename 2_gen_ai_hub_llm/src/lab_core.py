"""Reusable core workflows for the LLM and embedding notebooks."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from lab_common.ai_core import chat_text
from lab_common.config import Settings

from .business_embeddings import BusinessEmbeddingAdapter, ClusterResult, embed_texts, kmeans_cluster, l2_normalize


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "fixtures" / "business_embedding_cases.json"


def compare_prompts(
    question: str,
    settings: Settings,
    chat_caller: Callable[[Settings, list[dict[str, str]], str | None], str] = chat_text,
) -> dict[str, str]:
    """Compare baseline and constrained prompts through one SDK boundary."""
    cleaned = question.strip()
    if not cleaned:
        raise ValueError("질문을 입력하세요.")
    baseline = chat_caller(settings, [{"role": "user", "content": cleaned}], None)
    constrained = chat_caller(
        settings,
        [
            {"role": "system", "content": "너는 교육 보조자다. 한국어로, 정확히 한 문장으로만 답한다."},
            {"role": "user", "content": cleaned},
        ],
        None,
    )
    return {"question": cleaned, "baseline": baseline, "constrained": constrained}


def run_chat(
    message: str,
    settings: Settings,
    history: Sequence[dict[str, str]] = (),
    system_prompt: str = "",
    model: str | None = None,
    chat_caller: Callable[[Settings, list[dict[str, str]], str | None], str] = chat_text,
) -> dict[str, str]:
    """Send one chat turn while keeping message assembly and SDK access in the core."""
    cleaned = message.strip()
    if not cleaned:
        raise ValueError("질문을 입력하세요.")
    messages: list[dict[str, str]] = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    for item in history:
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            raise ValueError("대화 history에는 내용이 있는 user 또는 assistant 메시지만 넣을 수 있습니다.")
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": cleaned})
    selected_model = model.strip() if model and model.strip() else settings.llm_model
    return {
        "message": cleaned,
        "model": selected_model,
        "reply": chat_caller(settings, messages, selected_model),
    }


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Calculate cosine similarity and make invalid/zero vectors explicit."""
    left_vector = np.asarray(left, dtype=np.float64)
    right_vector = np.asarray(right, dtype=np.float64)
    if left_vector.ndim != 1 or right_vector.ndim != 1 or left_vector.shape != right_vector.shape:
        raise ValueError("두 embedding은 같은 차원의 1D vector여야 합니다.")
    denominator = float(np.linalg.norm(left_vector) * np.linalg.norm(right_vector))
    if denominator == 0:
        raise ValueError("zero vector의 cosine similarity는 계산할 수 없습니다.")
    return float(np.dot(left_vector, right_vector) / denominator)


def compare_embeddings(
    texts: Sequence[str], settings: Settings, model: str | None = None,
    embedder: Callable[[Sequence[str], Settings, str | None], np.ndarray] = embed_texts,
) -> dict[str, object]:
    """Embed texts once and return JSON-friendly pairwise cosine comparisons.

    The SDK boundary is injectable so the same workflow can be tested locally
    without sending text to AI Core.  Pair results are a list, rather than a
    dictionary keyed by text, so duplicate input text remains unambiguous.
    """
    cleaned_texts = [text.strip() if isinstance(text, str) else "" for text in texts]
    if len(cleaned_texts) < 2:
        raise ValueError("비교할 텍스트를 두 개 이상 입력하세요.")
    if any(not text for text in cleaned_texts):
        raise ValueError("비교할 텍스트에는 빈 값을 넣을 수 없습니다.")

    selected_model = model.strip() if model and model.strip() else os.getenv("EMBED_MODEL", "text-embedding-3-small")
    vectors = np.asarray(embedder(cleaned_texts, settings, selected_model), dtype=np.float64)
    if vectors.ndim != 2 or vectors.shape[1] == 0:
        raise ValueError("embedding 결과는 비어 있지 않은 2D vector여야 합니다.")
    if len(vectors) != len(cleaned_texts):
        raise ValueError("embedding 결과 수가 입력 텍스트 수와 다릅니다.")
    comparisons = [
        {
            "left": cleaned_texts[left],
            "right": cleaned_texts[right],
            "cosine_similarity": cosine_similarity(vectors[left], vectors[right]),
        }
        for left in range(len(cleaned_texts)) for right in range(left + 1, len(cleaned_texts))
    ]
    return {
        "model": selected_model,
        "dimensions": int(vectors.shape[1]),
        "texts": cleaned_texts,
        "comparisons": comparisons,
    }


def load_business_cases(path: Path | str = CASES_PATH) -> list[dict[str, str]]:
    """Load the labelled, synthetic business ticket fixture."""
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("business embedding fixture는 비어 있지 않은 list여야 합니다.")
    required = {"id", "text", "label"}
    if any(not required.issubset(case) for case in cases):
        raise ValueError("각 business embedding case에는 id, text, label이 필요합니다.")
    return cases


def holdout_indices_by_label(labels: Sequence[str]) -> np.ndarray:
    """Reserve the final observation of every label as a reproducible holdout."""
    values = np.asarray(labels, dtype=str)
    if not len(values):
        raise ValueError("label이 비어 있습니다.")
    return np.asarray([np.where(values == label)[0][-1] for label in sorted(set(values.tolist()))], dtype=int)


def run_business_embedding_workflow(
    cases: Sequence[dict[str, str]], vectors: Sequence[Sequence[float]] | np.ndarray, n_clusters: int = 4,
) -> dict[str, object]:
    """Cluster cases, train a frozen-vector adapter, and evaluate held-out labels."""
    matrix = l2_normalize(vectors)
    if len(cases) != len(matrix):
        raise ValueError("case와 vector의 수가 같아야 합니다.")
    labels = np.asarray([case["label"] for case in cases], dtype=str)
    holdout_indices = holdout_indices_by_label(labels)
    train_mask = np.ones(len(cases), dtype=bool)
    train_mask[holdout_indices] = False
    if not train_mask.any():
        raise ValueError("label마다 학습 사례가 하나 이상 필요합니다.")
    cluster: ClusterResult = kmeans_cluster(matrix, n_clusters=n_clusters)
    adapter = BusinessEmbeddingAdapter().fit(matrix[train_mask], labels[train_mask])
    predicted = adapter.predict(matrix[holdout_indices])
    actual = labels[holdout_indices].tolist()
    return {
        "cluster_assignments": cluster.assignments.tolist(),
        "cluster_inertia": cluster.inertia,
        "holdout_ids": [cases[index]["id"] for index in holdout_indices],
        "holdout_actual": actual,
        "holdout_predicted": predicted,
        "holdout_accuracy": float(np.mean(np.asarray(actual) == np.asarray(predicted))),
        "adapter": adapter,
    }


def recommend_business_queue(
    text: str, adapter: BusinessEmbeddingAdapter, settings: Settings, model: str | None = None,
    embedder: Callable[[Sequence[str], Settings, str | None], np.ndarray] = embed_texts,
) -> dict[str, object]:
    """Embed one new ticket and return its label plus auditable centroid scores."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("업무 문의를 입력하세요.")
    vector = embedder([cleaned], settings, model)
    scores = adapter.similarity(vector, adapter.centroids)[0]
    ranked = sorted(zip(adapter.labels, scores.tolist()), key=lambda item: item[1], reverse=True)
    return {"ticket": cleaned, "recommended_queue": adapter.predict(vector)[0], "label_similarity": dict(ranked)}


def run_business_embedding_lab(
    ticket: str,
    cases: Sequence[dict[str, str]],
    settings: Settings,
    n_clusters: int = 4,
    model: str | None = None,
    embedder: Callable[[Sequence[str], Settings, str | None], np.ndarray] = embed_texts,
) -> dict[str, object]:
    """Run the complete business-embedding lesson through one SDK boundary.

    The returned object intentionally contains only JSON-friendly teaching and
    audit artifacts.  The fitted adapter stays inside the core workflow rather
    than leaking into a CLI, notebook, or UI as mutable state.
    """
    cleaned_ticket = ticket.strip()
    if not cleaned_ticket:
        raise ValueError("업무 문의를 입력하세요.")
    if not cases:
        raise ValueError("business embedding 사례가 비어 있습니다.")
    required = {"id", "text", "label"}
    if any(not required.issubset(case) for case in cases):
        raise ValueError("각 business embedding case에는 id, text, label이 필요합니다.")
    normalized_cases = [
        {key: str(case[key]).strip() for key in required}
        for case in cases
    ]
    if any(not all(case.values()) for case in normalized_cases):
        raise ValueError("business embedding case의 id, text, label은 비어 있을 수 없습니다.")

    selected_model = model.strip() if model and model.strip() else os.getenv("EMBED_MODEL", "text-embedding-3-small")
    texts = [case["text"] for case in normalized_cases] + [cleaned_ticket]
    vectors = np.asarray(embedder(texts, settings, selected_model), dtype=np.float64)
    if vectors.ndim != 2 or vectors.shape[1] == 0:
        raise ValueError("embedding 결과는 비어 있지 않은 2D vector여야 합니다.")
    if len(vectors) != len(texts):
        raise ValueError("embedding 결과 수가 business case와 새 문의 수의 합과 다릅니다.")

    workflow = run_business_embedding_workflow(normalized_cases, vectors[:-1], n_clusters=n_clusters)
    adapter: BusinessEmbeddingAdapter = workflow["adapter"]  # Kept private to this composed workflow.
    ticket_vector = vectors[-1:]
    scores = adapter.similarity(ticket_vector, adapter.centroids)[0]
    ranked_scores = sorted(zip(adapter.labels, scores.tolist()), key=lambda item: item[1], reverse=True)
    holdout = [
        {"id": case_id, "actual": actual, "predicted": predicted}
        for case_id, actual, predicted in zip(
            workflow["holdout_ids"], workflow["holdout_actual"], workflow["holdout_predicted"], strict=True,
        )
    ]
    return {
        "model": selected_model,
        "embedding_dimensions": int(vectors.shape[1]),
        "case_count": len(normalized_cases),
        "clusters": [
            {**case, "cluster": assignment}
            for case, assignment in zip(normalized_cases, workflow["cluster_assignments"], strict=True)
        ],
        "cluster_inertia": workflow["cluster_inertia"],
        "holdout": {
            "cases": holdout,
            "accuracy": workflow["holdout_accuracy"],
        },
        "recommendation": {
            "ticket": cleaned_ticket,
            "recommended_queue": adapter.predict(ticket_vector)[0],
            "label_similarity": dict(ranked_scores),
        },
        "action": "추천과 평가만 생성했습니다. 외부 업무 큐나 상태는 변경하지 않았습니다.",
    }
