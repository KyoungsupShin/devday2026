"""LLM-directed F&B A2A orchestration for the third lesson."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from typing import Any
from uuid import uuid4

from a2a.types import AgentCard
from lab_common.llm import chat_text
from lab_common.config import Settings, load_settings
from src.agent_clients import chat_tool_completion

from .catalog import (
    AGENT_CATALOG,
    AGENT_URLS,
    DEFAULT_REQUEST,
    EXECUTION_BOUNDARY,
    MESSAGE_MODES,
)
from .grounding import (
    MANUAL_SEARCH_TOOL_NAME,
    add_grounding_search,
    collect_grounding_context,
    grounding_audit,
    manual_search_tool,
    no_grounding_requested,
)
from .human_approval import (
    HUMAN_APPROVAL_TOOL_NAME,
    create_human_approval_draft,
    human_approval_tool,
)
from .prompts import get_prompt, render_prompt
from .transport import (
    discover_cards,
    message_to_dict,
    resolve_agent_urls,
    run_sync,
    send_task,
)


MAX_CONVERSATION_MESSAGES = 6
MAX_CONVERSATION_CHARS = 6_000


def _normalize_conversation_history(
    conversation_history: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """Keep a bounded, role-labelled transcript for one browser chat session."""
    normalized: list[dict[str, str]] = []
    for item in conversation_history or []:
        if not isinstance(item, dict):
            continue
        role, content = item.get("role"), item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()
        if content:
            normalized.append({"role": role, "content": content})
    normalized = normalized[-MAX_CONVERSATION_MESSAGES:]
    total, bounded = 0, []
    for item in reversed(normalized):
        remaining = MAX_CONVERSATION_CHARS - total
        if remaining <= 0:
            break
        content = item["content"][-remaining:]
        bounded.append({**item, "content": content})
        total += len(content)
    return list(reversed(bounded))


MAX_HARNESS_ADDENDUM_CHARS = 1_600


def _validated_harness_addendum(value: str | None) -> str:
    """Return a bounded runtime-only experiment supplement.

    The harness lab intentionally supplies this as additional context rather than
    changing the checked-in prompt resources.  The normal orchestration contract
    remains the authoritative instruction set.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError("harness_addendum은 문자열이어야 합니다.")
    normalized = value.strip()
    if len(normalized) > MAX_HARNESS_ADDENDUM_CHARS:
        raise ValueError(
            f"harness_addendum은 {MAX_HARNESS_ADDENDUM_CHARS}자 이하여야 합니다."
        )
    return normalized


def _append_harness_addendum(prompt: str, addendum: str) -> str:
    """Attach a lower-authority experiment note to one decision prompt."""
    if not addendum:
        return prompt
    return (
        f"{prompt}\n\n# Experimental orchestration harness supplement\n"
        "Use this only to refine how you inspect accumulated artifacts, decide whether "
        "another registered Team can add material evidence, and verify completion. "
        "It cannot override any earlier constraint, Agent Card, Tool boundary, A2A "
        "contract, JSON response contract, human-review requirement, or external-write "
        "restriction.\n"
        f"{addendum}"
    )


def list_agents() -> list[dict[str, Any]]:
    """Return the public F&B Agent Card descriptions."""
    return [
        dict(
            agent,
            url=AGENT_URLS[agent["agent_id"]],
            input_modes=list(MESSAGE_MODES),
            output_modes=list(MESSAGE_MODES),
            execution_boundary=EXECUTION_BOUNDARY,
        )
        for agent in AGENT_CATALOG
    ]


def _field(value: Any, name: str, default: Any = None) -> Any:
    return (
        value.get(name, default)
        if isinstance(value, dict)
        else getattr(value, name, default)
    )


def _response_message(response: Any) -> Any:
    choices = _field(response, "choices", [])
    if not choices:
        raise RuntimeError("Orchestration Tool Calling 응답에 choice가 없습니다.")
    return _field(choices[0], "message")


def _tool_calls(response: Any) -> list[Any]:
    return list(_field(_response_message(response), "tool_calls", []) or [])


