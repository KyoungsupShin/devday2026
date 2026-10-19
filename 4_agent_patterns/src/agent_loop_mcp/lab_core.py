"""Core workflow for ``02_agent_loop_mcp.ipynb``.

This module deliberately does not create another planner loop. The existing
dependency graph is the runtime; each specialist can select its assigned,
read-only tools while it works. The public functions keep the lesson-facing
``02_agent_loop_mcp`` API small and JSON-friendly.
"""
from __future__ import annotations

from typing import Any

from lab_common.config import Settings

from ..agent_workflow.food_agents import list_food_agents
from ..agent_workflow.lab_core import run_workflow


def list_food_mcp_tools() -> list[dict[str, Any]]:
    """List Tool Calling contracts assigned within the existing graph.

    ``MCP`` remains in this lesson's historical filename, but these are local
    OpenAI-compatible Tool Calling functions, not a separately launched MCP
    server. All current contracts are read-only.
    """
    catalog: list[dict[str, Any]] = []
    for agent in list_food_agents():
        for tool in agent["tools"]:
            catalog.append(
                {
                    "agent_id": agent["agent_id"],
                    "agent_label": agent["agent_label"],
                    "name": tool["name"],
                    "type": tool["type"],
                    "description": tool["description"],
                    "write": False,
                }
            )
    return catalog


def run_food_mcp_loop(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
) -> dict[str, Any]:
    """Run the LLM-orchestrated graph and expose selected specialist Tool Calls.

    The name is retained for the notebook's public API. No separate MCP server
    or JSON planning loop is introduced; the graph continues to run through
    ``run_workflow`` and its normal Cohere Chat/Work route.
    """
    outcome = run_workflow(request, settings, min_margin=min_margin)
    selected_tools: list[dict[str, Any]] = []
    for agent_id, result in outcome.get("agent_results", {}).items():
        for call in result.get("tool_calls", []):
            selected_tools.append({"agent_id": agent_id, **call})
    return {
        **outcome,
        "tool_calls": selected_tools,
        "execution_boundary": "local read-only Tool Calling inside the existing Agent graph; no external write actions are available.",
    }
