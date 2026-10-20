"""Read-only Food Tool Calling functions and Agent-as-a-Tool helpers."""
from __future__ import annotations

from threading import Lock
from typing import Any

import requests
from lab_common.llm import chat_text
from src.agent_clients import generate_image_data_url

from ..prompts import get_prompt

MARKETING_IMAGE_MODEL = "gemini-3.1-flash-image"


_MARKETING_HTML_AGENT_PROMPT = get_prompt("marketing_html_agent")

_LATEST_MARKETING_HTML: dict[str, str] | None = None
_MARKETING_HTML_LOCK = Lock()
_MARKETING_IMAGE_ASSETS: dict[str, str] = {}


def latest_marketing_html_draft() -> dict[str, str] | None:
    """Return the latest HTML draft created in this Python process, if any."""
    with _MARKETING_HTML_LOCK:
        return dict(_LATEST_MARKETING_HTML) if _LATEST_MARKETING_HTML else None


def _remember_marketing_html(html_draft: str) -> None:
    global _LATEST_MARKETING_HTML
    with _MARKETING_HTML_LOCK:
        _LATEST_MARKETING_HTML = {"agent_label": "Marketing HTML Agent", "html": html_draft}


def marketing_image_asset(asset_id: str) -> str | None:
    """Return a same-process image data URL for UI preview only."""
    with _MARKETING_HTML_LOCK:
        return _MARKETING_IMAGE_ASSETS.get(asset_id)


def _insert_marketing_image(html_draft: str, image_data_url: str) -> str:
    image_tag = f'<img src="{image_data_url}" alt="AI 생성 프로모션 이미지" style="display:block;width:100%;max-height:260px;object-fit:cover;border-radius:12px;margin:0 0 14px">'
    if "</body>" in html_draft:
        return html_draft.replace("</body>", f"{image_tag}</body>", 1)
    if "</section>" in html_draft:
        return html_draft.replace("</section>", f"{image_tag}</section>", 1)
    return f"{image_tag}{html_draft}"


def execute_food_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    request: str = "",
    settings: Any = None,
    tool_session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a local read-only specialist aid; it never performs external writes."""
    if name == "open_food_facts_search":
        response = requests.get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={"search_terms": arguments["query"], "search_simple": 1, "action": "process", "json": 1, "page_size": 3},
            timeout=15,
        )
        response.raise_for_status()
        products = response.json().get("products", [])
        return {"source": "Open Food Facts public API", "query": arguments["query"], "products": [{"name": product.get("product_name"), "nutrition_grade": product.get("nutrition_grades"), "nutriments": product.get("nutriments", {})} for product in products]}
    if name == "generate_marketing_image":
        if settings is None:
            raise ValueError("Agent as a Tool 실행에는 AI Core settings가 필요합니다.")
        image_prompt = (
            "Use case: ads-marketing\n"
            "Asset type: convenience-store food promotion HTML hero image\n"
            f"Primary request: {arguments['visual_brief']}\n"
            f"Subject: {arguments['product_name']}\n"
            "Constraints: appetizing packaged meal, no logo, no text, no watermark, no people."
        )
        image_data_url = generate_image_data_url(settings, image_prompt, MARKETING_IMAGE_MODEL)
        asset_id = f"marketing-image-{len(_MARKETING_IMAGE_ASSETS) + 1}"
        with _MARKETING_HTML_LOCK:
            _MARKETING_IMAGE_ASSETS[asset_id] = image_data_url
        if tool_session is not None:
            tool_session["marketing_image_data_url"] = image_data_url
            tool_session["marketing_image_asset_id"] = asset_id
        return {"agent_label": "Marketing Image Agent", "asset_id": asset_id, "model": MARKETING_IMAGE_MODEL, "execution_boundary": "generated local preview asset only; no external publishing action was performed."}
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
        if tool_session and tool_session.get("marketing_image_data_url"):
            html_draft = _insert_marketing_image(html_draft, tool_session["marketing_image_data_url"])
        _remember_marketing_html(html_draft)
        return {"agent_label": "Marketing HTML Agent", "html": html_draft, "execution_boundary": "draft HTML only; no external publishing action was performed."}
    raise ValueError(f"허용되지 않은 Food Tool입니다: {name}")
