"""LLM-selected internal delegation for F&B Team A2A servers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from a2a.helpers import (
    new_data_part,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    Role,
    TaskState,
)
from google.protobuf.json_format import MessageToDict
from lab_common.llm import chat_text
from lab_common.config import Settings, load_settings
from src.agent_clients import chat_tool_completion

from .catalog import AGENT_CATALOG, HANDOFF_SCHEMA_VERSION, SUBAGENT_BY_LABEL
from .prompts import get_optional_prompt, get_prompt, render_prompt
from .tools import execute_tool, schemas_for_tool_ids

_MAX_READ_ONLY_TOOL_TURNS = 3


def _spec(agent_id: str) -> dict[str, Any]:
    try:
        return next(item for item in AGENT_CATALOG if item["agent_id"] == agent_id)
    except StopIteration as error:
        raise ValueError(f"알 수 없는 F&B A2A Agent: {agent_id}") from error


def _payload(context: RequestContext, agent_id: str) -> dict[str, Any]:
    if context.message is None:
        raise ValueError("A2A Message가 없습니다.")
    for part in context.message.parts:
        if part.HasField("data"):
            handoff = MessageToDict(part.data, preserving_proto_field_name=True)
            if (
                handoff.get("schema_version") == HANDOFF_SCHEMA_VERSION
                and handoff.get("target_agent_id") == agent_id
            ):
                value = handoff.get("input")
                if isinstance(value, dict):
                    return value
    raise ValueError("현재 팀을 대상으로 한 JSON DataPart가 필요합니다.")


def _role_prompt(team: dict[str, Any], subagent: str | None) -> str:
    """Compose one execution role from common and role-specific TOML resources."""
    if subagent is None:
        return render_prompt(
            "team.template",
            perspective=get_prompt(str(team["role_prompt_key"])),
        )
    subagent_spec = SUBAGENT_BY_LABEL.get(subagent)
    if subagent_spec is None:
        raise ValueError(f"알 수 없는 F&B Sub-agent: {subagent}")
    return render_prompt(
        "subagent.template",
        perspective=get_prompt(str(subagent_spec["role_prompt_key"])),
    )


def _tool_guidance(tool_schemas: list[dict[str, Any]]) -> str:
    """Attach optional interpretation guidance for Tools available to this role."""
    guidance: list[str] = []
    for schema in tool_schemas:
        function = schema.get("function")
        name = function.get("name") if isinstance(function, dict) else None
        if not isinstance(name, str):
            continue
        value = get_optional_prompt(f"tools.{name}.guidance")
        if value is not None:
            guidance.append(value)
    return "\n\n".join(guidance)


def _tool_schemas_for_subagent(subagent: str | None) -> list[dict[str, Any]]:
    """Resolve Catalog-declared Tool capabilities for one delegated role."""
    if subagent is None:
        return []
    subagent_spec = SUBAGENT_BY_LABEL.get(subagent)
    if subagent_spec is None:
        raise ValueError(f"알 수 없는 F&B Sub-agent: {subagent}")
    tool_ids = subagent_spec.get("tool_ids")
    if not isinstance(tool_ids, tuple):
        raise TypeError(f"{subagent}의 Tool 권한이 등록되지 않았습니다.")
    return schemas_for_tool_ids(tool_ids)


def _json_object(
    settings: Settings,
    team: dict[str, Any],
    role: str,
    context: dict[str, Any],
    contract: str,
    subagent: str | None = None,
    require_chat_summary: bool = False,
) -> dict[str, Any]:
    tool_schemas = _tool_schemas_for_subagent(subagent)
    tool_instruction = ""
    if tool_schemas:
        tool_names = ", ".join(
            str(schema["function"]["name"]) for schema in tool_schemas
        )
        tool_instruction = render_prompt(
            "executor.tool_instruction", tool_names=tool_names
        )
        if guidance := _tool_guidance(tool_schemas):
            tool_instruction = f"{tool_instruction}\n\n{guidance}"
    prompt = render_prompt(
        "executor.review_user",
        role_prompt=_role_prompt(team, subagent),
        role=role,
        tool_instruction=tool_instruction,
        decision_record=get_prompt("executor.decision_record"),
        contract=contract,
        context=json.dumps(context, ensure_ascii=False),
    )
    messages = [
        {
            "role": "system",
            "content": get_prompt("executor.json_system"),
        },
        {"role": "user", "content": prompt},
    ]
    tool_audit: list[dict[str, Any]] = []
    if tool_schemas:
        # This is a protocol-level evidence turn, not a business route. After the
        # LLM has selected a data-capable Sub-agent, it selects the actual scoped
        # Tool, arguments, and conclusion. Requiring one native observation keeps
        # that selected perspective from replacing available evidence with a
        # hypothetical "input needed" answer.
        response = chat_tool_completion(
            settings,
            messages,
            tool_schemas,
            tool_choice="required",
        )
        for turn in range(_MAX_READ_ONLY_TOOL_TURNS):
            calls = _tool_calls(response)
            if not calls:
                break
            messages.extend(
                _tool_call_messages(response, calls, tool_schemas, tool_audit)
            )
            response = chat_tool_completion(
                settings,
                messages,
                tool_schemas,
                tool_choice=(
                    "none" if turn == _MAX_READ_ONLY_TOOL_TURNS - 1 else "auto"
                ),
            )
        raw = _response_content(response)
    else:
        raw = chat_text(settings, messages)

    def parse(raw_response: str) -> dict[str, Any]:
        cleaned = raw_response.strip()
        if cleaned.startswith(chr(96) * 3):
            cleaned = cleaned.split("\n", 1)[1].rsplit(chr(96) * 3, 1)[0].strip()
        result = json.loads(cleaned)
        if not isinstance(result, dict):
            raise TypeError(f"{role}의 LLM 응답은 JSON 객체여야 합니다.")
        return result

    try:
        result = parse(raw)
        if require_chat_summary and not (
            isinstance(result.get("chat_summary"), str)
            and result["chat_summary"].strip()
        ):
            retry_messages = [
                *messages,
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": get_prompt("executor.display_retry_user"),
                },
            ]
            try:
                retry_raw = (
                    _response_content(
                        chat_tool_completion(
                            settings,
                            retry_messages,
                            tool_schemas,
                            tool_choice="none",
                        )
                    )
                    if tool_schemas
                    else chat_text(settings, retry_messages)
                )
                retry_result = parse(retry_raw)
            except (json.JSONDecodeError, TypeError):
                result["display_summary_error"] = True
            else:
                if (
                    isinstance(retry_result.get("chat_summary"), str)
                    and retry_result["chat_summary"].strip()
                ):
                    result["chat_summary"] = retry_result["chat_summary"].strip()
                else:
                    result["display_summary_error"] = True
        if tool_audit:
            result["tool_calls"] = tool_audit
        return result
    except (json.JSONDecodeError, TypeError) as error:
        # A malformed model response must fail visibly. Retrying with a new prompt
        # changes the LLM-driven flow and would act as a fallback decision path.
        raise RuntimeError(
            f"{role}의 LLM 응답이 유효한 JSON 객체가 아닙니다."
        ) from error


def _field(value: Any, name: str, default: Any = None) -> Any:
    return (
        value.get(name, default)
        if isinstance(value, dict)
        else getattr(value, name, default)
    )


def _response_message(response: Any) -> Any:
    choices = _field(response, "choices", [])
    if not choices:
        raise RuntimeError("Tool Calling 응답에 choice가 없습니다.")
    return _field(choices[0], "message")


def _response_content(response: Any) -> str:
    return str(_field(_response_message(response), "content", "") or "")


def _tool_calls(response: Any) -> list[Any]:
    return list(_field(_response_message(response), "tool_calls", []) or [])


def _tool_call_messages(
    response: Any,
    calls: list[Any],
    schemas: list[dict[str, Any]],
    audit: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the required assistant-tool transcript for one local read-only turn."""
    allowed = {str(schema["function"]["name"]) for schema in schemas}
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
                f"로컬 CSV Tool {name}의 arguments가 유효한 JSON이 아닙니다."
            ) from error
        if (
            not isinstance(name, str)
            or name not in allowed
            or not isinstance(call_id, str)
            or not isinstance(arguments, dict)
        ):
            raise RuntimeError(
                "Sub-agent가 허용되지 않은 로컬 CSV Tool을 선택했습니다."
            )
        observation = _execute_role_tool(name, arguments)
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
                "content": json.dumps(observation, ensure_ascii=False),
            }
        )
        audit.append({"name": name, "arguments": arguments, "result": observation})
    return [
        {
            "role": "assistant",
            "content": _field(_response_message(response), "content", "") or "",
            "tool_calls": assistant_calls,
        },
        *tool_messages,
    ]


