"""Shared workflow for the embedding and reranker comparison notebook."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Callable

import numpy as np

from src.business_embedding.lab_core import embed_texts
from src.embeddings.lab_core import cosine_similarity
from src.reranker.lab_core import MULTI_PROTOTYPE_DECISIONS, run_decision_recommendation
from src.reranker.lab_core import DEFAULT_MIN_MARGIN, DEFAULT_MIN_SCORE
from src.reranker.lesson_support.config import Settings
from src.reranker.lesson_support.models import Candidate


def _embedding_ranking(
    case_text: str,
    settings: Settings,
    candidates: list[Candidate],
    embedder: Callable[..., np.ndarray],
) -> tuple[list[dict[str, Any]], list[Candidate]]:
    vectors = np.asarray(
        embedder([case_text, *[candidate.description for candidate in candidates]], settings, None),
        dtype=np.float64,
    )
    if vectors.ndim != 2 or len(vectors) != len(candidates) + 1:
        raise ValueError("embedding 결과가 정책 후보 수와 일치하지 않습니다.")
    prototype_rows = sorted(
        [
            {
                "candidate": candidate,
                "prototype_score": cosine_similarity(vectors[0], vectors[index + 1]),
            }
            for index, candidate in enumerate(candidates)
        ],
        key=lambda item: float(item["prototype_score"]),
        reverse=True,
    )
    by_id: dict[str, dict[str, Any]] = {}
    for row in prototype_rows:
        candidate = row["candidate"]
        current = by_id.get(candidate.id)
        if current is None or row["prototype_score"] > current["score"]:
            by_id[candidate.id] = {
                "id": candidate.id,
                "label": candidate.label,
                "score": float(row["prototype_score"]),
            }
    ranked = sorted(by_id.values(), key=lambda item: float(item["score"]), reverse=True)
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return ranked, [row["candidate"] for row in prototype_rows]


def run_embedding_reranker_comparison(
    case_text: str,
    settings: Settings,
    *,
    top_k: int = 4,
    min_margin: float = DEFAULT_MIN_MARGIN,
    min_score: float = DEFAULT_MIN_SCORE,
    candidates: list[Candidate] | None = None,
    embedder: Callable[..., np.ndarray] = embed_texts,
) -> dict[str, Any]:
    """Use embedding retrieval then reranking against the same policy prototypes."""
    cleaned = case_text.strip()
    selected = candidates or MULTI_PROTOTYPE_DECISIONS
    if not cleaned:
        raise ValueError("고객 행동을 입력하세요.")
    if not 1 <= top_k <= len(selected):
        raise ValueError(f"top_k는 1에서 {len(selected)} 사이여야 합니다.")

    started = perf_counter()
    embedding_ranked, prototype_ranked = _embedding_ranking(cleaned, settings, selected, embedder)
    embedding_ms = (perf_counter() - started) * 1000
    retrieved = prototype_ranked[:top_k]

    started = perf_counter()
    reranker = run_decision_recommendation(
        cleaned, settings, candidates=retrieved, min_margin=min_margin, min_score=min_score
    )
    reranker_ms = (perf_counter() - started) * 1000
    reranker_ranks = {row["id"]: row for row in reranker["ranked_candidates"]}
    comparison_rows = [
        {
            "decision": row["id"],
            "label": row["label"],
            "embedding_rank": row["rank"],
            "embedding_score": row["score"],
            "reranker_rank": reranker_ranks.get(row["id"], {}).get("rank"),
            "reranker_score": reranker_ranks.get(row["id"], {}).get("score"),
        }
        for row in embedding_ranked
    ]
    return {
        "case": cleaned,
        "embedding": {
            "recommended": embedding_ranked[0]["id"],
            "ranked_candidates": embedding_ranked,
            "latency_ms": embedding_ms,
            "retrieved_prototype_count": len(retrieved),
        },
        "reranker": {**reranker, "latency_ms": reranker_ms},
        "comparison_rows": comparison_rows,
        "same_top_recommendation": embedding_ranked[0]["id"] == reranker["recommendation"],
    }
