"""Inspectable DeepAgents readiness and delegation-plan core."""
from __future__ import annotations

import importlib.util
import os
from typing import Any

from .harness_prompts import default_prompt


def deepagents_readiness() -> dict[str, object]:
    """Report optional dependencies and configuration without connecting anywhere."""
    return {
        "deepagents_installed": importlib.util.find_spec("deepagents") is not None,
        "langchain_openai_installed": importlib.util.find_spec("langchain_openai") is not None,
        "HARNESS_LLM_BASE_URL_set": bool(os.getenv("HARNESS_LLM_BASE_URL")),
        "HARNESS_LLM_API_KEY_set": bool(os.getenv("HARNESS_LLM_API_KEY")),
        "HARNESS_MODEL_set": bool(os.getenv("HARNESS_MODEL")),
        "note": "이 확인은 외부 runtime이나 MCP를 호출하지 않습니다.",
    }


def inspect_deepagents_setup(prompt_id: str) -> dict[str, object]:
    """Return the selected prompt and local readiness in a stable UI contract."""
    return {"prompt": default_prompt(prompt_id), "readiness": deepagents_readiness()}


def make_agent_plan(request: str) -> dict[str, Any]:
    """Build a no-write delegation plan from the versioned prompt catalog."""
    cleaned = request.strip()
    if not cleaned:
        raise ValueError("요청을 입력하세요.")
    return {
        "system_prompt": default_prompt("deep_orchestrator"),
        "request": cleaned,
        "delegation": ["researcher", "business_agent"],
        "final_writer": "analyst_writer",
        "write_tools": "human_approval_required",
    }


def runtime_contract() -> dict[str, object]:
    return {"optional_packages": ["deepagents", "langgraph", "langchain-openai"], "tools": ["read_only_mcp"], "write_tools": "human_approval_required"}


def connection_contract() -> dict[str, str]:
    return {"HARNESS_LLM_BASE_URL": "LiteLLM endpoint", "HARNESS_LLM_API_KEY": "secret", "HARNESS_MODEL": "deployed model", "MCP_REGISTRY": "approved tool registry"}
