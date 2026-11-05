"""Cohere Rerank-backed Chat/Work routing."""
from __future__ import annotations

import requests
from ..lesson_support.ai_core import api_headers, list_running_deployments
from ..lesson_support.config import Settings
from ..lesson_support.models import Candidate, RankedCandidate, RouteDecision

from ..prompts import routing_candidate

FAST_ROUTE_CANDIDATES = [
    Candidate(candidate_id, routing_candidate(candidate_id)["label"], routing_candidate(candidate_id)["description"])
    for candidate_id in ("chat", "work")
]


def _cohere_documents(candidates: list[Candidate]) -> list[str]:
    return [f"{candidate.label}\n{candidate.description}" for candidate in candidates]


def _rank_from_response(candidates: list[Candidate], response_data: dict) -> list[RankedCandidate]:
    scores = {int(item["index"]): float(item["relevance_score"]) for item in response_data["results"]}
    return sorted(
        (RankedCandidate(candidate, scores.get(index, 0.0)) for index, candidate in enumerate(candidates)),
        key=lambda item: (-item.score, item.candidate.id),
    )


def _cohere_deployment(settings: Settings) -> tuple[str, str]:
    model_name = settings.rerank_model.strip()
    for deployment in list_running_deployments(settings):
        deployed_model = (
            deployment.get("details", {})
            .get("resources", {})
            .get("backendDetails", {})
            .get("model", {})
            .get("name", "")
        )
        deployment_url = str(deployment.get("deploymentUrl", "")).rstrip("/")
        if deployed_model == model_name and deployment_url:
            return deployment_url, model_name
    raise RuntimeError(
        f"현재 AI Core Resource Group에 RERANK_MODEL={model_name!r}인 RUNNING deployment가 없습니다."
    )


def cohere_rank(query: str, candidates: list[Candidate], settings: Settings) -> tuple[list[RankedCandidate], str]:
    """Rank route candidates through Cohere's native rerank contract."""
    payload = {
        "model": settings.rerank_model,
        "query": query,
        "documents": _cohere_documents(candidates),
        "top_n": len(candidates),
    }
    if settings.rerank_endpoint:
        headers = {"Content-Type": "application/json"}
        if settings.rerank_api_key:
            headers["Authorization"] = f"Bearer {settings.rerank_api_key}"
        response = requests.post(settings.rerank_endpoint, headers=headers, json=payload, timeout=30)
        engine = "cohere_rerank_endpoint"
    else:
        deployment_url, model_name = _cohere_deployment(settings)
        payload["model"] = model_name
        response = requests.post(
            f"{deployment_url}/rerank",
            headers=api_headers(settings),
            json=payload,
            timeout=30,
        )
        engine = "btp_cohere_rerank"
    response.raise_for_status()
    return _rank_from_response(candidates, response.json()), engine


def decide(
    query: str,
    candidates: list[Candidate],
    settings: Settings,
    min_margin: float = 0.0,
) -> RouteDecision:
    """Choose through Cohere Rerank only; never synthesize a local ranking."""
    try:
        ranked, engine = cohere_rank(query, candidates, settings)
    except (requests.RequestException, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise RuntimeError(
            "Cohere Rerank 호출에 실패했습니다. RERANK_MODEL, deployment 상태, Resource Group 권한을 확인하세요."
        ) from error
    margin = ranked[0].score - ranked[1].score if len(ranked) > 1 else ranked[0].score
    return RouteDecision(
        selected=ranked[0].candidate.id,
        scores={item.candidate.id: item.score for item in ranked},
        margin=margin,
        engine=engine,
        fallback=margin < min_margin,
    )
