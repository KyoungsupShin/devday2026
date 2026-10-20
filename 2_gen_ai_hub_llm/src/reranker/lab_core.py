"""Core workflow for 03_reranker_decision_model.ipynb."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable

import requests

from lab_common.ai_core import api_headers, list_running_deployments
from lab_common.config import Settings
from lab_common.llm import chat_text
from lab_common.models import Candidate, RankedCandidate

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
DEFAULT_ORDER_POLICY_DOCUMENT = (
    (Path(__file__).resolve().parents[2] / "docs" / "customer_order_risk_policy.md")
    .read_text(encoding="utf-8")
    .strip()
)


@dataclass(frozen=True)
class DecisionResult:
    recommendation: str
    scores: dict[str, float]
    margin: float
    engine: str
    reason: str
    requires_human_review: bool
    policy_summary: str = ""
    policy_id: str = ""


def _summary(case_text: str, policy: str, settings: Settings) -> str:
    prompt = (
        "정책 문서와 고객 행동을 바탕으로 reranker용 정책 해석을 한국어 1~2문장으로 작성하세요. 고객 등급·추천·최종 결론은 쓰지 마세요. 입력 사실만 사용하세요.\n\n정책 문서:\n"
        + policy
        + "\n\n고객 행동:\n"
        + case_text
    )
    return chat_text(
        settings,
        [
            {
                "role": "system",
                "content": "제공된 문서와 사실만 사용하는 정책 분석가입니다.",
            },
            {"role": "user", "content": prompt},
        ],
    ).strip()


def _rank_response(
    response: requests.Response, candidates: list[Candidate]
) -> list[RankedCandidate]:
    response.raise_for_status()
    scores = {
        int(item["index"]): float(item["relevance_score"])
        for item in response.json()["results"]
    }
    return sorted(
        (
            RankedCandidate(candidate, scores.get(index, 0.0))
            for index, candidate in enumerate(candidates)
        ),
        key=lambda item: (-item.score, item.candidate.id),
    )


def _deployment(settings: Settings) -> tuple[str, str]:
    for deployment in list_running_deployments(settings):
        model = (
            deployment.get("details", {})
            .get("resources", {})
            .get("backendDetails", {})
            .get("model", {})
        )
        name, url = (
            str(model.get("name", "")),
            str(deployment.get("deploymentUrl", "")).rstrip("/"),
        )
        if name == settings.rerank_model and url:
            return url, name
    raise RuntimeError(
        "현재 AI Core Resource Group에 RUNNING Cohere reranker deployment가 없습니다."
    )


def _rank(
    query: str, candidates: list[Candidate], settings: Settings
) -> tuple[list[RankedCandidate], str]:
    body = {
        "model": settings.rerank_model,
        "query": query,
        "documents": [item.description for item in candidates],
        "top_n": len(candidates),
    }
    if settings.rerank_endpoint:
        headers = {"Content-Type": "application/json"}
        if settings.rerank_api_key:
            headers["Authorization"] = f"Bearer {settings.rerank_api_key}"
        return _rank_response(
            requests.post(
                settings.rerank_endpoint, headers=headers, json=body, timeout=15
            ),
            candidates,
        ), "llm_policy_litellm_rerank"
    url, model = _deployment(settings)
    body["model"] = model
    return _rank_response(
        requests.post(
            f"{url}/rerank", headers=api_headers(settings), json=body, timeout=30
        ),
        candidates,
    ), "llm_policy_btp_cohere_rerank"


def recommend(
    case_text: str,
    candidates: list[Candidate] | None = None,
    settings: Settings | None = None,
    policy_document: str | None = None,
    min_margin: float = DEFAULT_MIN_MARGIN,
    min_score: float = DEFAULT_MIN_SCORE,
) -> DecisionResult:
    cleaned = case_text.strip()
    selected = APPLICATION_DECISIONS if candidates is None else candidates
    if not cleaned:
        raise ValueError("고객 행동을 입력하세요.")
    if min_margin < 0 or min_score < 0:
        raise ValueError("min_margin과 min_score는 0 이상이어야 합니다.")
    if not selected:
        raise ValueError("At least one decision candidate is required.")
    if not settings:
        raise RuntimeError("AI Core LLM 및 Cohere reranker 설정이 필요합니다.")
    policy = (policy_document or DEFAULT_ORDER_POLICY_DOCUMENT).strip()
    if not policy:
        raise ValueError("정책 document를 입력하세요.")
    try:
        summary = _summary(cleaned, policy, settings)
        if not summary:
            raise RuntimeError("LLM이 정책 근거 요약을 반환하지 않았습니다.")
        ranked, engine = _rank(summary, selected, settings)
    except (
        requests.RequestException,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as error:
        raise RuntimeError(
            "AI Core LLM 또는 Cohere reranker 호출에 실패했습니다. 설정과 deployment 상태를 확인하세요."
        ) from error
    if not ranked:
        raise RuntimeError("Cohere reranker가 후보 점수를 반환하지 않았습니다.")
    winner = ranked[0]
    margin = winner.score - (ranked[1].score if len(ranked) > 1 else 0.0)
    reasons = []
    if winner.candidate.id == "manual-review":
        reasons.append("가장 관련도 높은 후보가 manual-review입니다.")
    if winner.score < min_score:
        reasons.append(
            f"최고 점수 {winner.score:.3f}가 최소 점수 {min_score:.3f}보다 낮습니다."
        )
    if len(ranked) > 1 and margin < min_margin:
        reasons.append(
            f"1·2위 점수 차이 {margin:.3f}가 최소 margin {min_margin:.3f}보다 작습니다."
        )
    review = bool(reasons)
    return DecisionResult(
        recommendation="manual-review" if review else winner.candidate.id,
        scores={item.candidate.id: item.score for item in ranked},
        margin=margin,
        engine=engine,
        reason=(
            "LLM이 정책 문서와 행동 사실을 요약한 뒤 Cohere가 후보 관련도를 순위화했습니다. "
            + (
                " ".join(reasons)
                if reasons
                else "점수와 margin 기준을 충족해 추천을 생성했습니다."
            )
        ),
        requires_human_review=review,
        policy_summary=summary,
        policy_id=f"sha256:{sha256(policy.encode('utf-8')).hexdigest()[:12]}",
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
    cleaned = case_text.strip()
    if not cleaned:
        raise ValueError("고객 행동을 입력하세요.")
    selected = APPLICATION_DECISIONS if candidates is None else candidates
    outcome = recommendation_runner(
        cleaned,
        candidates=selected,
        settings=settings,
        policy_document=policy_document,
        min_margin=min_margin,
        min_score=min_score,
    )
    labels = {candidate.id: candidate.label for candidate in selected}
    ranked = sorted(outcome.scores.items(), key=lambda item: item[1], reverse=True)
    return {
        "case": cleaned,
        "recommendation": outcome.recommendation,
        "recommendation_label": labels.get(
            outcome.recommendation, outcome.recommendation
        ),
        "requires_human_review": outcome.requires_human_review,
        "margin": outcome.margin,
        "engine": outcome.engine,
        "reason": outcome.reason,
        "policy_summary": outcome.policy_summary,
        "policy_id": outcome.policy_id,
        "decision_thresholds": {
            "min_score": min_score,
            "min_margin": min_margin,
        },
        "ranked_candidates": [
            {
                "rank": index + 1,
                "id": key,
                "label": labels.get(key, key),
                "score": value,
            }
            for index, (key, value) in enumerate(ranked)
        ],
        "action": "추천만 생성했습니다. 승인·반려 상태는 변경하지 않았습니다.",
    }
