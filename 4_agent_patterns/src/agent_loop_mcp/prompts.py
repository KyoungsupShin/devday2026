"""Load versioned Agent Workflow prompts from the local TOML catalog."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import tomllib
from typing import Any


_PROMPT_FILE = Path(__file__).with_name("prompts") / "agent_loop_mcp.toml"


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    with _PROMPT_FILE.open("rb") as handle:
        return tomllib.load(handle)


def get_prompt(name: str) -> str:
    """Return one named system prompt."""
    value = _catalog().get("prompts", {}).get(name)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Prompt catalog에 유효한 prompts.{name} 항목이 없습니다.")
    return value


def agent_prompt(agent_id: str) -> str:
    """Return the base system prompt for a registered Agent."""
    value = _catalog().get("agents", {}).get(agent_id, {}).get("system_prompt")
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Prompt catalog에 유효한 agents.{agent_id}.system_prompt 항목이 없습니다.")
    return value


def routing_candidate(candidate_id: str) -> dict[str, str]:
    """Return label and description for one Cohere routing candidate."""
    value = _catalog().get("routing", {}).get(candidate_id)
    if not isinstance(value, dict) or not all(isinstance(value.get(key), str) and value[key].strip() for key in ("label", "description")):
        raise RuntimeError(f"Prompt catalog에 유효한 routing.{candidate_id} 항목이 없습니다.")
    return {"label": value["label"], "description": value["description"]}
