"""Search registered business Context records from a user request."""

from __future__ import annotations

import json
from typing import Any

from lab_common.config import load_settings
from lab_common.llm import chat_text

from . import snapshot_reader
from .context_records import base_response, string_argument
from ..prompts import get_prompt, render_prompt


def _selected_context_ids(query: str, rows: list[dict[str, str]]) -> tuple[list[str], str]:
    """Ask the LLM to select records; never infer a match from aliases in code."""
    candidates = [
        {
            "context_id": row.get("CONTEXT_ID", ""),
            "display_name": row.get("DISPLAY_NAME", ""),
            "aliases": [
                alias.strip()
                for alias in row.get("SEARCH_ALIASES", "").split(";")
                if alias.strip()
            ],
        }
        for row in rows
        if row.get("CONTEXT_ID")
    ]
    raw = chat_text(
        load_settings(),
        [
            {"role": "system", "content": get_prompt("business_context.selector_system")},
            {
                "role": "user",
                "content": render_prompt(
                    "business_context.selector_user",
                    request_text=query,
                    candidates=json.dumps(candidates, ensure_ascii=False),
                ),
            },
        ],
    )
    cleaned = str(raw).strip()
    fence = chr(96) * 3
    if cleaned.startswith(fence):
        cleaned = cleaned.split("\n", 1)[1].rsplit(fence, 1)[0].strip()
    try:
        selection = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise RuntimeError("Context selector가 유효한 JSON을 반환하지 않았습니다.") from error
    selected = selection.get("context_ids") if isinstance(selection, dict) else None
    reason = selection.get("reason") if isinstance(selection, dict) else None
    if (
        not isinstance(selected, list)
        or len(selected) > 3
        or any(not isinstance(context_id, str) for context_id in selected)
        or not isinstance(reason, str)
        or not reason.strip()
    ):
        raise RuntimeError("Context selector 응답 형식이 유효하지 않습니다.")
    known = {candidate["context_id"] for candidate in candidates}
    unknown = [context_id for context_id in selected if context_id not in known]
    if unknown:
        raise RuntimeError("Context selector가 등록되지 않은 Context ID를 선택했습니다.")
    return list(dict.fromkeys(selected)), reason.strip()


def search_business_context(request_text: Any) -> dict[str, Any]:
    """Return matching Context candidates; it never chooses a Team or workflow."""
    query, invalid = string_argument(request_text, name="request_text")
    if invalid:
        return {"source": "hana_csv_snapshot", "lookup": "business_context", **invalid}

    state, rows, path = snapshot_reader.read_rows("business_context")
    if state != "found":
        return base_response("business_context", state, path)

    context_ids, reason = _selected_context_ids(query, rows)
    selected_ids = set(context_ids)
    records = [row for row in rows if row.get("CONTEXT_ID") in selected_ids]

    response = base_response(
        "business_context", "found" if records else "no_match", path
    )
    response.update(
        {
            "request_text": query,
            "records": records,
            "selection_reason": reason,
            "search_boundary": (
                "LLM이 등록 Context 후보에서 선택한 검색이며 Agent 선택이나 업무 단계 판단은 수행하지 않습니다."
            ),
        }
    )
    return response
