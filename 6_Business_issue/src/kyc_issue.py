"""Read-only KYC review scenario composed with the local Harness dispatcher."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from business_issue import MODULE_ROOT, _load_harness, route_request

DEFAULT_CASE_PATH = MODULE_ROOT / "fixtures" / "kyc_case.json"


def load_kyc_case(path: Path | str = DEFAULT_CASE_PATH) -> dict[str, Any]:
    """Load a synthetic, non-PII KYC review case."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_kyc_evidence_packet(case: dict[str, Any]) -> dict[str, Any]:
    """Keep source-labelled verification facts separate from the risk judgement."""
    verification = case["verification"]
    observations = [
        {"check": "corporate_registration", "result": "verified" if verification["corporate_registration_verified"] else "not_verified"},
        {"check": "representative_identity", "result": "verified" if verification["representative_identity_verified"] else "not_verified"},
        {"check": "ultimate_beneficial_owner", "result": "verified" if verification["ultimate_beneficial_owner_verified"] else "not_verified"},
        {"check": "sanctions", "result": verification["sanctions_screening"]},
        {"check": "pep", "result": verification["pep_screening"]},
        {"check": "adverse_media", "result": verification["adverse_media"]},
    ]
    return {
        "request_scope": case["request"],
        "customer_id": case["customer"]["customer_id"],
        "sources": case["sources"],
        "observations": observations,
        "limitation": "Screening results are a point-in-time snapshot; a compliance analyst must resolve possible matches.",
    }


def assess_kyc(case: dict[str, Any]) -> dict[str, Any]:
    """Apply explicit KYC policy gates; never activate an account in this demo."""
    verification = case["verification"]
    flags: list[str] = []
    if verification["sanctions_screening"] == "confirmed_match":
        decision = "block"
        flags.append("confirmed_sanctions_match")
    else:
        if not verification["ultimate_beneficial_owner_verified"]:
            flags.append("unverified_ubo")
        if verification["pep_screening"] == "possible_match":
            flags.append("possible_pep_match")
        if flags:
            decision = "enhanced_due_diligence"
        else:
            decision = "eligible_for_compliance_approval"

    required_actions = []
    if "unverified_ubo" in flags:
        required_actions.append("Collect and verify ultimate beneficial owner identification documents.")
    if "possible_pep_match" in flags:
        required_actions.append("Compliance analyst must resolve the possible PEP match and document the rationale.")
    if decision == "block":
        required_actions.append("Do not onboard or transact; escalate according to sanctions procedure.")
    return {
        "decision": decision,
        "risk_flags": flags,
        "required_actions": required_actions,
        "account_activation_allowed": False,
    }


def kyc_summary(assessment: dict[str, Any]) -> str:
    if assessment["decision"] == "block":
        return "확정 제재 매칭이 확인되어 계정 개설과 거래를 중단하고 제재 절차로 이관해야 합니다."
    if assessment["decision"] == "enhanced_due_diligence":
        return "제재 확정 매칭은 없지만 UBO 미확인 및 PEP 가능 매칭이 있어 강화심사 대상입니다. 준법감시인의 확인 전에는 계정을 개설하지 마세요."
    return "필수 확인 항목이 충족되었습니다. 준법감시인의 최종 승인 후에만 계정을 개설하세요."


def solve_kyc_issue(case: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run KYC evidence gathering and policy assessment up to a compliance approval gate."""
    case = case or load_kyc_case()
    default_prompt, _, _ = _load_harness()
    assessment = assess_kyc(case)
    return {
        "case_id": case["case_id"],
        "route": route_request(case["request"]),
        "business_agent_prompt_loaded": bool(default_prompt("business_agent")),
        "evidence_packet": build_kyc_evidence_packet(case),
        "assessment": assessment,
        "analyst_writer_answer": kyc_summary(assessment),
        "action": "compliance_approval_required",
        "write_performed": False,
    }