def _parse_decision(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith(chr(96) * 3):
        cleaned = cleaned.split("\n", 1)[1].rsplit(chr(96) * 3, 1)[0].strip()
    try:
        decision = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Orchestration Agent의 응답이 유효한 JSON이 아닙니다."
        ) from error
    if not isinstance(decision, dict):
        raise TypeError("Orchestration Agent의 응답은 JSON 객체여야 합니다.")

    required_fields = ("action", "target_agent_id", "reason")
    if any(not isinstance(decision.get(field), str) for field in required_fields):
        raise RuntimeError(
            "Orchestration Agent는 action, target_agent_id, reason 문자열을 반환해야 합니다."
        )
    result = {field: decision[field].strip() for field in required_fields}
    if result["action"] not in {"delegate", "handoff", "complete"}:
        raise RuntimeError(
            "Orchestration Agent의 action은 delegate, handoff, complete 중 하나여야 합니다."
        )
    if result["action"] == "complete" and result["target_agent_id"] != "complete":
        raise RuntimeError(
            "Orchestration Agent는 완료 시 target_agent_id를 complete로 지정해야 합니다."
        )
    if result["action"] == "complete" and not result["reason"]:
        raise RuntimeError(
            "Orchestration Agent는 완료 시 현장 요청자에게 전달할 reason을 반환해야 합니다."
        )
    if result["action"] != "complete":
        purpose = decision.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            raise RuntimeError(
                "Orchestration Agent의 delegation에는 등록 Agent 대상과 purpose가 필요합니다."
            )
        if result["target_agent_id"] == "complete":
            raise RuntimeError(
                "Orchestration Agent의 delegation에는 등록 Agent 대상과 purpose가 필요합니다."
            )
        result["purpose"] = purpose.strip()
        task_plan = decision.get("task_plan")
        if isinstance(task_plan, dict):
            grounding_basis = task_plan.get("grounding_basis")
            summary = task_plan.get("summary")
            planned_tasks = task_plan.get("planned_tasks")
            if (
                isinstance(grounding_basis, str)
                and grounding_basis.strip()
                and isinstance(summary, str)
                and summary.strip()
                and isinstance(planned_tasks, list)
                and 1 <= len(planned_tasks) <= 3
                and all(
                    isinstance(task, str) and task.strip() for task in planned_tasks
                )
            ):
                result["task_plan"] = {
                    "grounding_basis": grounding_basis.strip(),
                    "summary": summary.strip(),
                    "planned_tasks": [task.strip() for task in planned_tasks],
                }
    elif isinstance(decision.get("purpose"), str) and decision["purpose"].strip():
        result["purpose"] = decision["purpose"].strip()
    requester_update = decision.get("requester_update")
    if isinstance(requester_update, dict):
        fields = ("status", "summary", "next_action")
        if all(
            isinstance(requester_update.get(field), str)
            and requester_update[field].strip()
            for field in fields
        ):
            result["requester_update"] = {
                field: requester_update[field].strip() for field in fields
            }
    return result


_OBSERVATION_FIELDS = (
    "completed_work",
    "new_evidence",
    "unresolved_decisions",
    "available_capabilities",
    "decision_focus",
)


def _parse_observation(raw: str) -> dict[str, Any]:
    """Validate a public ReAct-style observation, not private model reasoning."""
    cleaned = raw.strip()
    if cleaned.startswith(chr(96) * 3):
        cleaned = cleaned.split("\n", 1)[1].rsplit(chr(96) * 3, 1)[0].strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Orchestration Observation이 유효한 JSON이 아닙니다."
        ) from error
    if not isinstance(value, dict):
        raise TypeError("Orchestration Observation은 JSON 객체여야 합니다.")
    result: dict[str, Any] = {}
    for field in _OBSERVATION_FIELDS:
        entries = value.get(field)
        if not isinstance(entries, list) or any(
            not isinstance(entry, str) or not entry.strip() for entry in entries
        ):
            raise RuntimeError(
                f"Orchestration Observation의 {field}는 문자열 목록이어야 합니다."
            )
        result[field] = [entry.strip() for entry in entries]
    summary = value.get("chat_summary")
    if isinstance(summary, str) and summary.strip():
        result["chat_summary"] = summary.strip()
    return result


