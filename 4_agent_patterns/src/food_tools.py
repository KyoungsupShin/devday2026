"""Read-only Tool Calling functions and Agent-as-a-Tool helpers for Food specialists."""
from __future__ import annotations

from threading import Lock
from typing import Any

import requests

from lab_common.ai_core import chat_text


_TOOL_SCHEMAS: dict[str, list[dict[str, Any]]] = {
    "work-planning": [
        {"type": "function", "function": {"name": "constraint_check", "description": "판매가·영양·조리 조건의 누락 여부를 점검합니다.", "parameters": {"type": "object", "properties": {"retail_price_krw": {"type": "number"}, "protein_g": {"type": "number"}, "microwaveable": {"type": "boolean"}}, "required": ["retail_price_krw", "protein_g", "microwaveable"], "additionalProperties": False}}},
    ],
    "food-rnd": [
        {"type": "function", "function": {"name": "nutrition_check", "description": "단백질 목표와 열량·나트륨 추정치를 점검합니다.", "parameters": {"type": "object", "properties": {"protein_g": {"type": "number"}, "kcal": {"type": "number"}, "sodium_mg": {"type": "number"}}, "required": ["protein_g", "kcal", "sodium_mg"], "additionalProperties": False}}},
        {"type": "function", "function": {"name": "open_food_facts_search", "description": "Open Food Facts 공개 API에서 제품 키워드의 식품 라벨 데이터를 읽기 전용으로 조회합니다.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}}},
    ],
    "procurement": [
        {"type": "function", "function": {"name": "ingredient_cost_total", "description": "추정 원재료 단가의 합계를 계산합니다.", "parameters": {"type": "object", "properties": {"costs_krw": {"type": "array", "items": {"type": "number"}}}, "required": ["costs_krw"], "additionalProperties": False}}},
    ],
    "quality-assurance": [
        {"type": "function", "function": {"name": "haccp_risk_check", "description": "식별된 위해요소의 예방관리 필요도를 표준 기준으로 점검합니다.", "parameters": {"type": "object", "properties": {"hazards": {"type": "array", "items": {"type": "string"}}}, "required": ["hazards"], "additionalProperties": False}}},
    ],
    "marketing": [
        {"type": "function", "function": {"name": "marketing_claim_check", "description": "마케팅 문구가 검증·법무 검토를 필요로 하는지 표시합니다.", "parameters": {"type": "object", "properties": {"claims": {"type": "array", "items": {"type": "string"}}}, "required": ["claims"], "additionalProperties": False}}},
        {"type": "function", "function": {"name": "open_food_facts_search", "description": "Open Food Facts 공개 API에서 제품 키워드의 식품 라벨 데이터를 읽기 전용으로 조회합니다.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}}},
        {"type": "function", "function": {"name": "generate_marketing_html", "description": "Marketing HTML Agent에게 상품의 한 장짜리 프로모션 HTML 시안 생성을 요청합니다.", "parameters": {"type": "object", "properties": {"product_name": {"type": "string"}, "positioning": {"type": "string"}, "key_messages": {"type": "array", "items": {"type": "string"}}}, "required": ["product_name", "positioning", "key_messages"], "additionalProperties": False}}},
    ],
    "finance": [
        {"type": "function", "function": {"name": "unit_economics", "description": "판매가와 단위원가로 단위 공헌이익과 공헌이익률을 계산합니다.", "parameters": {"type": "object", "properties": {"retail_price_krw": {"type": "number"}, "unit_cost_krw": {"type": "number"}}, "required": ["retail_price_krw", "unit_cost_krw"], "additionalProperties": False}}},
    ],
}

_TOOL_TYPES = {
    "constraint_check": "Function / validation",
    "nutrition_check": "Function / calculation",
    "ingredient_cost_total": "Function / calculation",
    "haccp_risk_check": "Function / validation",
    "marketing_claim_check": "Function / validation",
    "unit_economics": "Function / calculation",
    "open_food_facts_search": "API / read-only",
    "generate_marketing_html": "Agent as a Tool",
}

_MARKETING_HTML_AGENT_PROMPT = """You are a Marketing HTML Agent. Create one compact, self-contained Korean promotional
HTML fragment from the supplied product brief. Return HTML only, with minimal inline
CSS. Do not include Markdown, scripts, forms, external URLs, images, or unsupported
health claims. Keep the complete HTML under 900 characters."""

_LATEST_MARKETING_HTML: dict[str, str] | None = None
_MARKETING_HTML_LOCK = Lock()


def latest_marketing_html_draft() -> dict[str, str] | None:
    """Return the latest HTML draft created in this Python process, if any.

    This is a notebook/UI handoff convenience only. The draft is not published,
    written to disk, or shared outside the current local process.
    """
    with _MARKETING_HTML_LOCK:
        return dict(_LATEST_MARKETING_HTML) if _LATEST_MARKETING_HTML else None


def _remember_marketing_html(html_draft: str) -> None:
    global _LATEST_MARKETING_HTML
    with _MARKETING_HTML_LOCK:
        _LATEST_MARKETING_HTML = {"agent_label": "Marketing HTML Agent", "html": html_draft}


def tools_for_food_agent(agent_id: str) -> list[dict[str, Any]]:
    """Return the OpenAI-compatible Tool Calling schemas assigned to one Agent."""
    return [dict(schema) for schema in _TOOL_SCHEMAS.get(agent_id, [])]


def tool_names_for_food_agent(agent_id: str) -> list[str]:
    return [schema["function"]["name"] for schema in tools_for_food_agent(agent_id)]


def tool_catalog_for_food_agent(agent_id: str) -> list[dict[str, str]]:
    """Return public names, types, and descriptions without exposing JSON schemas."""
    return [
        {"name": schema["function"]["name"], "type": _TOOL_TYPES[schema["function"]["name"]], "description": schema["function"]["description"]}
        for schema in tools_for_food_agent(agent_id)
    ]


def execute_food_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    request: str = "",
    settings: Any = None,
) -> dict[str, Any]:
    """Execute a local read-only specialist aid; it never performs external writes."""
    if name == "constraint_check":
        missing = [key for key, value in arguments.items() if value is None]
        return {"missing_fields": missing, "protein_target_met": arguments["protein_g"] >= 30, "microwaveable": arguments["microwaveable"]}
    if name == "nutrition_check":
        return {"protein_target_met": arguments["protein_g"] >= 30, "estimated_kcal": arguments["kcal"], "estimated_sodium_mg": arguments["sodium_mg"], "all_values_are_estimates": True}
    if name == "ingredient_cost_total":
        costs = arguments["costs_krw"]
        return {"ingredient_cost_total_krw": round(sum(costs), 2), "line_item_count": len(costs), "all_values_are_estimates": True}
    if name == "haccp_risk_check":
        return {"hazards": arguments["hazards"], "required_controls": ["수입검사", "가열·냉각 관리", "교차오염 방지", "기록 검증"], "professional_verification_required": True}
    if name == "marketing_claim_check":
        return {"claims": arguments["claims"], "review_required": True, "note": "영양·건강 관련 표현은 표시·광고 적합성 검토가 필요합니다."}
    if name == "unit_economics":
        price = arguments["retail_price_krw"]
        cost = arguments["unit_cost_krw"]
        contribution = price - cost
        return {"retail_price_krw": price, "unit_cost_krw": cost, "contribution_krw": contribution, "contribution_margin_pct": round((contribution / price) * 100, 2) if price else None, "all_values_are_estimates": True}
    if name == "open_food_facts_search":
        response = requests.get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={"search_terms": arguments["query"], "search_simple": 1, "action": "process", "json": 1, "page_size": 3},
            timeout=15,
        )
        response.raise_for_status()
        products = response.json().get("products", [])
        return {"source": "Open Food Facts public API", "query": arguments["query"], "products": [{"name": product.get("product_name"), "nutrition_grade": product.get("nutrition_grades"), "nutriments": product.get("nutriments", {})} for product in products]}
    if name == "generate_marketing_html":
        if settings is None:
            raise ValueError("Agent as a Tool 실행에는 AI Core settings가 필요합니다.")
        html_draft = chat_text(
            settings,
            [
                {"role": "system", "content": _MARKETING_HTML_AGENT_PROMPT},
                {"role": "user", "content": f"제품명: {arguments['product_name']}\n포지셔닝: {arguments['positioning']}\n핵심 메시지: {arguments['key_messages']}\n원 요청: {request}"},
            ],
        )
        _remember_marketing_html(html_draft)
        return {"agent_label": "Marketing HTML Agent", "html": html_draft, "execution_boundary": "draft HTML only; no external publishing action was performed."}
    raise ValueError(f"허용되지 않은 Food Tool입니다: {name}")
