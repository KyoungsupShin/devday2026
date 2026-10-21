"""Core workflow for 02_embeddings.ipynb."""

from __future__ import annotations

import os
import warnings
from math import ceil, sqrt
from typing import Callable, Sequence

import numpy as np

from lab_common.config import Settings
from src.business_embedding.lab_core import embed_texts


DEFAULT_EMBED_MODEL = "amazon--titan-embed-image"


def _selected_model(model: str | None) -> str:
    return (
        model.strip()
        if model and model.strip()
        else os.getenv("EMBED_MODEL", DEFAULT_EMBED_MODEL)
    )


def _as_embedding_matrix(vectors: object, expected_rows: int | None = None) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("embedding 결과는 비어 있지 않은 2D vector여야 합니다.")
    if expected_rows is not None and matrix.shape[0] != expected_rows:
        raise ValueError("embedding 결과 수가 입력 텍스트 수와 다릅니다.")
    if not np.isfinite(matrix).all():
        raise ValueError("embedding 결과에는 유한한 숫자만 포함되어야 합니다.")
    return matrix


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms > 0)


def _cluster_count(item_count: int) -> int:
    return 1 if item_count == 1 else min(5, max(2, ceil(sqrt(item_count))))


def _kmeans_assignments(matrix: np.ndarray, n_clusters: int) -> np.ndarray:
    """Cluster normalized vectors with deterministic farthest-first seeds."""
    normalized = _l2_normalize(matrix)
    selected, closest = [0], np.sum((normalized - normalized[0]) ** 2, axis=1)
    for _ in range(1, n_clusters):
        index = int(np.argmax(closest))
        selected.append(index)
        closest = np.minimum(
            closest, np.sum((normalized - normalized[index]) ** 2, axis=1)
        )

    assignments = np.zeros(len(normalized), dtype=int)
    centroids = normalized[selected].copy()
    for _ in range(100):
        updated = np.argmin(
            np.sum((normalized[:, None, :] - centroids[None, :, :]) ** 2, axis=2),
            axis=1,
        )
        next_centroids = centroids.copy()
        for cluster_id in range(n_clusters):
            members = normalized[updated == cluster_id]
            if len(members):
                next_centroids[cluster_id] = members.mean(axis=0)
        if np.array_equal(updated, assignments) and np.allclose(
            next_centroids, centroids
        ):
            return updated
        assignments, centroids = updated, next_centroids
    return assignments


def _two_point_coordinates(matrix: np.ndarray) -> np.ndarray:
    """Return a deterministic 2D layout until UMAP has enough points."""
    if len(matrix) == 1:
        return np.zeros((1, 2), dtype=np.float64)
    centered = _l2_normalize(matrix)
    centered = centered - centered.mean(axis=0, keepdims=True)
    _, _, right_vectors = np.linalg.svd(centered, full_matrices=False)
    components = right_vectors[:2].copy()
    coordinates = centered @ components.T
    for column, component in enumerate(components):
        pivot = int(np.argmax(np.abs(component)))
        if component[pivot] < 0:
            coordinates[:, column] *= -1
    return np.pad(coordinates, ((0, 0), (0, max(0, 2 - coordinates.shape[1]))))[:, :2]


def _umap_coordinates(matrix: np.ndarray) -> np.ndarray:
    """Project normalized embeddings with a repeatable cosine-metric UMAP layout."""
    if len(matrix) < 3:
        return _two_point_coordinates(matrix)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ImportWarning)
            from umap import UMAP
    except ImportError as error:
        raise RuntimeError(
            "UMAP이 없습니다. python3 -m pip install -r requirements.txt 를 실행하세요."
        ) from error

    coordinates = np.asarray(
        UMAP(
            n_components=2,
            n_neighbors=min(15, len(matrix) - 1),
            min_dist=0.15,
            metric="cosine",
            init="random",
            random_state=42,
            n_jobs=1,
        ).fit_transform(_l2_normalize(matrix)),
        dtype=np.float64,
    )
    if coordinates.shape != (len(matrix), 2) or not np.isfinite(coordinates).all():
        raise ValueError("UMAP 결과는 유한한 2D 좌표여야 합니다.")
    return coordinates


