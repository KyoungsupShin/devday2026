"""Public execution interface for local read-only A2A Tools."""

from .tool_registry import execute_tool, schemas_for_tool_ids

__all__ = ["execute_tool", "schemas_for_tool_ids"]
