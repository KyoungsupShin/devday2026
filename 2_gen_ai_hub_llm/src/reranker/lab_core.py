"""Cohere reranker workflow for the decision-model notebook.

Reranker relevance is recorded as a ranking signal, not a probability.  Query
facts and decision prototypes are deliberately kept separate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Callable, Literal

import requests

from lab_common.ai_core import api_headers, list_running_deployments
from lab_common.config import Settings
from lab_common.llm import chat_text
from lab_common.models import Candidate, RankedCandidate

Strategy = Literal["v1", "v2", "v3"]
DEFAULT_STRATEGY: Strategy = "v3"
DECISION_CLASS = {"approve": "NORMAL", "manual-review": "CAUTION", "decline": "HIGH_RISK"}

# V1: original broad documents.  Kept unchanged as the benchmark baseline.
APPLICATION_DECISIONS = [
    Candidate("approve", "정상 고객", "정상적인 주문 빈도와 구매 흐름을 유지하며, 인증·결제·주문 이력에 특이사항이 없는 고객 행동 유형."),
    Candidate("manual-review", "모니터링 필요", "짧은 간격의 반복 주문, 일시적 실패나 중복 가능성, 평소와 다른 구매량 또는 확인이 필요한 인증·한도 상태가 관찰되는 고객 행동 유형."),
    Candidate("decline", "고위험 고객", "자동화·우회 정황, 지속적인 실패, 다계정·다중 결제수단 사용, 한도 회피 또는 비정상적 집중·분할 구매 정황이 관찰되는 고객 행동 유형."),
]

# V2 candidates are YAML strings. The query retains the customer's original
# statement and appends only explicitly observed facts; it never adds a class.
STRUCTURED_DECISIONS = [
    Candidate("approve", "정상 고객", """candidate_id: approve
class: NORMAL
selection_conditions:
  authenticated: true
  min_order_interval_seconds: at_least_20
  orders_per_minute: at_most_3
  duplicate_order_count: 0
  failed_order_count: 0
  limit_exceeded: false
exclusion_conditions:
  - orders_per_minute: at_least_4
  - order_interval_and_frequency: inconsistent
classification_note: NORMAL은 모든 selection_conditions를 충족할 때만 선택한다. 인증 성공, 중복·실패·한도 초과 없음만으로는 정상 후보가 되지 않으며, 분당 4회 이상의 주문 또는 주문 간격·빈도 불일치는 NORMAL에서 제외한다.
account_payment_delivery: consistent_with_known_customer_flow
scenario_examples:
  - 기존 고객이 평소 사용하던 기기·배송지·결제수단으로 정상 간격의 반복 구매
  - 수취인만 다른 1회 선물 주문이지만 주문 빈도와 결제·배송 흐름은 정상
  - 인증된 신규 고객이 한도 안의 수량을 한 번 주문하고 실패·중복·자동화 정황이 없는 경우
semantic_description: 인증된 고객이 20초 이상 간격으로 분당 3회 이하 주문하고, 중복·실패·한도 초과 없이 계정, 결제수단, 배송지와 수취인 흐름이 일관된 정상 구매. 기존 고객의 동일 기기·배송지·결제수단 반복 구매, 단일 선물 주문, 인증된 신규 고객의 정상 1회 주문도 정상 흐름에 해당한다."""),
    Candidate("manual-review", "모니터링 필요", """candidate_id: manual-review
class: CAUTION
selection_conditions:
  - order_velocity_or_concentration: at_least_4_per_minute_or_unusually_concentrated_purchase
  - duplicate_order: possible_or_unresolved
  - payment_instrument_irregularity: one_to_two_changes_or_one_to_two_failures
  - account_device_network_linkage: shared_device_network_or_delivery_across_accounts_without_confirmed_abuse
  - delivery_recipient_contact_anomaly: repeated_change_or_unexplained_reuse_without_confirmed_abuse
  - identity_or_behavior_inconsistency: authentication_order_interval_or_frequency_data_do_not_match
