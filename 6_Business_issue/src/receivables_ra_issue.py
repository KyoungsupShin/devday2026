"""Read-only receivables Risk Assessment (RA) scenario using Harness dispatch."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from business_issue import MODULE_ROOT, _load_harness, route_request

DEFAULT_CASE_PATH = MODULE_ROOT / "fixtures" / "receivables_ra_case.json"


def load_receivables_ra_case(path: Path | str = DEFAULT_CASE_PATH) -> dict[str, Any]:
    """Load a synthetic accounts-receivable risk review case."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_receivables_evidence_packet(case: dict[str, Any]) -> dict[str, Any]:
    aging = case["aging_krw"]
    overdue = sum(amount for bucket, amount in aging.items() if bucket != "current")
    outstanding = sum(aging.values())
    return {
        "request_scope": case["request"],
        "customer_id": case["customer"]["customer_id"],
        "sources": case["sources"],
        "credit_limit_krw": case["credit"]["credit_limit_krw"],
        "current_exposure_krw": case["credit"]["current_exposure_krw"],
        "requested_order_krw": case["credit"]["requested_order_krw"],
        "aging_krw": aging,
        "overdue_krw": overdue,
        "overdue_ratio": overdue / outstanding if outstanding else 0,
        "limitation": "Ledger snapshot does not prove a future payment; collection confirmation is required before release.",
    }


def assess_receivables_risk(case: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Calculate exposure and apply transparent credit policy gates."""
    credit = case["credit"]
    policy = case["policy"]
    post_order_exposure = credit["current_exposure_krw"] + credit["requested_order_krw"]
    over_limit_amount = max(0, post_order_exposure - credit["credit_limit_krw"])
    flags: list[str] = []
    if case["aging_krw"]["over_90"] > 0:
        flags.append("over_90_days_past_due")
        decision = "shipment_hold"
    else:
        if over_limit_amount:
            flags.append("credit_limit_exceeded")
        if evidence["overdue_ratio"] > policy["max_standard_overdue_ratio"]:
            flags.append("overdue_ratio_exceeded")
        decision = "conditional_release" if flags else "eligible_for_credit_approval"

    conditions = []
    if over_limit_amount:
        conditions.append(f"Secure payment or collateral for the {over_limit_amount:,} KRW credit-limit excess.")
    if "overdue_ratio_exceeded" in flags:
        conditions.append("Confirm a collection plan for overdue receivables before shipment release.")
    if decision == "shipment_hold":
        conditions.append("Keep shipment on hold until the 90+ day balance is resolved by credit management.")
    return {
        "decision": decision,
        "risk_flags": flags,
        "post_order_exposure_krw": post_order_exposure,
        "over_limit_amount_krw": over_limit_amount,
        "conditions": conditions,
        "shipment_release_allowed": False,
    }


def receivables_summary(assessment: dict[str, Any]) -> str:
    if assessment["decision"] == "shipment_hold":
        return "90일 초과 연체가 있어 출고를 보류해야 합니다. 신용관리 부서의 해제 승인 전에는 주문을 진행하지 마세요."
    if assessment["decision"] == "conditional_release":
        return (f"신규 주문 후 여신한도를 {assessment['over_limit_amount_krw']:,}원 초과하고 연체 비율도 정책 기준을 넘습니다. "
                "초과분 결제·담보와 회수계획 확인을 조건으로 신용관리 승인 후 출고를 검토하세요.")
    return "정책상 즉시 차단 사유는 없습니다. 신용관리 부서의 최종 승인 후에만 출고하세요."


def solve_receivables_ra_issue(case: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the receivables RA through a credit-manager approval gate."""
    case = case or load_receivables_ra_case()
    default_prompt, _, _ = _load_harness()
    evidence = build_receivables_evidence_packet(case)
    assessment = assess_receivables_risk(case, evidence)
    return {
        "case_id": case["case_id"],
        "route": route_request(case["request"]),
        "business_agent_prompt_loaded": bool(default_prompt("business_agent")),
        "evidence_packet": evidence,
        "assessment": assessment,
        "analyst_writer_answer": receivables_summary(assessment),
        "action": "credit_manager_approval_required",
        "write_performed": False,
    }