def _validated_cluster_entries(state: object) -> tuple[str | None, int | None, list[dict[str, object]]]:
    if state is None:
        return None, None, []
    if not isinstance(state, dict):
        raise ValueError("누적 embedding 상태 형식이 올바르지 않습니다. Reset 후 다시 시도하세요.")
    entries = state.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("누적 embedding 항목 형식이 올바르지 않습니다. Reset 후 다시 시도하세요.")
    if not entries:
        return None, None, []

    state_model, dimensions = state.get("model"), state.get("dimensions")
    if (
        not isinstance(state_model, str)
        or not state_model.strip()
        or not isinstance(dimensions, int)
        or isinstance(dimensions, bool)
    ):
        raise ValueError("누적 embedding 메타데이터가 올바르지 않습니다. Reset 후 다시 시도하세요.")
    if dimensions < 1:
        raise ValueError("누적 embedding 차원이 올바르지 않습니다. Reset 후 다시 시도하세요.")

    cleaned_entries: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("text"), str):
            raise ValueError("누적 embedding 항목 형식이 올바르지 않습니다. Reset 후 다시 시도하세요.")
        text = entry["text"].strip()
        try:
            vector = np.asarray(entry.get("vector"), dtype=np.float64)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "누적 embedding 항목이 올바르지 않습니다. Reset 후 다시 시도하세요."
            ) from error
        if not text or vector.ndim != 1 or len(vector) != dimensions or not np.isfinite(vector).all():
            raise ValueError("누적 embedding 항목이 올바르지 않습니다. Reset 후 다시 시도하세요.")
        cleaned_entries.append({"text": text, "vector": vector.tolist()})
    return state_model, dimensions, cleaned_entries


def _cluster_outcome(entries: list[dict[str, object]], model: str) -> dict[str, object]:
    matrix = _as_embedding_matrix([entry["vector"] for entry in entries])
    cluster_count = _cluster_count(len(entries))
    assignments = (
        np.zeros(len(entries), dtype=int)
        if cluster_count == 1
        else _kmeans_assignments(matrix, cluster_count)
    )
    coordinates = _umap_coordinates(matrix)
    return {
        "model": model,
        "dimensions": int(matrix.shape[1]),
        "cluster_count": cluster_count,
        "entries": [
            {
                "index": index + 1,
                "text": entry["text"],
                "vector": entry["vector"],
                "cluster": int(assignments[index]),
                "x": float(coordinates[index, 0]),
                "y": float(coordinates[index, 1]),
            }
            for index, entry in enumerate(entries)
        ],
    }


def _comparison_outcome(
    texts: Sequence[str], vectors: np.ndarray, model: str
) -> dict[str, object]:
    return {
        "model": model,
        "dimensions": int(vectors.shape[1]),
        "texts": list(texts),
        "comparisons": [
            {
                "left": texts[left],
                "right": texts[right],
                "cosine_similarity": cosine_similarity(vectors[left], vectors[right]),
            }
            for left in range(len(texts))
            for right in range(left + 1, len(texts))
        ],
    }


def append_embedding_cluster_point(
    text: str,
    state: object,
    settings: Settings,
    model: str | None = None,
    embedder: Callable[[Sequence[str], Settings, str | None], np.ndarray] = embed_texts,
) -> dict[str, object]:
    """Embed one new text and recalculate a session-local 2D cluster view.

    ``state`` is JSON-friendly output from the preceding call. Existing vectors are
    validated and reused, so each call sends only ``text`` to the embedding service.
    """
    cleaned_text = text.strip() if isinstance(text, str) else ""
    if not cleaned_text:
        raise ValueError("cluster에 추가할 키워드를 입력하세요.")

    selected_model = _selected_model(model)
    previous_model, dimensions, entries = _validated_cluster_entries(state)
    if previous_model is not None and previous_model != selected_model:
        raise ValueError("embedding 모델이 변경되었습니다. Reset 후 새 모델로 다시 시작하세요.")

    new_vector = _as_embedding_matrix(
        embedder([cleaned_text], settings, selected_model), expected_rows=1
    )[0]
    if dimensions is not None and len(new_vector) != dimensions:
        raise ValueError("embedding 차원이 변경되었습니다. Reset 후 다시 시작하세요.")

    entries.append({"text": cleaned_text, "vector": new_vector.tolist()})
    return _cluster_outcome(entries, selected_model)


