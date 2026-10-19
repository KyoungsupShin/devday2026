"""Core workflow for 02_embeddings.ipynb."""

from __future__ import annotations

import os
from typing import Callable, Sequence

import numpy as np

from lab_common.ai_core import apply_ai_core_environment
from lab_common.config import Settings


def embed_texts(
    texts: Sequence[str], settings: Settings, model: str | None = None
) -> np.ndarray:
    if not texts:
        raise ValueError("texts must not be empty.")
    apply_ai_core_environment(settings)
    from gen_ai_hub.proxy.native.openai import embeddings

    response = embeddings.create(
        input=list(texts),
        model_name=model or os.getenv("EMBED_MODEL", "text-embedding-3-small"),
    )
    return np.asarray(
        [
            item.embedding
            for item in sorted(
                response.data, key=lambda item: getattr(item, "index", 0)
            )
        ],
        dtype=np.float64,
    )


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
        else os.getenv("EMBED_MODEL", "text-embedding-3-small")
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
