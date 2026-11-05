"""Built-in date/time tool for the agent template.

Provides the current UTC date and time so the agent never needs to guess or
hallucinate a date.  The tool is always available regardless of which MCP
servers are connected.
"""
from datetime import datetime, timezone

from langchain_core.tools import StructuredTool
from pydantic import BaseModel


def _get_current_datetime() -> str:
    """Return the current UTC date and time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _DateTimeInput(BaseModel):
    """No inputs required — the tool always returns the current UTC time."""


def get_datetime_tool() -> StructuredTool:
    """Return a LangChain tool that reports the current UTC date/time."""
    return StructuredTool(
        name="get_current_datetime",
        description="Returns the current date and time in UTC. Use this whenever the user asks about the current date, time, or 'today', and never guess.",
        args_schema=_DateTimeInput,
        func=_get_current_datetime,
    )