def _execute_role_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return execute_tool(name, arguments)


def _status_event(kind: str, **data: Any) -> str:
    return json.dumps(
        {"event": kind, **data}, ensure_ascii=False, separators=(",", ":")
    )


def _available_subagents(team_id: str) -> list[dict[str, str]]:
    return [
        {"agent": item["label"], "responsibility": item["responsibility"]}
        for item in SUBAGENT_BY_LABEL.values()
        if item["team_agent_id"] == team_id
    ]


def _valid_delegations(
    plan: dict[str, Any], available_subagents: list[dict[str, str]]
) -> list[dict[str, Any]] | None:
    """Return a contract-valid LLM delegation plan, without choosing agents in code."""
    selected = plan.get("delegations")
    known = {item["agent"] for item in available_subagents}
    if (
        not isinstance(selected, list)
        or not selected
        or any(
            not isinstance(item, dict)
            or item.get("agent") not in known
            or not isinstance(item.get("goal"), str)
            or not item["goal"].strip()
            for item in selected
        )
    ):
        return None
    return selected


def _plan_delegations(
    settings: Settings,
    team: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Ask the Team Agent for its delegation plan without code-side recovery."""
    available_subagents = _available_subagents(team["agent_id"])
    planning_context = {
        "request": payload.get("request"),
        "grounding": payload.get("grounding"),
        "artifacts": payload.get("artifacts", []),
        "orchestration_observations": payload.get("orchestration_observations", []),
        "available_subagents": available_subagents,
    }
    contract = get_prompt("executor.delegation_contract")
    plan = _json_object(
        settings,
        team,
        f"{team['agent_label']} delegation planner",
        planning_context,
        contract,
    )
    selected = _valid_delegations(plan, available_subagents)
    if selected is None:
        raise RuntimeError(
            "LLM delegation planner는 최소 한 명의 유효한 팀 sub-agent를 선택해야 합니다."
        )
    return plan, selected


def _verified_tool_evidence(
    delegated_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expose completed Tool observations to later Teams without interpreting them."""
    observations: list[dict[str, Any]] = []
    for finding in delegated_findings:
        artifact = finding.get("artifact")
        tool_calls = (
            artifact.get("tool_calls", []) if isinstance(artifact, dict) else []
        )
        if not isinstance(tool_calls, list):
            continue
        for call in tool_calls:
            if not isinstance(call, dict) or not isinstance(call.get("result"), dict):
                continue
            observations.append(
                {
                    "producer": finding.get("agent"),
                    "goal": finding.get("goal"),
                    "source_type": "tool_observation",
                    "tool": call.get("name"),
                    "arguments": call.get("arguments", {}),
                    "observation": call["result"],
                }
            )
    return observations


def _run_team(
    team_id: str,
    payload: dict[str, Any],
    settings: Settings,
    progress: Callable[[str, dict[str, Any]], None],
) -> dict[str, Any]:
    team = _spec(team_id)
    progress("team_started", {"team": team_id})
    progress("delegation_started", {"team": team_id})
    plan, selected = _plan_delegations(settings, team, payload)
    progress("delegation_selected", {"team": team_id, "delegations": selected})

    def run_subagent(item: dict[str, Any]) -> dict[str, Any]:
        label = item["agent"]
        progress(
            "subagent_started",
            {"team": team_id, "agent": label, "goal": item.get("goal")},
        )
        context = {
            "goal": item.get("goal"),
            "request": payload.get("request"),
            "grounding": payload.get("grounding"),
            "artifacts": payload.get("artifacts", []),
            "orchestration_observations": payload.get("orchestration_observations", []),
        }
        result = _json_object(
            settings,
            team,
            label,
            context,
            get_prompt("executor.subagent_contract"),
            label,
            require_chat_summary=True,
        )
        completed = {
            "agent": label,
            "goal": item.get("goal"),
            "artifact": result,
        }
        progress("subagent_completed", {"team": team_id, **completed})
        return completed

    with ThreadPoolExecutor(max_workers=max(1, len(selected))) as executor:
        evidence = list(executor.map(run_subagent, selected))
    verified_evidence = _verified_tool_evidence(evidence)
    progress("synthesis_started", {"team": team_id})
    synthesis = _json_object(
        settings,
        team,
        f"{team['agent_label']} synthesis agent",
        {
            "request": payload.get("request"),
            "grounding": payload.get("grounding"),
            "artifacts": payload.get("artifacts", []),
            "orchestration_observations": payload.get("orchestration_observations", []),
            "delegation_plan": plan,
            "delegated_findings": evidence,
        },
        get_prompt("executor.synthesis_contract"),
        require_chat_summary=True,
    )
    progress("synthesis_completed", {"team": team_id})
    return {
        "type": "team_analysis",
        "payload": {
            "team_agent_id": team_id,
            "delegation": selected,
            "verified_evidence": verified_evidence,
            "team_synthesis": synthesis,
        },
    }


class FnbTeamExecutor(AgentExecutor):
    def __init__(self, agent_id: str, settings: Settings | None = None) -> None:
        _spec(agent_id)
        self.agent_id, self.settings = agent_id, settings or load_settings()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task_from_user_message(context.message)
        if context.current_task is None:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(
            event_queue=event_queue, task_id=task.id, context_id=task.context_id
        )
        message = lambda text: new_text_message(
            text,
            media_type="text/plain",
            context_id=task.context_id,
            task_id=task.id,
            role=Role.ROLE_AGENT,
        )
        try:
            loop = asyncio.get_running_loop()

            def progress(kind: str, data: dict[str, Any]) -> None:
                asyncio.run_coroutine_threadsafe(
                    updater.update_status(
                        TaskState.TASK_STATE_WORKING,
                        message(_status_event(kind, **data)),
                    ),
                    loop,
                ).result()

            result = await asyncio.to_thread(
                _run_team,
                self.agent_id,
                _payload(context, self.agent_id),
                self.settings,
                progress,
            )
        except Exception as error:  # noqa: BLE001 - report every worker failure as an A2A Task failure
            await updater.failed(message(str(error)))
            return
        await updater.add_artifact(
            parts=[
                new_text_part("LLM-selected team analysis", media_type="text/plain"),
                new_data_part(result, media_type="application/json"),
            ],
            name=result["type"],
        )
        await updater.complete(
            message(_status_event("team_completed", team=self.agent_id))
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError
