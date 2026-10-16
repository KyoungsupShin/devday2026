"""Reranker-backed, review-safe decision recommendations.

This module ranks *decision policies* against a case narrative.  It is not an
authorisation engine: callers must keep the human-review signal in the workflow
and perform any actual state change separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from lab_common.ai_core import api_headers, chat_text, list_running_deployments
from lab_common.config import Settings
from lab_common.models import Candidate, RankedCandidate

# Candidates stay intentionally short and are the only documents sent to the
# reranker.  Policy interpretation is produced by the configured LLM.
APPLICATION_DECISIONS = [
    Candidate(
        "approve",
        "정상 고객",
        "정상적인 주문 빈도와 구매 흐름을 유지하며, 인증·결제·주문 이력에 특이사항이 없는 고객 행동 유형.",
    ),
    Candidate(
        "manual-review",
        "모니터링 필요",
        "짧은 간격의 반복 주문, 일시적 실패나 중복 가능성, 평소와 다른 구매량 또는 확인이 필요한 인증·한도 상태가 관찰되는 고객 행동 유형.",
    ),
    Candidate(
        "decline",
        "고위험 고객",
        "자동화·우회 정황, 지속적인 실패, 다계정·다중 결제수단 사용, 한도 회피 또는 비정상적 집중·분할 구매 정황이 관찰되는 고객 행동 유형.",
    ),
]

DEFAULT_MIN_MARGIN = 0.12
DEFAULT_MIN_SCORE = 0.45

def _load_default_policy_document() -> str:
    policy_path = Path(__file__).resolve().parents[1] / "docs" / "customer_order_risk_policy.md"
    return policy_path.read_text(encoding="utf-8").strip()


DEFAULT_ORDER_POLICY_DOCUMENT = _load_default_policy_document()


@dataclass(frozen=True)
class DecisionResult:
    """A recommendation plus enough evidence to decide whether to trust it."""

    recommendation: str
    scores: dict[str, float]
    margin: float
    engine: str
    reason: str
    requires_human_review: bool



def _llm_policy_summary(case_text: str, policy_document: str, settings: Settings) -> str:
    """Ask the configured LLM to ground a case in the user-provided policy."""
    prompt = f"""다음 주문 정책 문서와 고객 행동을 바탕으로 reranker용 정책 해석 문장을
한국어 1~2문장으로 작성하세요. 고객 등급, 추천, 최종 결론은 쓰지 마세요.

입력에 명시된 사실만 사용하세요. 주문 빈도·실패·인증·한도·계정·결제수단처럼 입력에 없는
항목은 언급하지 마세요. 정책상 예외 또는 위험 패턴이 명시되지 않은 단일 구매라면
"일상적인 단일 상품 구매"로 요약하세요. 반대로 정책상 예외 또는 위험 패턴이 명시됐다면
그 패턴만 간결히 요약하세요.

정책 문서:
{policy_document}

고객 행동:
{case_text}
"""
    return chat_text(
        settings,
        [
            {"role": "system", "content": "제공된 문서와 사실만 사용하는 정책 분석가입니다."},
            {"role": "user", "content": prompt},
        ],
    ).strip()


def _remote_rank(case_text: str, candidates: list[Candidate], settings: Settings) -> list[RankedCandidate]:
    headers = {"Content-Type": "application/json"}
    if settings.rerank_api_key:
        headers["Authorization"] = f"Bearer {settings.rerank_api_key}"
    response = requests.post(
        settings.rerank_endpoint,
        headers=headers,
        json={
            "model": settings.rerank_model,
            "query": case_text,
            "documents": [candidate.description for candidate in candidates],
            "top_n": len(candidates),
        },
        timeout=15,
    )
    response.raise_for_status()
    response_data = response.json()
    scores = {int(item["index"]): float(item["relevance_score"]) for item in response_data["results"]}
    return sorted(
        (RankedCandidate(candidate, scores.get(index, 0.0)) for index, candidate in enumerate(candidates)),
        key=lambda item: (-item.score, item.candidate.id),
    )


def _btp_cohere_reranker_deployment(settings: Settings) -> tuple[str, str]:
    """Find the configured RUNNING Cohere reranker deployment in AI Core."""
    configured_model = settings.rerank_model.strip()
    for deployment in list_running_deployments(settings):
        model = (
            deployment.get("details", {})
            .get("resources", {})
            .get("backendDetails", {})
            .get("model", {})
        )
        model_name = str(model.get("name", ""))
        deployment_url = str(deployment.get("deploymentUrl", "")).rstrip("/")
        if model_name == configured_model and deployment_url:
            return deployment_url, model_name
    raise RuntimeError(
        f"현재 AI Core Resource Group에 RERANK_MODEL={configured_model!r}인 RUNNING deployment가 없습니다."
    )


def _btp_cohere_rank(case_text: str, candidates: list[Candidate], settings: Settings) -> list[RankedCandidate]:
    """Call the AI Core Cohere reranker deployment using its native /rerank contract."""
    deployment_url, model_name = _btp_cohere_reranker_deployment(settings)
    response = requests.post(
        f"{deployment_url}/rerank",
        headers=api_headers(settings),
        json={
            "model": model_name,
            "query": case_text,
            "documents": [candidate.description for candidate in candidates],
            "top_n": len(candidates),
        },
        timeout=30,
    )
    response.raise_for_status()
    response_data = response.json()
    scores = {int(item["index"]): float(item["relevance_score"]) for item in response_data["results"]}
    return sorted(
        (RankedCandidate(candidate, scores.get(index, 0.0)) for index, candidate in enumerate(candidates)),
        key=lambda item: (-item.score, item.candidate.id),
    )


def recommend(
    case_text: str,
    candidates: list[Candidate] | None = None,
    settings: Settings | None = None,
    policy_document: str | None = None,
    min_margin: float = DEFAULT_MIN_MARGIN,
    min_score: float = DEFAULT_MIN_SCORE,
) -> DecisionResult:
    """Rank policy candidates and force uncertain outcomes to human review."""
    cleaned_case = case_text.strip()
    if not cleaned_case:
        raise ValueError("고객 행동을 입력하세요.")
    if min_margin < 0 or min_score < 0:
        raise ValueError("min_margin과 min_score는 0 이상이어야 합니다.")
    candidates = APPLICATION_DECISIONS if candidates is None else candidates
    if not candidates:
        raise ValueError("At least one decision candidate is required.")
    policy = (policy_document or DEFAULT_ORDER_POLICY_DOCUMENT).strip()
    if not policy:
        raise ValueError("정책 document를 입력하세요.")
    if not settings:
        raise RuntimeError("AI Core LLM 및 Cohere reranker 설정이 필요합니다.")

    try:
        llm_summary = _llm_policy_summary(cleaned_case, policy, settings)
        if not llm_summary:
            raise RuntimeError("LLM이 정책 근거 요약을 반환하지 않았습니다.")
        if settings.rerank_endpoint:
            ranked = _remote_rank(llm_summary, candidates, settings)
            engine = "llm_policy_litellm_rerank"
        else:
            ranked = _btp_cohere_rank(llm_summary, candidates, settings)
            engine = "llm_policy_btp_cohere_rerank"
    except (requests.RequestException, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise RuntimeError("AI Core LLM 또는 Cohere reranker 호출에 실패했습니다. 설정과 deployment 상태를 확인하세요.") from error

    if not ranked:
        raise RuntimeError("Cohere reranker가 후보 점수를 반환하지 않았습니다.")
    winner = ranked[0]
    runner_up_score = ranked[1].score if len(ranked) > 1 else 0.0
    margin = winner.score - runner_up_score
    scores = {item.candidate.id: item.score for item in ranked}
    review_reasons: list[str] = []
    if winner.candidate.id == "manual-review":
        review_reasons.append("가장 관련도 높은 후보가 manual-review입니다.")
    if winner.score < min_score:
        review_reasons.append(f"최고 점수 {winner.score:.3f}가 최소 점수 {min_score:.3f}보다 낮습니다.")
    if len(ranked) > 1 and margin < min_margin:
        review_reasons.append(f"1·2위 점수 차이 {margin:.3f}가 최소 margin {min_margin:.3f}보다 작습니다.")
    requires_human_review = bool(review_reasons)
    recommendation = "manual-review" if requires_human_review else winner.candidate.id
    reason = (
        "LLM이 정책 문서와 행동 사실을 요약한 뒤 Cohere가 후보 관련도를 순위화했습니다. "
        + (" ".join(review_reasons) if review_reasons else "점수와 margin 기준을 충족해 추천을 생성했습니다.")
    )
    return DecisionResult(
        recommendation,
        scores,
        margin,
        engine,
        reason,
        requires_human_review,
    )


def run_decision_recommendation(
    case_text: str,
    settings: Settings,
    policy_document: str | None = None,
    candidates: list[Candidate] | None = None,
    min_margin: float = DEFAULT_MIN_MARGIN,
    min_score: float = DEFAULT_MIN_SCORE,
    recommendation_runner: Callable[..., DecisionResult] = recommend,
) -> dict[str, object]:
    """Return one read-only, JSON-friendly policy recommendation for a UI or CLI."""
    cleaned_case = case_text.strip()
    if not cleaned_case:
        raise ValueError("고객 행동을 입력하세요.")
    selected_candidates = APPLICATION_DECISIONS if candidates is None else candidates
    outcome = recommendation_runner(
        cleaned_case,
        candidates=selected_candidates,
        settings=settings,
        policy_document=policy_document,
        min_margin=min_margin,
        min_score=min_score,
    )
    labels = {candidate.id: candidate.label for candidate in selected_candidates}
    ranked_candidates = sorted(outcome.scores.items(), key=lambda item: item[1], reverse=True)
    return {
        "case": cleaned_case,
        "recommendation": outcome.recommendation,
        "recommendation_label": labels.get(outcome.recommendation, outcome.recommendation),
        "requires_human_review": outcome.requires_human_review,
        "margin": outcome.margin,
        "engine": outcome.engine,
        "reason": outcome.reason,
        "ranked_candidates": [
            {"rank": index + 1, "id": candidate_id, "label": labels.get(candidate_id, candidate_id), "score": score}
            for index, (candidate_id, score) in enumerate(ranked_candidates)
        ],
        "action": "추천만 생성했습니다. 승인·반려 상태는 변경하지 않았습니다.",
    }
