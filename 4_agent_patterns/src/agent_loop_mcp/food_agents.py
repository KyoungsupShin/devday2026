"""Food-manufacturing specialist definitions and their thin LLM runner."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from lab_common.llm import chat_text, chat_text_stream
from lab_common.config import Settings, load_settings
from src.agent_clients import chat_tool_completion

from .agents.registry import (
    FOOD_AGENT_BY_ID,
    FOOD_AGENT_DEFINITIONS,
    REVISION_AGENT_IDS,
    SPECIALIST_AGENT_IDS,
    FoodAgentDefinition,
)
from .prompts import get_prompt
from .tools import (
    execute_food_tool,
    tool_catalog_for_food_agent,
    tool_names_for_food_agent,
    tools_for_food_agent,
)

TOOL_CALLING_BOUNDARY = get_prompt("tool_calling_boundary")
EVALUATION_MIDDLEWARE_PROMPT = get_prompt("evaluation_middleware")


# Tool results are fed back into the model and are also included in the public
# workflow trace. A generated marketing HTML draft can contain an inlined image
# data URL, whose base64 payload is many orders of magnitude larger than the
# useful tool observation. Keep that asset in the local preview store, but
# never put its bytes into either LLM context or the trace.
_MAX_TOOL_OBSERVATION_CHARS = 12_000


def _tool_result_summary(name: str, result: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded, model-safe observation for a tool result."""
    if name == "generate_marketing_html":
        html_draft = result.get("html", "")
        return {
            "agent_label": result.get("agent_label", "Marketing HTML Agent"),
            "html_draft_created": True,
            "html_characters": len(html_draft) if isinstance(html_draft, str) else 0,
            "embedded_image": isinstance(html_draft, str) and "data:image/" in html_draft,
            "preview": "Available only from the local marketing preview store; image bytes are excluded from the LLM context.",
            "execution_boundary": result.get("execution_boundary"),
        }
    serialized = json.dumps(result, ensure_ascii=False)
    if len(serialized) <= _MAX_TOOL_OBSERVATION_CHARS:
        return result
    return {
        "tool_result_truncated": True,
        "original_characters": len(serialized),
        "preview": serialized[:_MAX_TOOL_OBSERVATION_CHARS],
    }


def _system_prompt(agent: FoodAgentDefinition) -> str:
    assigned_tools = tool_names_for_food_agent(agent.id)
    if not assigned_tools:
        return agent.system_prompt
    return f"{agent.system_prompt}\n\n{TOOL_CALLING_BOUNDARY} Assigned tools: {', '.join(assigned_tools)}."


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _tool_calls(response: Any) -> list[Any]:
    choices = _field(response, "choices", [])
    if not choices:
        raise RuntimeError("Tool Calling 응답에 choice가 없습니다.")
    return list(_field(_field(choices[0], "message"), "tool_calls", []) or [])