def compare_and_append_embedding_clusters(
    text_a: str,
    text_b: str,
    state: object,
    settings: Settings,
    model: str | None = None,
    embedder: Callable[[Sequence[str], Settings, str | None], np.ndarray] = embed_texts,
) -> dict[str, object]:
    """Compare two texts and append both to the session cluster in one request."""
    cleaned = [text_a.strip() if isinstance(text_a, str) else "", text_b.strip() if isinstance(text_b, str) else ""]
    if any(not text for text in cleaned):
        raise ValueError("비교할 두 텍스트를 모두 입력하세요.")

    selected_model = _selected_model(model)
    previous_model, dimensions, entries = _validated_cluster_entries(state)
    if previous_model is not None and previous_model != selected_model:
        raise ValueError("embedding 모델이 변경되었습니다. Reset 후 새 모델로 다시 시작하세요.")

    vectors = _as_embedding_matrix(
        embedder(cleaned, settings, selected_model), expected_rows=len(cleaned)
    )
    if dimensions is not None and vectors.shape[1] != dimensions:
        raise ValueError("embedding 차원이 변경되었습니다. Reset 후 다시 시작하세요.")
    unique_entries: list[dict[str, object]] = []
    seen_texts: set[str] = set()
    for entry in entries:
        text = str(entry["text"])
        if text not in seen_texts:
            unique_entries.append(entry)
            seen_texts.add(text)

    added_texts: list[str] = []
    for text, vector in zip(cleaned, vectors, strict=True):
        if text not in seen_texts:
            unique_entries.append({"text": text, "vector": vector.tolist()})
            seen_texts.add(text)
            added_texts.append(text)
    return {
        "comparison": _comparison_outcome(cleaned, vectors, selected_model),
        "cluster": _cluster_outcome(unique_entries, selected_model),
        "added_texts": added_texts,
    }


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    left_vector, right_vector = (
        np.asarray(left, dtype=np.float64),
        np.asarray(right, dtype=np.float64),
    )
    if (
        left_vector.ndim != 1
        or right_vector.ndim != 1
        or left_vector.shape != right_vector.shape
    ):
        raise ValueError("두 embedding은 같은 차원의 1D vector여야 합니다.")
    denominator = float(np.linalg.norm(left_vector) * np.linalg.norm(right_vector))
    if denominator == 0:
        raise ValueError("zero vector의 cosine similarity는 계산할 수 없습니다.")
    return float(np.dot(left_vector, right_vector) / denominator)


def compare_embeddings(
    texts: Sequence[str],
    settings: Settings,
    model: str | None = None,
    embedder: Callable[[Sequence[str], Settings, str | None], np.ndarray] = embed_texts,
) -> dict[str, object]:
    cleaned = [text.strip() if isinstance(text, str) else "" for text in texts]
    if len(cleaned) < 2:
        raise ValueError("비교할 텍스트를 두 개 이상 입력하세요.")
    if any(not text for text in cleaned):
        raise ValueError("비교할 텍스트에는 빈 값을 넣을 수 없습니다.")
    selected_model = _selected_model(model)
    vectors = _as_embedding_matrix(
        embedder(cleaned, settings, selected_model), expected_rows=len(cleaned)
    )
    return _comparison_outcome(cleaned, vectors, selected_model)


def retrieve_similar_texts(
    query: str,
    documents: Sequence[str],
    settings: Settings,
    *,
    top_k: int = 3,
    min_similarity: float | None = None,
    model: str | None = None,
    embedder: Callable[[Sequence[str], Settings, str | None], np.ndarray] = embed_texts,
) -> dict[str, object]:
    """Rank documents by cosine similarity to one query in a single batch call."""
    cleaned_query = query.strip() if isinstance(query, str) else ""
    cleaned_documents = [
        document.strip() if isinstance(document, str) else ""
        for document in documents
    ]
    if not cleaned_query:
        raise ValueError("검색 질문을 입력하세요.")
    if not cleaned_documents:
        raise ValueError("검색할 문서를 한 개 이상 입력하세요.")
    if any(not document for document in cleaned_documents):
        raise ValueError("검색할 문서에는 빈 값을 넣을 수 없습니다.")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise ValueError("top_k는 1 이상의 정수여야 합니다.")
    if min_similarity is not None and not -1 <= min_similarity <= 1:
        raise ValueError("min_similarity는 -1과 1 사이여야 합니다.")

    selected_model = (
        model.strip()
        if model and model.strip()
        else os.getenv("EMBED_MODEL", DEFAULT_EMBED_MODEL)
    )
    vectors = np.asarray(
        embedder([cleaned_query, *cleaned_documents], settings, selected_model),
        dtype=np.float64,
    )
    if vectors.ndim != 2 or vectors.shape[1] == 0:
        raise ValueError("embedding 결과는 비어 있지 않은 2D vector여야 합니다.")
    if len(vectors) != len(cleaned_documents) + 1:
        raise ValueError("embedding 결과 수가 입력 텍스트 수와 다릅니다.")

    scored = [
        {
            "document_index": index,
            "document": document,
            "cosine_similarity": cosine_similarity(vectors[0], vectors[index + 1]),
        }
        for index, document in enumerate(cleaned_documents)
    ]
    ranked = sorted(
        scored,
        key=lambda item: (-float(item["cosine_similarity"]), int(item["document_index"])),
    )
    if min_similarity is not None:
        ranked = [
            item
            for item in ranked
            if float(item["cosine_similarity"]) >= min_similarity
        ]
    results = [
        {**item, "rank": rank}
        for rank, item in enumerate(ranked[:top_k], start=1)
    ]
    return {
        "model": selected_model,
        "dimensions": int(vectors.shape[1]),
        "query": cleaned_query,
        "candidate_count": len(cleaned_documents),
        "min_similarity": min_similarity,
        "results": results,
    }
