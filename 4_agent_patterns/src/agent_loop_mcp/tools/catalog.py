"""Tool schemas and Agent-to-Tool assignments."""
from __future__ import annotations

from typing import Any

_TOOL_SCHEMAS: dict[str, list[dict[str, Any]]] = {
    "food-rnd": [
        {"type": "function", "function": {"name": "open_food_facts_search", "description": "Open Food Facts 공개 API에서 제품 키워드의 식품 라벨 데이터를 읽기 전용으로 조회합니다.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}}},
    ],
    "marketing": [
        {"type": "function", "function": {"name": "open_food_facts_search", "description": "Open Food Facts 공개 API에서 제품 키워드의 식품 라벨 데이터를 읽기 전용으로 조회합니다.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}}},
        {"type": "function", "function": {"name": "generate_marketing_image", "description": "Marketing Image Agent에게 프로모션 HTML에 넣을 제품 이미지를 생성하도록 요청합니다. HTML 시안에 이미지를 넣어야 하면 generate_marketing_html과 함께 선택하세요.", "parameters": {"type": "object", "properties": {"product_name": {"type": "string"}, "visual_brief": {"type": "string"}}, "required": ["product_name", "visual_brief"], "additionalProperties": False}}},
        {"type": "function", "function": {"name": "generate_marketing_html", "description": "Marketing HTML Agent에게 상품의 한 장짜리 프로모션 HTML 시안 생성을 요청합니다.", "parameters": {"type": "object", "properties": {"product_name": {"type": "string"}, "positioning": {"type": "string"}, "key_messages": {"type": "array", "items": {"type": "string"}}}, "required": ["product_name", "positioning", "key_messages"], "additionalProperties": False}}},
    ],
}

_TOOL_TYPES = {
    "open_food_facts_search": "API / read-only",
    "generate_marketing_image": "Agent as a Tool",
    "generate_marketing_html": "Agent as a Tool",
}


def tools_for_food_agent(agent_id: str) -> list[dict[str, Any]]:
    return [dict(schema) for schema in _TOOL_SCHEMAS.get(agent_id, [])]


def tool_names_for_food_agent(agent_id: str) -> list[str]:
    return [schema["function"]["name"] for schema in tools_for_food_agent(agent_id)]


def tool_catalog_for_food_agent(agent_id: str) -> list[dict[str, str]]:
    return [
        {"name": schema["function"]["name"], "type": _TOOL_TYPES[schema["function"]["name"]], "description": schema["function"]["description"]}
        for schema in tools_for_food_agent(agent_id)
    ]
