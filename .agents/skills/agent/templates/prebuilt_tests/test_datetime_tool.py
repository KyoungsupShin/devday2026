"""Tests for datetime_tool.py — built-in UTC date/time tool."""
# pyright: reportMissingImports=false

from datetime import datetime, timezone

import pytest


@pytest.mark.structure
class TestDatetimeTool:

    def test_tool_returns_valid_utc_datetime(self, add_agent_to_path):
        from datetime_tool import get_datetime_tool
        tool = get_datetime_tool()
        before = datetime.now(tz=timezone.utc).replace(microsecond=0)
        result = tool.run({})
        after = datetime.now(tz=timezone.utc).replace(microsecond=0)
        dt = datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        assert before <= dt <= after

    def test_tool_is_registered_in_agent_executor(self, add_agent_to_path):
        from agent_executor import AgentExecutor
        executor = AgentExecutor()
        tool_names = [t.name for t in executor.skill_tools]
        assert "get_current_datetime" in tool_names
