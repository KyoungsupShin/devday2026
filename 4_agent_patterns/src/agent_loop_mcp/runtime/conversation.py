"""Conversation observation and bounded context construction."""
from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from lab_common.llm import chat_text
from lab_common.config import Settings, load_settings

from ..prompts import get_prompt


class ConversationObservation(TypedDict):
    """The only conversation state that may reach routing or Agents."""

    use_history: bool
    observation: str
    external_data_needed: bool
    needs_work: bool


_CONVERSATION_OBSERVER_PROMPT = get_prompt("conversation_observer")
_IMAGE_DATA_URL_PATTERN = re.compile(r"data:image/[^;\s]+;base64,[A-Za-z0-9+/=]+")


def _empty_observation() -> ConversationObservation:
    return {
        "use_history": False,
        "observation": "",
        "external_data_needed": False,
        "needs_work": False,
    }


def observe_conversation_context(
    request: str,
    conversation_history: list[dict[str, Any]] | None = None,
    marketing_html_draft: str | None = None,
    settings: Settings | None = None,
) -> ConversationObservation:
    """Return compact relevant context; never forward a raw transcript."""
    turns: list[str] = []
    for item in (conversation_history or [])[-6:]:
        if not isinstance(item, dict):
            continue
        role, content = item.get("role"), item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        speaker = "사용자" if role == "user" else "AI"
        turns.append(f"{speaker}: {content.strip()}")
    has_draft = isinstance(marketing_html_draft, str) and bool(marketing_html_draft.strip())
    if not turns and not has_draft:
        return _empty_observation()

    source = "\n".join(turns) if turns else "(최근 대화 없음)"
    active_settings = settings or load_settings()
    try:
        raw = chat_text(
            active_settings,
            [
                {"role": "system", "content": _CONVERSATION_OBSERVER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"현재 사용자 요청: {request}\n\n최근 대화:\n{source}"
                        f"\n\nMarketing HTML 초안 존재: {'예' if has_draft else '아니오'}"
                    ),
                },
            ],
        )
        parsed = json.loads(raw)
    except (RuntimeError, ValueError, TypeError, json.JSONDecodeError):
        return _empty_observation()
    if not isinstance(parsed, dict) or not isinstance(parsed.get("use_history"), bool):
        return _empty_observation()

    observed_facts = parsed.get("observation", "")
    return {
        "use_history": parsed["use_history"],
        "observation": observed_facts.strip()[:600] if isinstance(observed_facts, str) else "",
        "external_data_needed": parsed.get("external_data_needed") is True,
        "needs_work": parsed.get("needs_work") is True,
    }


def build_observed_request(
    request: str,
    observation: ConversationObservation | dict[str, Any],
    marketing_html_draft: str | None = None,
) -> str:
    """Build bounded Agent context from an observation, never raw chat history."""
    if not observation.get("use_history"):
        return request
    sections: list[str] = []
    observed_facts = observation.get("observation")
    if isinstance(observed_facts, str) and observed_facts.strip():
        sections.append("[대화 관찰 — 현재 요청에 관련된 이전 사실만 사용]\n" + observed_facts.strip())
    if isinstance(marketing_html_draft, str) and marketing_html_draft.strip():
        safe_draft = _IMAGE_DATA_URL_PATTERN.sub("[이전 생성 이미지 asset]", marketing_html_draft.strip())
        sections.append("[현재 Marketing HTML 초안]\n" + safe_draft)
    return "\n\n".join(sections + [f"[현재 사용자 요청]\n{request}"])
