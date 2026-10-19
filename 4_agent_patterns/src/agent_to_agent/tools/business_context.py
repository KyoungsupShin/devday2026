"""Search registered business Context records from a user request."""

from __future__ import annotations

from typing import Any

from . import snapshot_reader
from .context_records import base_response, string_argument


def search_business_context(request_text: Any) -> dict[str, Any]:
    """Return matching Context candidates; it never chooses a Team or workflow."""
    query, invalid = string_argument(request_text, name="request_text")
    if invalid:
        return {"source": "hana_csv_snapshot", "lookup": "business_context", **invalid}

    state, rows, path = snapshot_reader.read_rows("business_context")
    if state != "found":
        return base_response("business_context", state, path)

    query_folded = query.casefold()
    records: list[dict[str, str]] = []
    matches: dict[str, list[str]] = {}
    for row in rows:
        aliases = [
            row.get("DISPLAY_NAME", ""),
            *row.get("SEARCH_ALIASES", "").split(";"),
        ]
        matched = [
            alias.strip()
            for alias in aliases
            if alias.strip() and alias.strip().casefold() in query_folded
        ]
        if matched:
            records.append(row)
            matches[row.get("CONTEXT_ID", "")] = matched

    response = base_response(
        "business_context", "found" if records else "no_match", path
    )
    response.update(
        {
            "request_text": query,
            "records": records,
            "matched_aliases": matches,
            "search_boundary": (
                "표시명·별칭을 이용한 Context 검색이며 Agent 선택이나 업무 단계 판단은 수행하지 않습니다."
            ),
        }
    )
    return response