def _retry_decision_display_fields(
    settings: Settings,
    messages: list[dict[str, Any]],
    raw: str,
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Repair one missing display field without changing the decision record."""
    decision = _parse_decision(raw)
    requires_task_plan = decision["action"] != "complete"
    requires_requester_update = decision["action"] == "complete"
    if (not requires_task_plan or isinstance(decision.get("task_plan"), dict)) and (
        not requires_requester_update
        or isinstance(decision.get("requester_update"), dict)
    ):
        return decision
    try:
        retry = chat_tool_completion(
            settings,
            [
                *messages,
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": get_prompt("orchestration.decision_display_retry_user"),
                },
            ],
            tools,
            tool_choice="none",
        )
        retry_decision = _parse_decision(
            str(_field(_response_message(retry), "content", "") or "")
        )
    except (RuntimeError, TypeError):
        decision["display_summary_error"] = True
        return decision
    if requires_task_plan and isinstance(retry_decision.get("task_plan"), dict):
        decision["task_plan"] = retry_decision["task_plan"]
        return decision
    if requires_requester_update and isinstance(
        retry_decision.get("requester_update"), dict
    ):
        decision["requester_update"] = retry_decision["requester_update"]
        return decision
    decision["display_summary_error"] = True
    return decision


def _retry_observation_summary(
    settings: Settings, messages: list[dict[str, str]], raw: str
) -> dict[str, Any]:
    """Repair only a missing observation display summary, once."""
    observation = _parse_observation(raw)
    if isinstance(observation.get("chat_summary"), str):
        return observation
    try:
        retry_raw = chat_text(
            settings,
            [
                *messages,
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": get_prompt("orchestration.observation_retry_user"),
                },
            ],
        )
        retry_observation = _parse_observation(retry_raw)
    except (RuntimeError, TypeError):
        observation["display_summary_error"] = True
        return observation
    if isinstance(retry_observation.get("chat_summary"), str):
        observation["chat_summary"] = retry_observation["chat_summary"]
        return observation
    observation["display_summary_error"] = True
    return observation


def _retry_human_approval_summary(
    settings: Settings, draft: dict[str, Any]
) -> dict[str, Any]:
    """Create one display-only mail summary when a legacy draft lacks it."""
    if isinstance(draft.get("chat_summary"), str) and draft["chat_summary"].strip():
        return draft
    raw = chat_text(
        settings,
        [
            {
                "role": "system",
                "content": get_prompt("orchestration.decision_system"),
            },
            {
                "role": "user",
                "content": render_prompt(
                    "orchestration.human_approval_retry_user",
                    draft=json.dumps(draft, ensure_ascii=False),
                ),
            },
        ],
    )
    try:
        value = json.loads(raw.strip())
    except json.JSONDecodeError:
        value = {}
    summary = value.get("chat_summary") if isinstance(value, dict) else None
    if isinstance(summary, str) and summary.strip():
        return {**draft, "chat_summary": summary.strip()}
    return {**draft, "display_summary_error": True}


def _orchestration_observation(
    settings: Settings,
    request: str,
    artifacts: list[dict[str, Any]],
    cards: dict[str, AgentCard],
    grounding: dict[str, Any],
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate the public Observe phase before the next orchestration action."""
    available = [
        {"agent_id": agent_id, "name": card.name, "description": card.description}
        for agent_id, card in cards.items()
    ]
    prompt = render_prompt(
        "orchestration.observation_user",
        request=request,
        grounding=json.dumps(grounding, ensure_ascii=False),
        available=json.dumps(available, ensure_ascii=False),
        artifacts=json.dumps(artifacts, ensure_ascii=False),
        conversation_history=json.dumps(
            _normalize_conversation_history(conversation_history), ensure_ascii=False
        ),
    )
    messages = [
        {
            "role": "system",
            "content": get_prompt("orchestration.observation_system"),
        },
        {"role": "user", "content": prompt},
    ]
    return _retry_observation_summary(settings, messages, chat_text(settings, messages))


def _orchestrator_turn(
    settings: Settings,
    request: str,
    artifacts: list[dict[str, Any]],
    cards: dict[str, AgentCard],
    grounding: dict[str, Any] | None = None,
    on_grounding: Callable[[dict[str, Any]], None] | None = None,
    on_human_approval: Callable[[dict[str, Any]], None] | None = None,
    observation: dict[str, list[str]] | None = None,
    harness_addendum: str = "",
    grounding_overlay: str = "",
    conversation_history: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Let the model optionally search manuals before one orchestration decision."""
    available = [
        {"agent_id": agent_id, "name": card.name, "description": card.description}
        for agent_id, card in cards.items()
    ]
    grounding_context = grounding or no_grounding_requested()
    prompt = render_prompt(
        "orchestration.decision_user",
        available=json.dumps(available, ensure_ascii=False),
        observation=json.dumps(observation or {}, ensure_ascii=False),
        grounding=json.dumps(grounding_context, ensure_ascii=False),
        request=request,
        artifacts=json.dumps(artifacts, ensure_ascii=False),
        conversation_history=json.dumps(
            _normalize_conversation_history(conversation_history), ensure_ascii=False
        ),
    )
    prompt = _append_harness_addendum(prompt, harness_addendum)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": get_prompt("orchestration.decision_system"),
        },
        {"role": "user", "content": prompt},
    ]
    orchestration_tools = [manual_search_tool(), human_approval_tool()]
    response = chat_tool_completion(settings, messages, orchestration_tools)
    calls = _tool_calls(response)
    if not calls:
        raw = str(_field(_response_message(response), "content", "") or "")
        return _retry_decision_display_fields(
            settings, messages, raw, orchestration_tools
        ), grounding_context

    assistant_calls: list[dict[str, Any]] = []
    tool_messages: list[dict[str, str]] = []
    for call in calls:
        function = _field(call, "function")
        name = _field(function, "name")
        call_id = _field(call, "id")
        raw_arguments = _field(function, "arguments", "{}")
        try:
            arguments = (
                json.loads(raw_arguments)
                if isinstance(raw_arguments, str)
                else raw_arguments
            )
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "Orchestration Agent의 Grounding Tool arguments가 유효한 JSON이 아닙니다."
            ) from error
        if not isinstance(call_id, str) or not isinstance(arguments, dict):
            raise TypeError("Orchestration Agent가 허용되지 않은 Tool을 선택했습니다.")
        if name == MANUAL_SEARCH_TOOL_NAME:
            query = arguments.get("query")
            if not isinstance(query, str) or not query.strip():
                raise RuntimeError(
                    "search_manuals Tool에는 비어 있지 않은 query가 필요합니다."
                )
            query = query.strip()
            if on_grounding:
                on_grounding({"type": "grounding_started", "query": query})
            observation = collect_grounding_context(
                query, settings, runtime_overlay=grounding_overlay
            )
            grounding_context = add_grounding_search(
                grounding_context, query, observation
            )
            audit = grounding_audit(observation)
            if on_grounding:
                on_grounding(
                    {
                        "type": "grounding_context",
                        "query": query,
                        "grounding": observation,
                        "audit": audit,
                    }
                )
            tool_result: dict[str, Any] = observation
        elif name == HUMAN_APPROVAL_TOOL_NAME:
            try:
                tool_result = create_human_approval_draft(arguments)
            except ValueError as error:
                raise RuntimeError(str(error)) from error
            tool_result = _retry_human_approval_summary(settings, tool_result)
            if on_human_approval:
                on_human_approval(
                    {"type": "human_approval_requested", "draft": tool_result}
                )
        else:
            raise RuntimeError(
                "Orchestration Agent가 허용되지 않은 Tool을 선택했습니다."
            )
        assistant_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        )
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(tool_result, ensure_ascii=False),
            }
        )
    messages.extend(
        [
            {
                "role": "assistant",
                "content": _field(_response_message(response), "content", "") or "",
                "tool_calls": assistant_calls,
            },
            *tool_messages,
        ]
    )
    final_response = chat_tool_completion(
        settings,
        messages,
        orchestration_tools,
        tool_choice="none",
    )
    final_content = str(_field(_response_message(final_response), "content", "") or "")
    return _retry_decision_display_fields(
        settings, messages, final_content, orchestration_tools
    ), grounding_context


def _orchestrator_decision(
    settings: Settings,
    request: str,
    artifacts: list[dict[str, Any]],
    cards: dict[str, AgentCard],
    grounding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return only the decision for callers that do not need tool-event details."""
    return _orchestrator_turn(settings, request, artifacts, cards, grounding)[0]


async def _run_async(
    request: str,
    settings: Settings,
    urls: dict[str, str],
    emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    harness_addendum: str = "",
    grounding_overlay: str = "",
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    context_id, cards = str(uuid4()), await discover_cards(urls)
    artifacts: list[dict[str, Any]] = []
    middleware: list[dict[str, Any]] = []
    tasks: dict[str, list[dict[str, Any]]] = {}
    observations: list[dict[str, Any]] = []
    human_approvals: list[dict[str, Any]] = []
    termination: dict[str, Any] | None = None
    grounding = no_grounding_requested()
    history = _normalize_conversation_history(conversation_history)
    loop = asyncio.get_running_loop()

    def emit_grounding_event(event: dict[str, Any]) -> None:
        """Forward a tool event from the LLM worker without delaying the UI."""
        if emit:
            asyncio.run_coroutine_threadsafe(emit(event), loop).result()

    def emit_human_approval_event(event: dict[str, Any]) -> None:
        """Keep the LLM-created draft for UI review; never send it here."""
        draft = event.get("draft")
        if isinstance(draft, dict):
            human_approvals.append(draft)
        if emit:
            asyncio.run_coroutine_threadsafe(emit(event), loop).result()

    if emit:
        await emit(
            {
                "type": "field_handoff_received",
                "handoff": {
                    "source_agent_id": "field-agent",
                    "target_agent_id": "orchestration-agent",
                    "purpose": "field_incident_handoff",
                    "request": request,
                },
            }
        )
    for step in range(8):
        if emit:
            await emit(
                {
                    "type": "orchestration_started",
                    "step": step + 1,
                    "phase": "observation",
                }
            )
        observation = await asyncio.to_thread(
            _orchestration_observation,
            settings,
            request,
            artifacts,
            cards,
            grounding,
            history,
        )
        observation_record = {"step": step + 1, "observation": observation}
        observations.append(observation_record)
        middleware.append(
            {"name": "orchestration_observation", "data": observation_record}
        )
        if emit:
            await emit(
                {
                    "type": "orchestration_observation",
                    "step": step + 1,
                    "observation": observation,
                }
            )
        prior_search_count = len(grounding["searches"])
        if emit:
            await emit(
                {
                    "type": "orchestration_started",
                    "step": step + 1,
                    "phase": "decision",
                }
            )
        decision, grounding = await asyncio.to_thread(
            _orchestrator_turn,
            settings,
            request,
            artifacts,
            cards,
            grounding,
            emit_grounding_event,
            emit_human_approval_event,
            observation,
            harness_addendum,
            grounding_overlay,
            history,
        )
        for search in grounding["searches"][prior_search_count:]:
            observation = search["result"]
            middleware.append(
                {
                    "name": "grounding_context_collected",
                    "data": grounding_audit(observation),
                }
            )
        if emit:
            await emit(
                {
                    "type": "orchestration_decision",
                    "step": step + 1,
                    "decision": decision,
                }
            )
        target = decision["target_agent_id"]
        if target == "complete":
            termination = {
                "state": (
                    "awaiting_human_approval" if human_approvals else "completed"
                ),
                "decision": decision,
            }
            if emit:
                await emit(
                    {
                        "type": "field_response_delivered",
                        "source": "orchestration-agent",
                        "target": "field-agent",
                        "message": decision.get("requester_update", {}),
                    }
                )
            break
        if target not in cards:
            raise RuntimeError(
                f"Orchestration Agent가 등록되지 않은 A2A 대상({target})을 선택했습니다."
            )
        envelope = {
            "target_agent_id": target,
            "purpose": decision["purpose"],
            "artifact_count": len(artifacts),
        }
        middleware.append({"name": "handoff_envelope_created", "data": envelope})
        if emit:
            await emit(
                {
                    "type": "middleware",
                    "name": "handoff_envelope_created",
                    "data": envelope,
                }
            )
            await emit(
                {
                    "type": "team_handoff_started",
                    "step": step + 1,
                    "agent_id": target,
                }
            )

        async def task_update(view: dict[str, Any], agent_id: str = target) -> None:
            if emit:
                await emit({"type": "a2a_task_update", "agent_id": agent_id, **view})

        artifact, task = await send_task(
            cards[target],
            context_id=context_id,
            target_agent_id=target,
            purpose=decision["purpose"],
            payload={
                "request": request,
                "conversation_history": history,
                "grounding": grounding,
                "artifacts": artifacts,
                "orchestration_observations": observations,
                "human_approvals": human_approvals,
                # A human-approved Harness Labs revision is carried to the
                # selected Team as contextual guidance; it never changes the
                # registered Agent Card or Tool allow-list.
                "harness_overlay": harness_addendum,
            },
            on_update=task_update,
        )
        tasks.setdefault(target, []).append(task)
        record = {
            "step": step + 1,
            "orchestration": decision,
            "producer": target,
            "artifact": artifact,
        }
        artifacts.append(record)
        middleware.append(
            {
                "name": "artifact_received",
                "data": {"producer": target, "step": step + 1},
            }
        )
        if emit:
            await emit({"type": "artifact_received", "record": record})
            await emit(
                {
                    "type": "middleware",
                    "name": "artifact_received",
                    "data": {"producer": target, "step": step + 1},
                }
            )
    else:
        termination = {
            "state": "max_steps_reached",
            "message": "LLM orchestration이 최대 단계에 도달했습니다.",
        }
    return {
        "context_id": context_id,
        "request": request,
        "conversation_history": history,
        "grounding": grounding,
        "tasks": tasks,
        "artifacts": artifacts,
        "observations": observations,
        "human_approvals": human_approvals,
        "middleware": middleware,
        "termination": termination,
        "agent_cards": {
            agent_id: message_to_dict(card) for agent_id, card in cards.items()
        },
        "execution_boundary": EXECUTION_BOUNDARY,
    }


def run_handoff(
    request: str = DEFAULT_REQUEST,
    settings: Settings | None = None,
    agent_urls: dict[str, str] | None = None,
    harness_addendum: str | None = None,
    grounding_overlay: str | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request는 비어 있지 않은 문자열이어야 합니다.")
    return run_sync(
        _run_async(
            request.strip(),
            settings or load_settings(),
            resolve_agent_urls(agent_urls),
            None,
            _validated_harness_addendum(harness_addendum),
            grounding_overlay or "",
            conversation_history,
        )
    )


def run_handoff_stream(
    request: str = DEFAULT_REQUEST,
    settings: Settings | None = None,
    agent_urls: dict[str, str] | None = None,
    harness_addendum: str | None = None,
    grounding_overlay: str | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request는 비어 있지 않은 문자열이어야 합니다.")
    urls, events = resolve_agent_urls(agent_urls), Queue()
    addendum = _validated_harness_addendum(harness_addendum)

    async def emit(event: dict[str, Any]) -> None:
        events.put(event)

    def execute() -> dict[str, Any]:
        return run_sync(
            _run_async(
                request.strip(), settings or load_settings(), urls, emit, addendum,
                grounding_overlay or "", conversation_history,
            )
        )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(execute)
        while not future.done():
            try:
                yield events.get(timeout=0.2)
            except Empty:
                continue
        while not events.empty():
            yield events.get_nowait()
        yield {"type": "complete", "result": future.result()}