classification_note: 단일 또는 미확정 신호는 추가 확인 대상이다. 인증 성공과 중복·실패·한도 초과 없음이 함께 있어도 분당 4회 이상의 빈번한 주문은 NORMAL이 아니다. 분당 7회 이상처럼 매우 높은 빈도라도 자동화·다계정 악용·한도 회피가 명시되지 않으면 CAUTION으로 분류한다.
scenario_examples:
  - 분당 4회 이상 주문 또는 짧은 시간의 집중 구매
  - 인증과 결제는 성공했지만 1분에 5회처럼 정상 범위를 넘는 주문 시도
  - 인증됐고 중복·실패·한도 초과는 없지만 1분에 매우 많은 주문을 시도해 추가 확인이 필요한 경우
  - 서로 다른 계정이 같은 기기·네트워크·배송지를 사용하지만 악용 정황은 미확정
  - 두 계정이 같은 기기·네트워크·배송지를 사용하지만 결제 실패와 한도 회피는 미확정
  - 결제수단 변경 1~2회 또는 인증·결제 실패 1~2회
  - 배송지는 유지한 채 수취인·연락처를 짧은 시간에 반복 변경하거나 동일 정보 재사용의 사유가 불명확
  - 주문 간격과 주문 빈도 또는 인증 정보가 서로 맞지 않는 기록
semantic_description: 한 가지 이상 확인이 필요한 주문 이상 신호가 있는 모니터링 대상. 빈번하거나 집중된 주문, 중복 가능성, 가벼운 결제 이상, 계정·기기·네트워크·배송지 연계, 배송지는 유지한 채 수취인·연락처를 반복 변경하는 주문, 인증 또는 행동 데이터 불일치를 추가 검토한다."""),
    Candidate("decline", "고위험 고객", """candidate_id: decline
class: HIGH_RISK
selection_conditions:
  - automated_extreme_velocity: automation_or_script_pattern_with_repeated_high_frequency_orders
  - multi_account_linkage: repeated_shared_device_network_delivery_or_contact_across_accounts
  - repeated_payment_failure_or_churn: at_least_3_failures_or_repeated_method_changes_with_failures
  - limit_evasion_or_structuring: split_or_concentrated_purchase_to_avoid_product_or_customer_limits
  - recipient_or_delivery_network_abuse: repeated_shared_recipient_contact_or_delivery_with_multi_account_or_payment_irregularity
  - authentication_evasion_or_compound_inconsistency: repeated_authentication_anomaly_with_other_risk_signals
classification_note: 독립적인 복합·반복 정황이 확인된 경우 HIGH_RISK다. 단일 빈도 증가나 한 번의 정보 변경만으로는 HIGH_RISK를 선택하지 않는다.
scenario_examples:
  - 자동화 의심 주문과 초고빈도·반복 요청이 함께 발생
  - 다계정이 동일 기기·네트워크·배송지·연락처를 공유하면서 결제 이상 또는 실패가 반복
  - 결제수단 반복 변경과 실패 누적이 함께 발생
  - 한도 회피 목적의 분할 구매 또는 고가 상품 집중 구매가 반복
  - 동일 수취인·배송지 네트워크를 여러 계정과 결제수단이 반복 사용
