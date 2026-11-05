"""Core workflow for 03_embedding_advanced.ipynb."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np

from .lesson_support.ai_core import apply_ai_core_environment
from .lesson_support.config import Settings


@dataclass(frozen=True)
class ClusterResult:
    assignments: np.ndarray
    centroids: np.ndarray
    inertia: float


def _as_matrix(vectors: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("vectors must be a non-empty 2D matrix.")
    if not np.isfinite(matrix).all():
        raise ValueError("vectors must contain only finite values.")
    return matrix


def l2_normalize(vectors: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    matrix = _as_matrix(vectors)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms > 0)


def embed_texts(
    texts: Sequence[str], settings: Settings, model: str | None = None
) -> np.ndarray:
    if not texts:
        raise ValueError("texts must not be empty.")
    if any(not text.strip() for text in texts):
        raise ValueError("texts must not contain blank values.")
    selected_model = _selected_embedding_model(model)
    if selected_model.startswith("text-embedding-"):
        return _embed_openai_texts(texts, settings, selected_model)
    return _embed_titan_inputs(
        [{"inputText": text} for text in texts], settings, selected_model
    )


def _selected_embedding_model(model: str | None) -> str:
    return (
        model.strip()
        if model and model.strip()
        else os.getenv("EMBED_MODEL", "amazon--titan-embed-image")
    )


def _embed_openai_texts(
    texts: Sequence[str], settings: Settings, model: str
) -> np.ndarray:
    """Embed text-only OpenAI models through the Gen AI Hub OpenAI proxy."""
    apply_ai_core_environment(settings)
    try:
        from gen_ai_hub.proxy.native.openai import OpenAI
    except ImportError as error:
        raise RuntimeError(
            "OpenAI embedding 모델에는 sap-ai-sdk-gen이 필요합니다. requirements.txt를 다시 설치하세요."
        ) from error

    response = OpenAI().embeddings.create(model=model, input=list(texts))
    data = sorted(response.data, key=lambda item: int(getattr(item, "index", 0)))
    vectors = [getattr(item, "embedding", None) for item in data]
    if any(not isinstance(vector, list) for vector in vectors):
        raise ValueError("OpenAI embedding 응답에 embedding vector가 없습니다.")
    return _as_matrix(vectors)


def _embed_titan_inputs(
    payloads: Sequence[dict[str, str]], settings: Settings, model: str | None = None
) -> np.ndarray:
    """Call Amazon Titan Multimodal Embeddings once for every text input."""
    if not payloads:
        raise ValueError("embedding inputs must not be empty.")
    apply_ai_core_environment(settings)
    try:
        from gen_ai_hub.proxy.native.amazon import Session
    except ImportError as error:
        raise RuntimeError(
            "Amazon Titan embedding에는 aiobotocore가 필요합니다. requirements.txt를 다시 설치하세요."
        ) from error

    client = Session().client(model_name=_selected_embedding_model(model))
    vectors = []
    for payload in payloads:
        response = client.invoke_model(
            body=json.dumps(payload),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        embedding = result.get("embedding")
        if not isinstance(embedding, list):
            raise ValueError("Titan embedding 응답에 embedding vector가 없습니다.")
        vectors.append(embedding)
    return _as_matrix(vectors)


def kmeans_cluster(
    vectors: Sequence[Sequence[float]] | np.ndarray,
    n_clusters: int,
    max_iterations: int = 100,
) -> ClusterResult:
    matrix = l2_normalize(vectors)
    if not 1 <= n_clusters <= len(matrix) or max_iterations < 1:
        raise ValueError("n_clusters 또는 max_iterations가 유효하지 않습니다.")
    selected, closest = [0], np.sum((matrix - matrix[0]) ** 2, axis=1)
    for _ in range(1, n_clusters):
        index = int(np.argmax(closest))
        selected.append(index)
        closest = np.minimum(closest, np.sum((matrix - matrix[index]) ** 2, axis=1))
    assignments, centroids = np.zeros(len(matrix), dtype=int), matrix[selected].copy()
    for _ in range(max_iterations):
        updated = np.argmin(
            np.sum((matrix[:, None, :] - centroids[None, :, :]) ** 2, axis=2), axis=1
        )
        next_centroids = centroids.copy()
        for cluster_id in range(n_clusters):
            members = matrix[updated == cluster_id]
            if len(members):
                next_centroids[cluster_id] = members.mean(axis=0)
        if np.array_equal(updated, assignments) and np.allclose(
            next_centroids, centroids
        ):
            assignments, centroids = updated, next_centroids
            break
        assignments, centroids = updated, next_centroids
    return ClusterResult(
        assignments, centroids, float(np.sum((matrix - centroids[assignments]) ** 2))
    )


class BusinessEmbeddingAdapter:
    def __init__(self, regularization: float = 1e-6, max_weight: float = 20.0):
        (
            self.regularization,
            self.max_weight,
            self.weights,
            self.labels,
            self.centroids,
        ) = regularization, max_weight, None, (), None

    def fit(
        self, vectors: Sequence[Sequence[float]] | np.ndarray, labels: Iterable[str]
    ) -> "BusinessEmbeddingAdapter":
        matrix, label_array = l2_normalize(vectors), np.asarray(list(labels), dtype=str)
        if len(label_array) != len(matrix):
            raise ValueError("labels must have one entry per vector.")
        classes = tuple(sorted(set(label_array.tolist())))
        if len(classes) < 2:
            raise ValueError("At least two distinct business labels are required.")
        mean, between, within, class_means = (
            matrix.mean(axis=0),
            np.zeros(matrix.shape[1]),
            np.zeros(matrix.shape[1]),
            [],
        )
        for label in classes:
            members = matrix[label_array == label]
            class_mean = members.mean(axis=0)
            class_means.append(class_mean)
            between += len(members) * (class_mean - mean) ** 2
            within += ((members - class_mean) ** 2).sum(axis=0)
        weights = (between / len(matrix)) / (within / len(matrix) + self.regularization)
        weights /= max(float(weights.mean()), self.regularization)
        self.weights, self.labels = (
            np.clip(weights, 1 / self.max_weight, self.max_weight),
            classes,
        )
        self.centroids = l2_normalize(np.asarray(class_means) * np.sqrt(self.weights))
        return self

    def transform(self, vectors):
        if self.weights is None:
            raise RuntimeError("Call fit before transform.")
        matrix = _as_matrix(vectors)
        if matrix.shape[1] != len(self.weights):
            raise ValueError("vector dimension does not match fitted adapter.")
        return l2_normalize(matrix * np.sqrt(self.weights))

    def predict(self, vectors):
        if self.centroids is None:
            raise RuntimeError("Call fit before predict.")
        return [
            self.labels[index]
            for index in np.argmax(self.transform(vectors) @ self.centroids.T, axis=1)
        ]

    def similarity(self, left, right):
        return self.transform(left) @ self.transform(right).T


CASES_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "business_embedding_cases.json"
)


def load_business_cases(path: Path | str = CASES_PATH) -> list[dict[str, str]]:
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"id", "text", "label"}
    if (
        not isinstance(cases, list)
        or not cases
        or any(not required.issubset(case) for case in cases)
    ):
        raise ValueError("각 business embedding case에는 id, text, label이 필요합니다.")
    return cases


def holdout_indices_by_label(labels: Sequence[str]) -> np.ndarray:
    values = np.asarray(labels, dtype=str)
    if not len(values):
        raise ValueError("label이 비어 있습니다.")
    return np.asarray(
        [np.where(values == label)[0][-1] for label in sorted(set(values.tolist()))],
        dtype=int,
    )


def run_business_embedding_workflow(
    cases: Sequence[dict[str, str]],
    vectors: Sequence[Sequence[float]] | np.ndarray,
    n_clusters: int = 4,
) -> dict[str, object]:
    matrix = l2_normalize(vectors)
    if len(cases) != len(matrix):
        raise ValueError("case와 vector의 수가 같아야 합니다.")
    labels = np.asarray([case["label"] for case in cases], dtype=str)
    holdout_indices = holdout_indices_by_label(labels)
    train_mask = np.ones(len(cases), dtype=bool)
    train_mask[holdout_indices] = False
    if not train_mask.any():
        raise ValueError("label마다 학습 사례가 하나 이상 필요합니다.")
    cluster = kmeans_cluster(matrix, n_clusters=n_clusters)
    adapter = BusinessEmbeddingAdapter().fit(matrix[train_mask], labels[train_mask])
    actual, predicted = (
        labels[holdout_indices].tolist(),
        adapter.predict(matrix[holdout_indices]),
    )
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
    text: str,
    adapter: BusinessEmbeddingAdapter,
    settings: Settings,
    model: str | None = None,
    embedder: Callable[[Sequence[str], Settings, str | None], np.ndarray] = embed_texts,
) -> dict[str, object]:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("업무 문의를 입력하세요.")
    vector = embedder([cleaned], settings, model)
    scores = adapter.similarity(vector, adapter.centroids)[0]
    return {
        "ticket": cleaned,
        "recommended_queue": adapter.predict(vector)[0],
        "label_similarity": dict(
            sorted(
                zip(adapter.labels, scores.tolist()),
                key=lambda item: item[1],
                reverse=True,
            )
        ),
    }


def run_business_embedding_lab(
    ticket: str,
    cases: Sequence[dict[str, str]],
    settings: Settings,
    n_clusters: int = 4,
    model: str | None = None,
    embedder: Callable[[Sequence[str], Settings, str | None], np.ndarray] = embed_texts,
) -> dict[str, object]:
    cleaned_ticket = ticket.strip()
    required = {"id", "text", "label"}
    if not cleaned_ticket:
        raise ValueError("업무 문의를 입력하세요.")
    if not cases:
        raise ValueError("business embedding 사례가 비어 있습니다.")
    if any(not required.issubset(case) for case in cases):
        raise ValueError("각 business embedding case에는 id, text, label이 필요합니다.")
    normalized = [{key: str(case[key]).strip() for key in required} for case in cases]
    if any(not all(case.values()) for case in normalized):
        raise ValueError(
            "business embedding case의 id, text, label은 비어 있을 수 없습니다."
        )
    selected_model = (
        model.strip()
        if model and model.strip()
        else _selected_embedding_model(None)
    )
    vectors = np.asarray(
        embedder(
            [case["text"] for case in normalized] + [cleaned_ticket],
            settings,
            selected_model,
        ),
        dtype=np.float64,
    )
    if (
        vectors.ndim != 2
        or vectors.shape[1] == 0
        or len(vectors) != len(normalized) + 1
    ):
        raise ValueError("embedding 결과의 형태 또는 수가 입력과 일치하지 않습니다.")
    workflow = run_business_embedding_workflow(normalized, vectors[:-1], n_clusters)
    adapter, ticket_vector = workflow["adapter"], vectors[-1:]
    scores = adapter.similarity(ticket_vector, adapter.centroids)[0]
    holdout = [
        {"id": case_id, "actual": actual, "predicted": predicted}
        for case_id, actual, predicted in zip(
            workflow["holdout_ids"],
            workflow["holdout_actual"],
            workflow["holdout_predicted"],
            strict=True,
        )
    ]
    return {
        "model": selected_model,
        "embedding_dimensions": int(vectors.shape[1]),
        "case_count": len(normalized),
        "clusters": [
            {**case, "cluster": assignment}
            for case, assignment in zip(
                normalized, workflow["cluster_assignments"], strict=True
            )
        ],
        "cluster_inertia": workflow["cluster_inertia"],
        "holdout": {"cases": holdout, "accuracy": workflow["holdout_accuracy"]},
        "recommendation": {
            "ticket": cleaned_ticket,
            "recommended_queue": adapter.predict(ticket_vector)[0],
            "label_similarity": dict(
                sorted(
                    zip(adapter.labels, scores.tolist()),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ),
        },
        "action": "추천과 평가만 생성했습니다. 외부 업무 큐나 상태는 변경하지 않았습니다.",
    }
