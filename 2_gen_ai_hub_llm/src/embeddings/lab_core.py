"""Core workflow for 02_embeddings.ipynb."""

from __future__ import annotations

import os
from typing import Callable, Sequence

import numpy as np

from lab_common.config import Settings
from src.business_embedding.lab_core import embed_texts


DEFAULT_EMBED_MODEL = "amazon--titan-embed-image"


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
    selected_model = (
        model.strip()
        if model and model.strip()
        else os.getenv("EMBED_MODEL", DEFAULT_EMBED_MODEL)
    )
    vectors = np.asarray(embedder(cleaned, settings, selected_model), dtype=np.float64)
    if vectors.ndim != 2 or vectors.shape[1] == 0:
        raise ValueError("embedding 결과는 비어 있지 않은 2D vector여야 합니다.")
    if len(vectors) != len(cleaned):
        raise ValueError("embedding 결과 수가 입력 텍스트 수와 다릅니다.")
    comparisons = [
        {
            "left": cleaned[left],
            "right": cleaned[right],
            "cosine_similarity": cosine_similarity(vectors[left], vectors[right]),
        }
        for left in range(len(cleaned))
        for right in range(left + 1, len(cleaned))
    ]
    return {
        "model": selected_model,
        "dimensions": int(vectors.shape[1]),
        "texts": cleaned,
        "comparisons": comparisons,
    }


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