def _tool_call_messages(
    response: Any,
    tool_calls: list[Any],
    request: str,
    settings: Settings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    message = _field(_field(response, "choices", [])[0], "message")
    assistant_calls: list[dict[str, Any]] = []
    tool_messages: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    tool_session: dict[str, Any] = {}
    ordered_calls = sorted(
        tool_calls,
        key=lambda call: 0 if _field(_field(call, "function"), "name") == "generate_marketing_image" else 1,
    )
    for call in ordered_calls:
        function = _field(call, "function")
        name = _field(function, "name")
        raw_arguments = _field(function, "arguments", "{}")
        call_id = _field(call, "id")
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Tool {name}의 arguments가 유효한 JSON이 아닙니다.") from error
        if not isinstance(arguments, dict) or not isinstance(name, str) or not call_id:
            raise RuntimeError("Tool Calling 응답의 함수 계약이 유효하지 않습니다.")
        result = execute_food_tool(name, arguments, request=request, settings=settings, tool_session=tool_session)
        assistant_calls.append({"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}})
        safe_result = _tool_result_summary(name, result)
        tool_messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(safe_result, ensure_ascii=False)})
        artifacts.append({"name": name, "arguments": arguments, "result": safe_result})
    assistant_message = {"role": "assistant", "content": _field(message, "content") or "", "tool_calls": assistant_calls}
    return [assistant_message, *tool_messages], artifacts


def _tool_follow_up(
    settings: Settings,
    messages: list[dict[str, Any]],
    schemas: list[dict[str, Any]],
) -> str:
    """Request the final answer on the same SAP SDK client as the tool turn.

    A ``tool`` message is valid only immediately after the assistant message that
    declared its ``tool_calls``.  Sending this transcript through a different
    client path caused that link to be dropped and Azure rejected the request.
    """
    response = chat_tool_completion(settings, messages, schemas, tool_choice="none")
    choices = _field(response, "choices", [])
    if not choices:
        raise RuntimeError("Tool Calling 후속 응답에 choice가 없습니다.")
    return str(_field(_field(choices[0], "message"), "content") or "")


def list_food_agents() -> list[dict[str, Any]]:
    """Return the public, inspectable configuration for every food specialist."""
    return [
        {
            "agent_id": agent.id,
            "agent_label": agent.label,
            "description": agent.description,
            "system_prompt": _system_prompt(agent),
            "tools": tool_catalog_for_food_agent(agent.id),
            "execution_boundary": "AI Core LLM with local read-only Tool Calling; no external write actions.",
        }
        for agent in FOOD_AGENT_DEFINITIONS
    ]


def _plan_work_agents_once(
    request: str,
    settings: Settings,
    correction_reason: str | None = None,
) -> dict[str, Any]:
    """Request and validate one LLM-authored specialist execution plan."""
    orchestrator = FOOD_AGENT_BY_ID["work-planning"]
    catalog = [
        {"agent_id": agent.id, "label": agent.label, "description": agent.description}
        for agent in FOOD_AGENT_DEFINITIONS
        if agent.id in SPECIALIST_AGENT_IDS
    ]
    contract = (
        'Return JSON only: {"brief":"Korean text","stages":[{"agent_ids":["agent-id"],"objective":"Korean text"}],"final_agent_id":"agent-id"}. '
        "Each specialist may occur once. stages are ordered; agents in one stage run in parallel. "
        "final_agent_id must appear exactly once as the only agent in its own final stage, after every other specialist stage."
    )
    correction = ""
    if correction_reason:
        correction = (
            "\n\nThe previous execution plan violated the runtime contract "
            f"({correction_reason}). Generate a new plan. In particular, place final_agent_id "
            "exactly once as the sole agent_ids value in the last stage; put every other specialist stage before it."
        )
    raw = chat_text(
        settings,
        [
            {"role": "system", "content": f"{orchestrator.system_prompt}\n\n{contract}{correction}"},
            {"role": "user", "content": f"사용자 요청: {request}\n전문 Agent 목록: {json.dumps(catalog, ensure_ascii=False)}"},
        ],
    )
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("Orchestration Agent가 유효한 JSON 실행 계획을 반환하지 않았습니다.") from error
    if not isinstance(plan, dict) or not isinstance(plan.get("brief"), str):
        raise RuntimeError("Orchestration Agent 실행 계획의 brief 계약이 유효하지 않습니다.")
    stages = plan.get("stages")
    if not isinstance(stages, list) or not stages:
        raise RuntimeError("Orchestration Agent 실행 계획에 stages가 없습니다.")
    normalized_stages: list[dict[str, Any]] = []
    selected_ids: list[str] = []
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get("objective"), str):
            raise RuntimeError("Orchestration Agent stage 계약이 유효하지 않습니다.")
        agent_ids = stage.get("agent_ids")
        if not isinstance(agent_ids, list) or not agent_ids:
            raise RuntimeError("Orchestration Agent stage의 agent_ids 계약이 유효하지 않습니다.")
        invalid_ids = [agent_id for agent_id in agent_ids if agent_id not in SPECIALIST_AGENT_IDS]
        if invalid_ids:
            raise RuntimeError(
                "Orchestration Agent가 허용되지 않은 Specialist Agent를 선택했습니다: "
                f"{invalid_ids!r}. 허용 ID: {', '.join(SPECIALIST_AGENT_IDS)}"
            )
        normalized_ids = [str(agent_id) for agent_id in agent_ids]
        selected_ids.extend(normalized_ids)
        normalized_stages.append({"agent_ids": normalized_ids, "objective": stage["objective"]})
    if len(selected_ids) != len(set(selected_ids)):
        raise RuntimeError("Orchestration Agent 실행 계획에 중복 Specialist Agent가 있습니다.")
    final_agent_id = plan.get("final_agent_id")
    if final_agent_id not in SPECIALIST_AGENT_IDS:
        raise RuntimeError("Orchestration Agent의 final_agent_id가 허용되지 않은 Specialist Agent입니다.")
    if final_agent_id not in normalized_stages[-1]["agent_ids"]:
        raise RuntimeError(
            "Orchestration Agent의 final_agent_id는 마지막 실행 단계에 있어야 합니다."
        )
    if normalized_stages[-1]["agent_ids"] != [final_agent_id]:
        raise RuntimeError(
            "Orchestration Agent의 마지막 실행 단계에는 final_agent_id만 있어야 합니다."
        )
    return {"brief": plan["brief"], "stages": normalized_stages, "final_agent_id": final_agent_id}


