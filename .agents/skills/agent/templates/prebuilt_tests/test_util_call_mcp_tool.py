"""Tests for call_mcp_tool in util.py."""
# pyright: reportMissingImports=false

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.structure

TOOL_NAME = "count_a_costcenter_2_for_sap_self"
TOOL_URL = "https://eu12.access.sapdas.cloud.sap/v1/mcp/customer.build:apiResource:cost-center-ai-agent-7e036.sap-s4-ce-costcenter-0001-mcp-server:v1/731482421"
MCP_401_TEXT = (
    "MCP Builder destination request failed. Status code: 401. "
    'Response: {"body":{"value":null},'
    '"headers":{"content-type":"text/html; charset=utf-8","content-length":6356},'
    '"statusCode":401}'
)


def _make_tool(name=TOOL_NAME):
    tool = MagicMock()
    tool.name = name
    return tool


def _make_client(result=None, side_effect=None):
    client = MagicMock()
    client.call_mcp_tool = AsyncMock(return_value=result, side_effect=side_effect)
    return client


def _make_401_exception_group():
    """Exact structure produced by anyio task group teardown wrapping AgentGatewayServerError."""
    from sap_cloud_sdk.agentgateway.exceptions import AgentGatewayServerError
    agw_error = AgentGatewayServerError(
        f"Tool '{TOOL_NAME}' on '{TOOL_URL}' returned an error: {MCP_401_TEXT}"
    )
    return ExceptionGroup("unhandled errors in a TaskGroup", [
        ExceptionGroup("unhandled errors in a TaskGroup", [agw_error])
    ])


class TestCallMcpTool:
    @pytest.mark.asyncio
    async def test_401_error_propagated_to_llm(self, add_agent_to_path):
        """The exact 401 error from production logs reaches the LLM as a readable ToolException."""
        from langchain_core.tools import ToolException
        from util import call_mcp_tool

        client = _make_client(side_effect=_make_401_exception_group())
        with pytest.raises(ToolException) as exc_info:
            await call_mcp_tool(client, _make_tool())

        msg = str(exc_info.value)
        assert "401" in msg
        assert "MCP Builder destination request failed" in msg

    @pytest.mark.asyncio
    async def test_success_returns_string(self, add_agent_to_path):
        from util import call_mcp_tool
        assert await call_mcp_tool(_make_client(result="ok"), _make_tool()) == "ok"

    @pytest.mark.asyncio
    async def test_none_tool_raises_value_error(self, add_agent_to_path):
        from util import call_mcp_tool
        with pytest.raises(ValueError):
            await call_mcp_tool(_make_client(), None)

    @pytest.mark.asyncio
    async def test_none_result_raises_tool_exception(self, add_agent_to_path):
        from langchain_core.tools import ToolException
        from util import call_mcp_tool
        with pytest.raises(ToolException):
            await call_mcp_tool(_make_client(result=None), _make_tool())

    @pytest.mark.asyncio
    async def test_timeout_raises_tool_exception(self, add_agent_to_path):
        from langchain_core.tools import ToolException
        from util import call_mcp_tool

        async def slow(*args, **kwargs):
            await asyncio.sleep(9999)

        client = MagicMock()
        client.call_mcp_tool = slow
        with pytest.raises(ToolException, match="timed out"):
            await call_mcp_tool(client, _make_tool())

    @pytest.mark.asyncio
    async def test_result_is_minified_json(self, add_agent_to_path):
        import json
        from util import call_mcp_tool
        pretty = json.dumps({"a": 1}, indent=2)
        assert await call_mcp_tool(_make_client(result=pretty), _make_tool()) == '{"a":1}'

    @pytest.mark.asyncio
    async def test_result_is_truncated_when_oversized(self, add_agent_to_path):
        from util import call_mcp_tool, MCP_MAX_RESPONSE_CHARS
        big = "x" * (MCP_MAX_RESPONSE_CHARS + 1000)
        result = await call_mcp_tool(_make_client(result=big), _make_tool())
        assert result.endswith("...[truncated]")

    @pytest.mark.asyncio
    async def test_user_token_forwarded(self, add_agent_to_path):
        from util import call_mcp_tool
        client = _make_client(result="ok")
        await call_mcp_tool(client, _make_tool(), user_token="tok")
        assert client.call_mcp_tool.call_args[1].get("user_token") == "tok"

    @pytest.mark.asyncio
    async def test_no_user_token_not_forwarded(self, add_agent_to_path):
        from util import call_mcp_tool
        client = _make_client(result="ok")
        await call_mcp_tool(client, _make_tool(), user_token=None)
        assert "user_token" not in client.call_mcp_tool.call_args[1]
