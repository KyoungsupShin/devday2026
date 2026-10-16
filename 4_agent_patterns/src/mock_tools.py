"""Safe mock MCP tools; no external state is changed unless explicitly enabled."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _data() -> dict[str, Any]:
    return json.loads((ROOT / "fixtures" / "sample_business_data.json").read_text(encoding="utf-8"))


def get_inventory() -> list[dict[str, Any]]:
    return _data()["inventory"]


def search_policy(query: str) -> list[dict[str, str]]:
    return [item for item in _data()["policies"] if any(word in item["text"].lower() for word in query.lower().split())]


def draft_reorder(item: str, quantity: int, approved: bool = False) -> dict[str, Any]:
    plan = {"item": item, "quantity": quantity, "status": "approved_and_executed" if approved else "approval_required"}
    if not approved:
        plan["message"] = "안전 모드: 발주를 실행하지 않았습니다. 승인 후에만 외부 쓰기를 허용하세요."
    return plan


TOOLS = {"get_inventory": get_inventory, "search_policy": search_policy, "draft_reorder": draft_reorder}

