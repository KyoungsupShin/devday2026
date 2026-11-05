"""Dynamic capability inventory built from existing Harness registries."""

from __future__ import annotations

from typing import Any

from .datasets import discover_csv_datasets
from .handoff import LocalCSVCapabilityAdapter


def discover_capabilities() -> list[dict[str, Any]]:
    """Read registered Work Agents and read-only F&B tools without hard coding IDs."""
    capabilities: list[dict[str, Any]] = []
    try:
        from src.custom_harness_joule_agents.registry import load_agent_registry

        for agent in load_agent_registry():
            capabilities.append({
                "kind": "agent", "id": agent.id, "label": agent.name,
                "description": agent.description, "capabilities": list(agent.skills),
                "execution": "read_only",
            })
    except Exception as error:  # Registry availability is itself an observation.
        capabilities.append({"kind": "system", "id": "work-agent-registry", "description": f"Unavailable: {error}"})

    try:
        from src.agent_to_agent.tools.tool_registry import TOOL_SCHEMAS

        for tool_id, schema in TOOL_SCHEMAS.items():
            function = schema.get("function", {})
            capabilities.append({
                "kind": "tool", "id": tool_id,
                "label": function.get("name", tool_id),
                "description": function.get("description", ""),
                "capabilities": [tool_id], "execution": "read_only",
            })
    except Exception as error:
        capabilities.append({"kind": "system", "id": "tool-registry", "description": f"Unavailable: {error}"})
    csv_operations = [
        {"kind": "capability", "id": item, "label": item,
         "description": "등록 CSV 스냅샷에서 읽기 전용으로 실행하는 분석 기능",
         "capabilities": [item], "execution": "read_only"}
        for item in sorted(LocalCSVCapabilityAdapter.supported_capabilities)
    ]
    return [*capabilities, *csv_operations, *discover_csv_datasets()]


def capability_ids(inventory: list[dict[str, Any]]) -> set[str]:
    identifiers: set[str] = set()
    for item in inventory:
        if not isinstance(item, dict):
            continue
        if item.get("id"):
            identifiers.add(str(item["id"]))
        identifiers.update(
            str(capability) for capability in item.get("capabilities", [])
            if isinstance(capability, str) and capability
        )
    return identifiers
