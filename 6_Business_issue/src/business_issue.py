"""A read-only inventory replenishment example that composes the local Harness.

Quantities and money are intentionally calculated in deterministic Python.  Harness
is used for specialist dispatch and for the evidence-to-answer boundary; a human
approval remains required before a write tool could create a purchase order.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[0]
DEFAULT_CASE_PATH = MODULE_ROOT / "fixtures" / "replenishment_case.json"


def load_case(path: Path | str = DEFAULT_CASE_PATH) -> dict[str, Any]:
    """Load the fixture standing in for read-only ERP and policy tools."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_harness():
    """Import the Harness package without requiring repository installation."""
    for directory in (REPOSITORY_ROOT / "shared", REPOSITORY_ROOT / "5_harness"):
        directory_text = str(directory)
        if directory_text in sys.path:
            sys.path.remove(directory_text)
        sys.path.insert(0, directory_text)

    from src.harness_prompts import default_prompt
    from src.reranker import SPECIALIST_CANDIDATES, decide

    return default_prompt, SPECIALIST_CANDIDATES, decide


def route_request(request: str) -> dict[str, Any]:
    """Use the existing Harness specialist dispatcher for the business request."""
    _, candidates, decide = _load_harness()
    decision = decide(request, candidates)
    return {
        "selected": decision.selected,
        "scores": decision.scores,
        "margin": decision.margin,
        "engine": decision.engine,
        "fallback": decision.fallback,
    }


def build_evidence_packet(case: dict[str, Any]) -> dict[str, Any]:
    """Build the compact, source-labelled packet expected from Business Agent."""
    observations = []
    for item in case["items"]:
        projected = item["on_hand"] - item["forecast_demand"]
        gap_to_safety = max(0, item["safety_stock"] - projected)
        observations.append(
            {
                "sku": item["sku"],
                "name": item["name"],
                "projected_stock": projected,
                "safety_stock": item["safety_stock"],
                "gap_to_safety": gap_to_safety,
                "risk": "safety_stock_breach" if gap_to_safety else "within_safety_stock",
            }
        )
    return {
        "request_scope": case["request"],
        "sources": case["sources"],
        "observations": observations,
        "limitation": "Fixture is a read-only snapshot; supplier capacity and delivery dates require confirmation before approval.",
    }


def draft_replenishment(case: dict[str, Any], evidence_packet: dict[str, Any]) -> dict[str, Any]:
    """Apply explicit policy rules: safety stock, MOQ, eligible discount and budget."""
    by_sku = {observation["sku"]: observation for observation in evidence_packet["observations"]}
    lines = []
    for item in case["items"]:
        gap = by_sku[item["sku"]]["gap_to_safety"]
        if not gap:
            continue
        quantity = max(gap, item["moq"])
        discount_applied = bool(item["discount_threshold"] and quantity >= item["discount_threshold"])
        discount_rate = item["discount_rate"] if discount_applied else 0
        gross_cost = quantity * item["unit_price_krw"]
        net_cost = round(gross_cost * (1 - discount_rate))
        lines.append(
            {
                "sku": item["sku"],
                "name": item["name"],
                "quantity": quantity,
                "reason": f"Safety-stock gap {gap:,} units; MOQ {item['moq']:,} units applied",
                "discount_rate": discount_rate,
                "net_cost_krw": net_cost,
            }
        )
    total = sum(line["net_cost_krw"] for line in lines)
    return {
        "lines": lines,
        "total_order_cost_krw": total,
        "budget_krw": case["budget_krw"],
        "remaining_budget_krw": case["budget_krw"] - total,
        "within_budget": total <= case["budget_krw"],
    }


def analyst_summary(recommendation: dict[str, Any]) -> str:
    """Produce a concise Korean answer analogous to Analyst Writer's final handoff."""
    ordered_skus = ", ".join(line["sku"] for line in recommendation["lines"]) or "없음"
    budget_status = "예산 이내" if recommendation["within_budget"] else "예산 초과"
    return (
        f"{ordered_skus}는 다음 주 수요 후 안전재고 미달이 예상됩니다. "
        f"MOQ와 SKU-B 할인 정책을 반영한 발주 초안은 {recommendation['total_order_cost_krw']:,}원으로 "
        f"{budget_status}입니다(잔여 {recommendation['remaining_budget_krw']:,}원). "
        "공급 가능일을 확인한 뒤 담당자 승인 후에만 발주하세요."
    )


def solve_business_issue(case: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the read-only Harness-shaped flow and stop at the human approval gate."""
    case = case or load_case()
    default_prompt, _, _ = _load_harness()
    route = route_request(case["request"])
    evidence_packet = build_evidence_packet(case)
    recommendation = draft_replenishment(case, evidence_packet)
    return {
        "case_id": case["case_id"],
        "route": route,
        "business_agent_prompt_loaded": bool(default_prompt("business_agent")),
        "evidence_packet": evidence_packet,
        "recommendation": recommendation,
        "analyst_writer_answer": analyst_summary(recommendation),
        "action": "approval_required",
        "write_performed": False,
    }