def plan_work_agents(request: str, settings: Settings | None = None) -> dict[str, Any]:
    """Let the Orchestrator LLM select a valid specialist execution plan.

    The runtime validates every plan and never rearranges its stages. A malformed
    LLM response gets one bounded repair attempt with the violated contract;
    a second invalid response is surfaced to the caller unchanged.
    """
    active_settings = settings or load_settings()
    correction_reason: str | None = None
    for attempt in range(2):
        try:
            return _plan_work_agents_once(request, active_settings, correction_reason)
        except RuntimeError as error:
            if attempt == 1:
                raise
            correction_reason = str(error)
    raise RuntimeError("Orchestration Agent 실행 계획을 생성하지 못했습니다.")


def evaluate_workflow_execution(
    request: str,
    plan: dict[str, Any],
    agent_results: dict[str, dict[str, Any]],
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Use an LLM middleware to approve or request a bounded rework plan.

    The middleware chooses any revision stages itself. This function only validates
    the returned contract; it does not infer missing Agents or Tools.
    """
    active_settings = settings or load_settings()
    final_agent_id = plan.get("final_agent_id")
    evidence = {
        agent_id: {
            "agent_label": result.get("agent_label"),
            "answer": result.get("answer"),
            "tool_calls": result.get("tool_calls", []),
        }
        for agent_id, result in agent_results.items()
        if agent_id in REVISION_AGENT_IDS
    }
    contract = (
        'Return JSON only: {"verdict":"pass|revise","reason":"Korean text",'
        '"revision_stages":[{"agent_ids":["agent-id"],"objective":"Korean text"}]}. '
        "For pass, revision_stages must be []. For revise, use one or more stages, each agent at most once, "
        f"and put {final_agent_id!r} exactly once in the final stage."
    )
    raw = chat_text(
        active_settings,
        [
            {"role": "system", "content": f"{EVALUATION_MIDDLEWARE_PROMPT}\n\n{contract}"},
            {
                "role": "user",
                "content": (
                    f"사용자 요청: {request}\n\nOrchestrator 실행 계획: {json.dumps(plan, ensure_ascii=False)}"
                    f"\n\n실행 증거(Agent 응답 및 Tool audit): {json.dumps(evidence, ensure_ascii=False)}"
                ),
            },
        ],
    )
    try:
        review = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("Evaluation Middleware가 유효한 JSON 평가를 반환하지 않았습니다.") from error
    if not isinstance(review, dict) or review.get("verdict") not in {"pass", "revise"} or not isinstance(review.get("reason"), str):
        raise RuntimeError("Evaluation Middleware 평가 계약이 유효하지 않습니다.")
    stages = review.get("revision_stages")
    if not isinstance(stages, list):
        raise RuntimeError("Evaluation Middleware의 revision_stages 계약이 유효하지 않습니다.")
    if review["verdict"] == "pass":
        if stages:
            raise RuntimeError("Evaluation Middleware pass 결과에는 보완 stage가 없어야 합니다.")
        return {"verdict": "pass", "reason": review["reason"], "revision_stages": []}

    normalized_stages: list[dict[str, Any]] = []
    selected_ids: list[str] = []
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get("objective"), str):
            raise RuntimeError("Evaluation Middleware 보완 stage 계약이 유효하지 않습니다.")
        agent_ids = stage.get("agent_ids")
        if not isinstance(agent_ids, list) or not agent_ids or any(agent_id not in REVISION_AGENT_IDS for agent_id in agent_ids):
            raise RuntimeError("Evaluation Middleware가 허용되지 않은 Specialist Agent를 선택했습니다.")
        normalized_ids = [str(agent_id) for agent_id in agent_ids]
        selected_ids.extend(normalized_ids)
        normalized_stages.append({"agent_ids": normalized_ids, "objective": stage["objective"]})
    if len(selected_ids) != len(set(selected_ids)):
        raise RuntimeError("Evaluation Middleware 보완 계획에 중복 Specialist Agent가 있습니다.")
    if not normalized_stages or selected_ids.count(final_agent_id) != 1 or final_agent_id not in normalized_stages[-1]["agent_ids"]:
        raise RuntimeError("Evaluation Middleware 보완 계획의 마지막 stage에는 원래 최종 Agent가 정확히 한 번 포함되어야 합니다.")
    return {"verdict": "revise", "reason": review["reason"], "revision_stages": normalized_stages}


def run_food_agent(
    agent_id: str,
    request: str,
    settings: Settings | None = None,
    on_delta: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """Run one food agent, using assigned Tool Calling functions before final synthesis when selected."""
    agent = FOOD_AGENT_BY_ID[agent_id]
    messages = [
        {"role": "system", "content": _system_prompt(agent)},
        {"role": "user", "content": request},
    ]
    active_settings = settings or load_settings()
    tool_artifacts: list[dict[str, Any]] = []
    schemas = tools_for_food_agent(agent_id)
    if schemas:
        tool_response = chat_tool_completion(active_settings, messages, schemas)
        selected_calls = _tool_calls(tool_response)
        if selected_calls:
            allowed_tools = set(tool_names_for_food_agent(agent_id))
            if any(_field(_field(call, "function"), "name") not in allowed_tools for call in selected_calls):
                raise RuntimeError(f"{agent.label}에 할당되지 않은 Tool이 선택되었습니다.")
            tool_messages, tool_artifacts = _tool_call_messages(tool_response, selected_calls, request, active_settings)
            messages.extend(tool_messages)
        else:
            answer = _field(_field(_field(tool_response, "choices", [])[0], "message"), "content") or ""
            if on_delta and answer:
                on_delta(answer)
            return {"agent_id": agent.id, "agent_label": agent.label, "answer": answer, "tool_calls": tool_artifacts}
    if tool_artifacts:
        answer = _tool_follow_up(active_settings, messages, schemas)
        if on_delta and answer:
            on_delta(answer)
    elif on_delta is None:
        answer = chat_text(active_settings, messages)
    else:
        chunks: list[str] = []
        for delta in chat_text_stream(active_settings, messages):
            chunks.append(delta)
            on_delta(delta)
        answer = "".join(chunks)
    return {"agent_id": agent.id, "agent_label": agent.label, "answer": answer, "tool_calls": tool_artifacts}
