"""Read-only local stand-in for the production MCP Registry discovery contract."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_mock_registry(path: Path | None = None) -> dict:
    registry = path or ROOT / "fixtures" / "mcp_registry.json"
    return json.loads(registry.read_text(encoding="utf-8"))


def tool_names(registry: dict | None = None) -> list[str]:
    return [tool["name"] for tool in (registry or load_mock_registry())["tools"]]