semantic_description: 자동화, 다계정 연계, 반복 결제 실패·수단 교체, 한도 회피성 분할 구매, 수취인·배송지 네트워크 악용, 인증 우회 정황이 복합 또는 반복된 고위험 주문 패턴."""),
]

# V3: equal, focused prototypes let the reranker match a single decisive signal
# without one broad document collecting unrelated normal-language overlap.
# Scores are still selected only by the reranker and aggregated by max per class.
MULTI_PROTOTYPE_DECISIONS = [
    Candidate("approve", "정상 고객", "candidate_id: approve\nprototype: stable_low_frequency\nauthenticated: true\norders_per_minute: at_most_3\nduplicate_order_count: 0\nfailed_order_count: 0\nlimit_exceeded: false\nmatch_note: 분당 0~3회의 낮은 빈도인 경우에만 정상 후보를 선택한다."),
    Candidate("approve", "정상 고객", "candidate_id: approve\nprototype: ordinary_repeat_purchase\nauthenticated: true\nmin_order_interval_seconds: at_least_20\norders_per_minute: at_most_3\naccount_payment_delivery: consistent\nmatch_note: 주문 빈도가 분당 3회 이하이고 정상 흐름이 확인된 경우다."),
    Candidate("manual-review", "모니터링 필요", "candidate_id: manual-review\nprototype: high_frequency_without_confirmed_abuse\norders_per_minute: at_least_4\nautomation_detected: unknown_or_false\nlimit_avoidance_detected: unknown_or_false\naccount_abuse_detected: unknown_or_false\nmatch_note: 인증 성공, 중복·실패·한도 초과 없음이 함께 있어도 분당 4회 이상이면 정상 고객이 아닌 모니터링 대상이다. 매우 높은 주문 빈도만 있고 자동화·한도 회피·계정 악용이 명시되지 않은 경우에도 이 후보를 선택한다."),
    Candidate("manual-review", "모니터링 필요", "candidate_id: manual-review\nprototype: unresolved_duplicate_or_inconsistent_facts\nduplicate_order_count: positive_or_unknown OR failed_order_count: 1_to_2\norder_interval_and_frequency: inconsistent_or_unknown\nmatch_note: 중복·실패 가능성 또는 주문 간격과 빈도의 불일치는 추가 확인 대상이다."),
    Candidate("decline", "고위험 고객", "candidate_id: decline\nprototype: confirmed_automation_or_evasion\nautomation_detected: true OR limit_avoidance_detected: true\norders_per_minute: at_least_7\nmatch_note: 높은 빈도와 함께 자동화 또는 한도 회피가 명시적으로 확인된 경우에만 고위험 후보를 선택한다."),
    Candidate("decline", "고위험 고객", "candidate_id: decline\nprototype: confirmed_account_abuse_or_repeated_failures\naccount_abuse_detected: true OR failed_order_count: at_least_3\nmultiple_accounts: true_or_confirmed\nmatch_note: 다계정 악용 또는 반복 실패가 명시적으로 확인된 고위험 패턴이다."),
]

DEFAULT_MIN_MARGIN = 0.0
DEFAULT_MIN_SCORE = 0.0
DEFAULT_ORDER_POLICY_DOCUMENT = (Path(__file__).resolve().parents[2] / "docs" / "customer_order_risk_policy.md").read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class OrderObservations:
    authenticated: bool | None = None
    min_order_interval_seconds: int | None = None
    orders_per_minute: int | None = None
    duplicate_order_count: int | None = None
    failed_order_count: int | None = None
    limit_exceeded: bool | None = None
    limit_avoidance_detected: bool | None = None
    automation_detected: bool | None = None
    account_abuse_detected: bool | None = None


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
    strategy: str = DEFAULT_STRATEGY
    model: str = ""
    top1_score: float = 0.0
    top2_score: float = 0.0
    observations: dict[str, bool | int | None] = field(default_factory=dict)
    policy_validation: dict[str, Any] = field(default_factory=dict)
    ranked_documents: tuple[dict[str, Any], ...] = ()


def observations_dict(o: OrderObservations) -> dict[str, bool | int | None]:
    return {"authenticated": o.authenticated, "min_order_interval_seconds": o.min_order_interval_seconds,
            "orders_per_minute": o.orders_per_minute, "duplicate_order_count": o.duplicate_order_count,
            "failed_order_count": o.failed_order_count, "limit_exceeded": o.limit_exceeded,
            "limit_avoidance_detected": o.limit_avoidance_detected,
            "automation_detected": o.automation_detected, "account_abuse_detected": o.account_abuse_detected}


def _yaml_bool(text: str, field: str) -> bool | None:
    found = re.search(rf"(?im)^\s*{field}\s*:\s*(true|false|null|unknown)\s*$", text)
    return {"true": True, "false": False}.get(found.group(1).lower()) if found else None


def _yaml_int(text: str, field: str) -> int | None:
    found = re.search(rf"(?im)^\s*{field}\s*:\s*(\d+|null|unknown)\s*$", text)
    return int(found.group(1)) if found and found.group(1).isdigit() else None


def extract_observations(case_text: str) -> OrderObservations:
    """Conservatively extract explicit facts; missing values remain unknown."""
    text, low = case_text.strip(), case_text.lower()
    auth, interval = _yaml_bool(text, "authenticated"), _yaml_int(text, "min_order_interval_seconds")
    rate, duplicate = _yaml_int(text, "orders_per_minute"), _yaml_int(text, "duplicate_order_count")
    failed, limit = _yaml_int(text, "failed_order_count"), _yaml_bool(text, "limit_exceeded")
    limit_avoidance = _yaml_bool(text, "limit_avoidance_detected")
    automation, abuse = _yaml_bool(text, "automation_detected"), _yaml_bool(text, "account_abuse_detected")
    if auth is None:
        auth = True if re.search(r"인증된 고객|인증은 모두 성공|authenticated customer", text, re.I) else (False if re.search(r"인증되지 않은|unauthenticated", text, re.I) else None)
    if interval is None:
        found = re.search(r"(\d+)\s*(?:~\s*\d+\s*)?초\s*(?:이상|간격|마다)", text)
        interval = int(found.group(1)) if found else None
    if rate is None:
        found = re.search(r"(?:1분\s*(?:에|당|동안)|분당)\s*(\d+)\s*회", text)
        rate = int(found.group(1)) if found else None
    no_duplicate_failure_limit = bool(re.search(r"중복\s*,?\s*실패\s*,?\s*한도 초과(?:는|가)?\s*(?:없다|없음|없습니다)", text, re.I))
    if duplicate is None:
        if no_duplicate_failure_limit or re.search(r"중복(?: 주문)?(?:은|,)?\s*(?:없다|없음|없습니다)", text, re.I): duplicate = 0
        elif re.search(r"중복|동일 .*주문.*(?:두 번|2회)|duplicate", text, re.I): duplicate = 1
    if failed is None:
        if no_duplicate_failure_limit or re.search(r"(?:실패|failed)[^\n.]{0,20}(?:없다|없음|없습니다)|실패는 없다", text, re.I): failed = 0
        else:
            found = re.search(r"(?:인증|결제|주문)?\s*실패(?:가|은)?\s*(?:총\s*)?(\d+)회", text)
            failed = int(found.group(1)) if found else None
    if limit is None:
        limit = False if no_duplicate_failure_limit or re.search(r"한도 초과(?:는|가)?\s*(?:없다|없음|없습니다)", text, re.I) else (True if re.search(r"한도 초과|limit exceeded", text, re.I) else None)
    if limit_avoidance is None and re.search(r"한도 회피|(?:분할|나누어) 구매", text, re.I):
        limit_avoidance = True
    if automation is None:
        automation = False if re.search(r"자동화 (?:정황|주문).*?(?:없|미확인)", text, re.I) else (True if re.search(r"자동화|bot", low, re.I) else None)
    if abuse is None and re.search(r"다계정|계정 악용|multiple accounts|account abuse", low, re.I): abuse = True
    return OrderObservations(auth, interval, rate, duplicate, failed, limit, limit_avoidance, automation, abuse)


def build_structured_query(case_text: str) -> tuple[str, OrderObservations]:
    """Build fact-only YAML. It contains no predicted class or recommendation."""
    facts = extract_observations(case_text)
    lines = ["task: customer_order_behavior_classification", "observations:"]
    for name, value in observations_dict(facts).items():
        rendered = "unknown" if value is None else str(value).lower()
        unit = " seconds" if name == "min_order_interval_seconds" and value is not None else (" per_minute" if name == "orders_per_minute" and value is not None else "")
        lines.append(f"  {name}: {rendered}{unit}")
    return "\n".join(lines), facts


def _summary(case_text: str, policy: str, settings: Settings) -> str:
    """V1 only: retain the original LLM-summary baseline for comparison."""
    prompt = (
        "정책 문서와 고객 행동을 바탕으로 reranker용 정책 해석을 한국어 1~2문장으로 작성하세요. "
        "고객 등급·추천·최종 결론은 쓰지 마세요. 입력 사실만 사용하세요.\n\n정책 문서:\n"
        + policy + "\n\n고객 행동:\n" + case_text
    )
    return chat_text(settings, [
        {"role": "system", "content": "제공된 문서와 사실만 사용하는 정책 분석가입니다."},
        {"role": "user", "content": prompt},
    ]).strip()


def _rank_response(response: requests.Response, candidates: list[Candidate]) -> list[RankedCandidate]:
    response.raise_for_status()
    results = response.json().get("results")
    if not isinstance(results, list):
        raise ValueError("Cohere reranker 응답에 results가 없습니다.")
    scores: dict[int, float] = {}
    for result in results:
        index = int(result["index"])
        if index < 0 or index >= len(candidates):
            raise ValueError("Cohere reranker가 범위를 벗어난 document index를 반환했습니다.")
        scores[index] = float(result["relevance_score"])
    return sorted(
        (RankedCandidate(candidate, scores.get(index, 0.0)) for index, candidate in enumerate(candidates)),
        key=lambda item: (-item.score, item.candidate.id),
    )


def _deployment(settings: Settings) -> tuple[str, str]:
    for deployment in list_running_deployments(settings):
        model = deployment.get("details", {}).get("resources", {}).get("backendDetails", {}).get("model", {})
        name = str(model.get("name", ""))
        url = str(deployment.get("deploymentUrl", "")).rstrip("/")
        if name == settings.rerank_model and url:
            return url, name
    raise RuntimeError("현재 AI Core Resource Group에 RUNNING Cohere reranker deployment가 없습니다.")


def build_rerank_payload(query: str, candidates: list[Candidate], model: str) -> dict[str, Any]:
    """Exact request body sent to Rerank; authentication headers are excluded."""
    return {"model": model, "query": query, "documents": [item.description for item in candidates], "top_n": len(candidates)}


def _rank(query: str, candidates: list[Candidate], settings: Settings) -> tuple[list[RankedCandidate], str]:
    body = build_rerank_payload(query, candidates, settings.rerank_model)
    if settings.rerank_endpoint:
        headers = {"Content-Type": "application/json"}
        if settings.rerank_api_key:
            headers["Authorization"] = f"Bearer {settings.rerank_api_key}"
        response = requests.post(settings.rerank_endpoint, headers=headers, json=body, timeout=15)
        return _rank_response(response, candidates), "cohere_rerank_litellm"
    url, model = _deployment(settings)
    body["model"] = model
    response = requests.post(f"{url}/rerank", headers=api_headers(settings), json=body, timeout=30)
    return _rank_response(response, candidates), "cohere_rerank_ai_core"


def build_reranker_query(case_text: str) -> tuple[str, OrderObservations]:
    """Preserve the original statement and add fact-only YAML for reranking."""
    structured, facts = build_structured_query(case_text)
    statement = case_text.replace("\n", "\n  ")
    return f"{structured}\ncustomer_statement: |\n  {statement}", facts


def _strategy_inputs(case_text: str, policy: str, settings: Settings, strategy: Strategy, candidates: list[Candidate] | None) -> tuple[str, list[Candidate], OrderObservations]:
    if strategy not in {"v1", "v2", "v3"}:
        raise ValueError("strategy는 v1, v2, v3 중 하나여야 합니다.")
    if candidates is not None:
        if strategy == "v1":
            return _summary(case_text, policy, settings), candidates, OrderObservations()
        query, facts = build_reranker_query(case_text)
        return query, candidates, facts
    if strategy == "v1":
        return _summary(case_text, policy, settings), APPLICATION_DECISIONS, OrderObservations()
    if strategy == "v2":
        query, facts = build_reranker_query(case_text)
        return query, STRUCTURED_DECISIONS, facts
    query, facts = build_reranker_query(case_text)
    return query, MULTI_PROTOTYPE_DECISIONS, facts


def _aggregate_scores(ranked: list[RankedCandidate]) -> dict[str, float]:
    """Use max prototype relevance per class; V3 has equal prototype counts."""
    scores: dict[str, float] = {}
    for item in ranked:
        scores[item.candidate.id] = max(scores.get(item.candidate.id, float("-inf")), item.score)
    return scores


def validate_policy(observations: OrderObservations) -> dict[str, Any]:
    """Check only explicit policy conditions; this never changes a customer state."""
    findings: list[str] = []
    recommended_class: str | None = None
    if observations.orders_per_minute is not None and 4 <= observations.orders_per_minute <= 6:
        findings.append("정책상 분당 4~6회 주문은 관찰 대상입니다.")
        recommended_class = "manual-review"
    if observations.min_order_interval_seconds is not None and observations.min_order_interval_seconds < 20:
        findings.append("정책상 20초 미만 반복 주문 간격은 관찰 대상입니다.")
        recommended_class = "manual-review"
    if observations.duplicate_order_count is not None and observations.duplicate_order_count > 0:
        findings.append("중복 주문 가능성이 관측되었습니다.")
        recommended_class = "manual-review"
    if observations.failed_order_count is not None and 1 <= observations.failed_order_count <= 2:
        findings.append("인증·결제·주문 실패 1~2회가 관측되었습니다.")
        recommended_class = "manual-review"
    if observations.limit_exceeded is True:
        findings.append("한도 초과가 관측되었습니다.")
        recommended_class = "manual-review"
    if observations.limit_avoidance_detected is True:
        findings.append("분할 구매 또는 한도 회피 정황이 관측되었습니다.")
        recommended_class = "manual-review"
    if observations.failed_order_count is not None and observations.failed_order_count >= 3:
        findings.append("반복 실패 3회 이상이 관측되었습니다.")
        recommended_class = "decline"
    if observations.orders_per_minute is not None and observations.orders_per_minute >= 7 and (observations.automation_detected is True or observations.account_abuse_detected is True):
        findings.append("분당 7회 이상과 자동화 또는 계정 악용 정황이 함께 관측되었습니다.")
        recommended_class = "decline"
    if observations.orders_per_minute is not None and observations.orders_per_minute >= 7 and observations.limit_avoidance_detected is True:
        findings.append("분당 7회 이상과 한도 회피 정황이 함께 관측되었습니다.")
        recommended_class = "decline"
    if observations.automation_detected is True or observations.account_abuse_detected is True:
        findings.append("자동화 또는 계정 악용 정황이 관측되었습니다.")
        recommended_class = "decline"
    return {"enabled": True, "findings": findings, "recommended_class": recommended_class, "requires_review": bool(findings)}


def recommend(
    case_text: str,
    candidates: list[Candidate] | None = None,
    settings: Settings | None = None,
    policy_document: str | None = None,
    min_margin: float = DEFAULT_MIN_MARGIN,
    min_score: float = DEFAULT_MIN_SCORE,
    strategy: Strategy = DEFAULT_STRATEGY,
    enable_policy_validation: bool = False,
    enable_uncertainty_detection: bool = False,
) -> DecisionResult:
    cleaned = case_text.strip()
    if not cleaned:
        raise ValueError("고객 행동을 입력하세요.")
    if min_margin < 0 or min_score < 0:
        raise ValueError("min_margin과 min_score는 0 이상이어야 합니다.")
    if not settings:
        raise RuntimeError("AI Core LLM 및 Cohere reranker 설정이 필요합니다.")
    policy = (policy_document or DEFAULT_ORDER_POLICY_DOCUMENT).strip()
    if not policy:
        raise ValueError("정책 document를 입력하세요.")
    query, selected, facts = _strategy_inputs(cleaned, policy, settings, strategy, candidates)
    if enable_policy_validation or enable_uncertainty_detection:
        _, facts = build_structured_query(cleaned)
    try:
        if not query:
            raise RuntimeError("reranker query를 생성하지 못했습니다.")
        ranked, engine = _rank(query, selected, settings)
    except (requests.RequestException, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise RuntimeError("Cohere reranker 호출에 실패했습니다. 설정과 deployment 상태를 확인하세요.") from error
    if not ranked:
        raise RuntimeError("Cohere reranker가 후보 점수를 반환하지 않았습니다.")

    scores = _aggregate_scores(ranked)
    ordered_scores = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    winner_id, top1_score = ordered_scores[0]
    top2_score = ordered_scores[1][1] if len(ordered_scores) > 1 else 0.0
    margin = top1_score - top2_score
    reasons: list[str] = []
    if winner_id == "manual-review":
        reasons.append("가장 관련도 높은 후보가 manual-review입니다.")
    if top1_score < min_score:
        reasons.append(f"최고 점수 {top1_score:.3f}가 최소 점수 {min_score:.3f}보다 낮습니다.")
    if len(ordered_scores) > 1 and margin < min_margin:
        reasons.append(f"1·2위 점수 차이 {margin:.3f}가 최소 margin {min_margin:.3f}보다 작습니다.")
    validation = validate_policy(facts) if enable_policy_validation else {"enabled": False, "findings": [], "recommended_class": None, "requires_review": False}
    if validation["requires_review"]:
        reasons.extend(validation["findings"])
    missing = [name for name, value in observations_dict(facts).items() if value is None]
    if enable_uncertainty_detection and missing:
        reasons.append("확인되지 않은 관측값이 있습니다: " + ", ".join(missing))

    source_indexes = {id(candidate): index for index, candidate in enumerate(selected)}
    ranked_documents = tuple(
        {"returned_rank": rank + 1, "source_index": source_indexes.get(id(item.candidate), next((index for index, candidate in enumerate(selected) if candidate.id == item.candidate.id), -1)), "id": item.candidate.id, "score": item.score}
        for rank, item in enumerate(ranked)
    )
    final_recommendation = validation["recommended_class"] or ("manual-review" if reasons else winner_id)
    return DecisionResult(
        recommendation=final_recommendation,
        scores=scores,
        margin=margin,
        engine=engine,
        reason="Cohere reranker가 고객 행동 원문·확인된 사실과 후보 기준의 관련도를 순위화했습니다. " + (" ".join(reasons) if reasons else "점수와 margin 기준을 충족해 추천을 생성했습니다."),
        requires_human_review=bool(reasons),
        policy_summary=query,
        policy_id=f"sha256:{sha256(policy.encode('utf-8')).hexdigest()[:12]}",
        strategy=strategy,
        model=settings.rerank_model,
        top1_score=top1_score,
        top2_score=top2_score,
        observations=observations_dict(facts),
        policy_validation=validation,
        ranked_documents=ranked_documents,
    )


def run_decision_recommendation(
    case_text: str,
    settings: Settings,
    policy_document: str | None = None,
    candidates: list[Candidate] | None = None,
    min_margin: float = DEFAULT_MIN_MARGIN,
    min_score: float = DEFAULT_MIN_SCORE,
    strategy: Strategy = DEFAULT_STRATEGY,
    enable_policy_validation: bool = False,
    enable_uncertainty_detection: bool = False,
    recommendation_runner: Callable[..., DecisionResult] = recommend,
) -> dict[str, Any]:
    """JSON-friendly, read-only result consumed by the CLI and Gradio UI."""
    cleaned = case_text.strip()
    if not cleaned:
        raise ValueError("고객 행동을 입력하세요.")
    outcome = recommendation_runner(
        cleaned, candidates=candidates, settings=settings, policy_document=policy_document,
        min_margin=min_margin, min_score=min_score, strategy=strategy,
        enable_policy_validation=enable_policy_validation,
        enable_uncertainty_detection=enable_uncertainty_detection,
    )
    display_candidates = candidates or (
        APPLICATION_DECISIONS if strategy == "v1"
        else STRUCTURED_DECISIONS if strategy == "v2"
        else MULTI_PROTOTYPE_DECISIONS
    )
    labels = {candidate.id: candidate.label for candidate in display_candidates}
    ranked = sorted(outcome.scores.items(), key=lambda item: (-item[1], item[0]))
    return {
        "case": cleaned,
        "recommendation": outcome.recommendation,
        "recommendation_label": labels.get(outcome.recommendation, outcome.recommendation),
        "risk_class": DECISION_CLASS.get(outcome.recommendation, "REVIEW_REQUIRED"),
        "requires_human_review": outcome.requires_human_review,
        "margin": outcome.margin,
        "top1_score": outcome.top1_score,
        "top2_score": outcome.top2_score,
        "engine": outcome.engine,
        "model": outcome.model,
        "strategy": outcome.strategy,
        "reason": outcome.reason,
        "policy_summary": outcome.policy_summary,
        "policy_id": outcome.policy_id,
        "observations": outcome.observations,
        "policy_validation": outcome.policy_validation,
        "decision_thresholds": {"min_score": min_score, "min_margin": min_margin},
        "ranked_candidates": [
            {"rank": index + 1, "id": key, "label": labels.get(key, key), "risk_class": DECISION_CLASS.get(key), "score": value}
            for index, (key, value) in enumerate(ranked)
        ],
        "ranked_documents": list(outcome.ranked_documents),
        "action": "추천만 생성했습니다. 승인·반려 상태는 변경하지 않았습니다.",
    }
