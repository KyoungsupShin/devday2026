"""Routing for the fixed workflow, optionally ranked by Cohere Rerank."""
from __future__ import annotations

import requests

from lab_common.ai_core import api_headers, list_running_deployments
from lab_common.config import Settings
from lab_common.models import Candidate, RankedCandidate, RouteDecision

FAST_ROUTE_CANDIDATES = [
    Candidate(
        "chat",
        "Conversation",
        "사용자의 의도가 인사, 일반적인 질의응답, 개념 설명, 자유 대화 또는 즉시 제공 가능한 조언에 머무르는 요청입니다. 외부 정보 확인, 전문 역할 분담, 단계적 분석, 계산·검토, 결과물 생산이 필요하지 않으며 하나의 대화형 응답만으로 사용자의 목적을 충족할 수 있을 때 선택합니다.",
    ),
    Candidate(
        "work",
        "Work",
        "사용자의 목표를 달성하려면 정보를 구조화하고 분석·계산·검토하거나 전문 역할의 판단을 적용해야 하는 업무 요청입니다. 신제품 기획, 레시피와 제조공정 설계, 원가·수익성 분석, 품질·안전 검토, 마케팅 전략, 보고서 작성처럼 근거와 가정을 명시한 실행 결과가 필요한 경우를 포함합니다.",
    ),
]
def _cohere_documents(candidates: list[Candidate]) -> list[str]:
    """Keep candidate identity in each document while preserving its semantic description."""
    return [f"{candidate.label}\n{candidate.description}" for candidate in candidates]


def _rank_from_response(candidates: list[Candidate], response_data: dict) -> list[RankedCandidate]:
    scores = {int(item["index"]): float(item["relevance_score"]) for item in response_data["results"]}
    return sorted(
        (RankedCandidate(candidate, scores.get(index, 0.0)) for index, candidate in enumerate(candidates)),
        key=lambda item: (-item.score, item.candidate.id),
    )


def _cohere_deployment(settings: Settings) -> tuple[str, str]:
    """Find the configured Cohere Rerank deployment in the current AI Core group."""
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
    """Rank route candidates through Cohere's native rerank contract.

    ``RERANK_ENDPOINT`` is useful for a Cohere-compatible proxy.  Without it,
    the configured AI Core Cohere deployment is discovered and called directly.
    """
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
