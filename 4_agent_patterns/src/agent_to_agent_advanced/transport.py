"""A2A Protocol transport primitives shared by the F&B orchestration flow."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_data_part, new_text_message
from a2a.types import AgentCard, Role, SendMessageRequest
from google.protobuf.json_format import MessageToDict

from .catalog import AGENT_URLS, HANDOFF_SCHEMA_VERSION

T = TypeVar("T")


def resolve_agent_urls(overrides: dict[str, str] | None) -> dict[str, str]:
    """Validate endpoint overrides against the registered Team topology."""
    overrides = overrides or {}
    unexpected = sorted(set(overrides) - set(AGENT_URLS))
    if unexpected:
        raise ValueError(
            "등록되지 않은 F&B A2A Agent URL입니다: " + ", ".join(unexpected)
        )
    urls = {**AGENT_URLS, **overrides}
    invalid = [
        agent_id
        for agent_id, url in urls.items()
        if not isinstance(url, str) or not url.strip()
    ]
    if invalid:
        raise ValueError("F&B A2A Agent URL이 없습니다: " + ", ".join(invalid))
    return {agent_id: url.rstrip("/") for agent_id, url in urls.items()}


def message_to_dict(value: Any) -> dict[str, Any]:
    return MessageToDict(value, preserving_proto_field_name=True)


def _status_signature(task: dict[str, Any]) -> str:
    """Return the user-visible status identity, excluding transport repetition."""
    status = task.get("status", {})
    if not isinstance(status, dict):
        status = {}
    message = status.get("message", {})
    if not isinstance(message, dict):
        message = {}
    parts = message.get("parts", [])
    return json.dumps(
        {"state": status.get("state"), "parts": parts},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


async def discover_cards(urls: dict[str, str]) -> dict[str, AgentCard]:
    cards: dict[str, AgentCard] = {}
    unavailable: list[str] = []
    async with httpx.AsyncClient(timeout=8.0) as client:
        for agent_id, url in urls.items():
            try:
                cards[agent_id] = await A2ACardResolver(client, url).get_agent_card()
            except Exception:
                unavailable.append(f"{agent_id} ({url})")
    if unavailable:
        raise RuntimeError(
            "Advanced A2A Agent Card를 찾을 수 없습니다: "
            + ", ".join(unavailable)
            + ". 별도 터미널에서 `python3 4_agent_patterns/main.py "
            "fnb-a2a-advanced-local`을 시작하세요."
        )
    return cards


def artifact_data(task: Any) -> dict[str, Any]:
    for artifact in reversed(task.artifacts):
        for part in artifact.parts:
            if part.HasField("data"):
                value = message_to_dict(part.data)
                if isinstance(value, dict):
                    return value
    raise RuntimeError(f"A2A Task {task.id}가 JSON artifact를 반환하지 않았습니다.")


def task_failure_message(task: Any | None) -> str:
    """Preserve the remote Agent's failure detail instead of masking it."""
    if task is None:
        return "A2A Task가 응답을 반환하지 않았습니다."
    status = message_to_dict(task).get("status", {})
    message = status.get("message", {}) if isinstance(status, dict) else {}
    parts = message.get("parts", []) if isinstance(message, dict) else []
    details = [part["text"] for part in parts if isinstance(part.get("text"), str)]
    if details:
        return "A2A Task 실패: " + "\n".join(details)
    state = status.get("state") if isinstance(status, dict) else None
    return f"A2A Task가 정상 완료되지 않았습니다. 상태: {state or 'unknown'}"


async def send_task(
    card: AgentCard,
    *,
    context_id: str,
    target_agent_id: str,
    purpose: str,
    payload: dict[str, Any],
    on_update: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    handoff = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "handoff_id": str(uuid4()),
        "source_agent_id": "orchestration-agent",
        "target_agent_id": target_agent_id,
        "purpose": purpose,
        "input": payload,
    }
    message = new_text_message(
        "Orchestration Agent delegation",
        media_type="text/plain",
        context_id=context_id,
        role=Role.ROLE_USER,
    )
    message.parts.add().CopyFrom(new_data_part(handoff, media_type="application/json"))
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=8.0)) as client:
        a2a_client = await create_client(
            card, ClientConfig(streaming=True, httpx_client=client)
        )
        latest_task = None
        last_status_signature: str | None = None
        try:
            async for response in a2a_client.send_message(
                SendMessageRequest(message=message)
            ):
                if response.HasField("task"):
                    latest_task = response.task
                elif latest_task is not None and response.HasField("status_update"):
                    latest_task.status.CopyFrom(response.status_update.status)
                elif latest_task is not None and response.HasField("artifact_update"):
                    latest_task.artifacts.add().CopyFrom(
                        response.artifact_update.artifact
                    )
                if latest_task is not None and on_update:
                    task_view = message_to_dict(latest_task)
                    status_signature = _status_signature(task_view)
                    if status_signature != last_status_signature:
                        last_status_signature = status_signature
                        await on_update({"task": task_view, "handoff": handoff})
        finally:
            await a2a_client.close()
    if (
        latest_task is None
        or message_to_dict(latest_task).get("status", {}).get("state")
        != "TASK_STATE_COMPLETED"
    ):
        raise RuntimeError(task_failure_message(latest_task))
    return artifact_data(latest_task), message_to_dict(latest_task)


def run_sync(awaitable: Awaitable[T]) -> T:
    """Run an async API from both plain Python and an active notebook loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(awaitable)).result()
