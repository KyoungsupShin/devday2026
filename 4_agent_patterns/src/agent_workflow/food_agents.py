"""Agent catalog, LLM-authored plans, and individual Agent execution."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from lab_common.ai_core import chat_text, chat_text_stream
from lab_common.config import Settings, load_settings

from .agents.registry import EXECUTABLE_AGENT_IDS, FOOD_AGENT_BY_ID, FOOD_AGENT_DEFINITIONS


def list_food_agents() -> list[dict[str, Any]]:
    """Return the inspectable Agent catalog used by the notebook."""
    return [
        {
            "agent_id": agent.id,
            "agent_label": agent.label,
            "description": agent.description,
            "system_prompt": agent.system_prompt,
        }
        for agent in FOOD_AGENT_DEFINITIONS
    ]


def _history_text(conversation_history: list[dict[str, Any]] | None) -> str:
    turns = [
        f"{item['role']}: {item['content'].strip()}"
        for item in conversation_history or []
        if isinstance(item, dict)
        and item.get("role") in {"user", "assistant"}
        and isinstance(item.get("content"), str)
        and item["content"].strip()
    ]
    return "\n".join(turns[-6:])


def plan_work_agents(
    request: str,
    settings: Settings | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ask the Orchestrator to author the complete execution plan."""
    active_settings = settings or load_settings()
    orchestrator = FOOD_AGENT_BY_ID["work-planning"]
    catalog = [
        {"agent_id": agent.id, "label": agent.label, "description": agent.description}
        for agent in FOOD_AGENT_DEFINITIONS
        if agent.id in EXECUTABLE_AGENT_IDS
    ]
    contract = (
        'Return JSON only: {"brief":"Korean text","stages":[{"agent_ids":["agent-id"],"objective":"Korean text"}],"final_agent_id":"agent-id"}. '
        "Select only necessary Agents. Stages are ordered; Agents in a stage may use only the shared brief and prior-stage answers. "
        "final_agent_id must occur exactly once in the final stage."
    )
    history = _history_text(conversation_history)
    prompt = f"현재 사용자 요청: {request}\n전문 Agent 목록: {json.dumps(catalog, ensure_ascii=False)}"
    if history:
        prompt += f"\n최근 대화: {history}"
    raw = chat_text(
        active_settings,
        [
            {"role": "system", "content": f"{orchestrator.system_prompt}\n\n{contract}"},
            {"role": "user", "content": prompt},
        ],
    )
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("Orchestrator가 유효한 JSON 실행 계획을 반환하지 않았습니다.") from error
    if not isinstance(plan, dict) or not isinstance(plan.get("brief"), str):
        raise RuntimeError("Orchestrator 실행 계획의 brief 계약이 유효하지 않습니다.")
    stages = plan.get("stages")
    if not isinstance(stages, list) or not stages:
        raise RuntimeError("Orchestrator 실행 계획에 stages가 없습니다.")

    normalized_stages: list[dict[str, Any]] = []
    selected_ids: list[str] = []
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get("objective"), str):
            raise RuntimeError("Orchestrator Agent stage 계약이 유효하지 않습니다.")
        agent_ids = stage.get("agent_ids")
        if not isinstance(agent_ids, list) or not agent_ids or any(agent_id not in EXECUTABLE_AGENT_IDS for agent_id in agent_ids):
            raise RuntimeError("Orchestrator가 허용되지 않은 Agent를 선택했습니다.")
        normalized_ids = [str(agent_id) for agent_id in agent_ids]
        selected_ids.extend(normalized_ids)
        normalized_stages.append({"agent_ids": normalized_ids, "objective": stage["objective"]})
    if len(selected_ids) != len(set(selected_ids)):
        raise RuntimeError("Orchestrator 실행 계획에 중복 Agent가 있습니다.")
    final_agent_id = plan.get("final_agent_id")
    if final_agent_id not in EXECUTABLE_AGENT_IDS or selected_ids.count(final_agent_id) != 1:
        raise RuntimeError("Orchestrator의 final_agent_id가 실행 계획과 일치하지 않습니다.")
    if final_agent_id not in normalized_stages[-1]["agent_ids"]:
        raise RuntimeError("Orchestrator의 final_agent_id는 마지막 실행 단계에 있어야 합니다.")
    return {"brief": plan["brief"], "stages": normalized_stages, "final_agent_id": final_agent_id}


def run_food_agent(
    agent_id: str,
    request: str,
    settings: Settings | None = None,
    on_delta: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """Run one Agent using its role prompt."""
    agent = FOOD_AGENT_BY_ID[agent_id]
    active_settings = settings or load_settings()
    messages = [
        {"role": "system", "content": agent.system_prompt},
        {"role": "user", "content": request},
    ]
    if on_delta is None:
        answer = chat_text(active_settings, messages)
    else:
        chunks: list[str] = []
        for delta in chat_text_stream(active_settings, messages):
            chunks.append(delta)
            on_delta(delta)
        answer = "".join(chunks)
    return {"agent_id": agent.id, "agent_label": agent.label, "answer": answer}
