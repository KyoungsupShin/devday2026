"""Local, versioned snapshot of the Harness prompt catalog and HANA overrides."""
from __future__ import annotations

import json
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]

PROMPT_DEFINITIONS = {
    "intent_router": {"file": "intent_router.md", "title": "Conversation Responder", "role": "Chat answer; reranker-failure fallback routing"},
    "deep_orchestrator": {"file": "deep_orchestrator.md", "title": "Deep Orchestrator", "role": "Routing, delegation, and final synthesis policy"},
    "researcher": {"file": "researcher.md", "title": "Researcher Agent", "role": "Evidence collection and read-only research policy"},
    "business_agent": {"file": "business_agent.md", "title": "Business Agent", "role": "Read-only Business and SCM evidence policy"},
    "app_agent": {"file": "app_agent.md", "title": "App Agent", "role": "MCP, n8n, and App Builder handoff policy"},
    "analyst_writer": {"file": "analyst_writer.md", "title": "Analyst Writer", "role": "Evidence synthesis and user response policy"},
    "app_builder_request_writer": {"file": "app_builder_request_writer.md", "title": "App Builder Request Writer", "role": "HIL additional-opinion request rewrite policy"},
}


def default_prompt(prompt_id: str) -> str:
    """Return the exact default text used by the Harness source prompt file."""
    try:
        filename = PROMPT_DEFINITIONS[prompt_id]["file"]
    except KeyError as error:
        raise KeyError(f"Unknown Harness prompt: {prompt_id}") from error
    return (HARNESS_ROOT / "prompts" / filename).read_text(encoding="utf-8").strip()


def hana_override_snapshot() -> dict:
    """Load the read-only snapshot exported from SAP_HARNESS_PROMPTS."""
    return json.loads((HARNESS_ROOT / "fixtures" / "harness_prompt_overrides.json").read_text(encoding="utf-8"))


def hana_overrides() -> dict[str, dict[str, str]]:
    return {item["id"]: item for item in hana_override_snapshot()["prompts"]}


def rerank_document(document_id: str, default: str) -> str:
    """Match Harness: a HANA override wins over the declared default document."""
    return str(hana_overrides().get(document_id, {}).get("content") or default)


def prompt_catalog() -> list[dict[str, str]]:
    """Catalog suitable for displaying in a notebook or passing to a DeepAgent adapter."""
    return [
        {"id": prompt_id, "title": definition["title"], "role": definition["role"], "content": default_prompt(prompt_id)}
        for prompt_id, definition in PROMPT_DEFINITIONS.items()
    ]
