"""Explicit LLM-to-LLM handoff for food-product launch planning."""
from __future__ import annotations

from typing import Any

from lab_common.ai_core import chat_text
from lab_common.config import Settings, load_settings


A2A_AGENT_CATALOG = (
    {
        "agent_id": "food-researcher",
        "agent_label": "Food Researcher Agent",
        "description": "요청에서 제품·시장·제약 조건의 핵심 근거와 미확인 가정을 정리합니다.",
        "system_prompt": """You are a Food Product Researcher. Analyze the user's product-launch request and prepare a compact evidence brief for another agent. Separate stated facts from assumptions and identify missing information. Do not claim external research was performed. Respond in Korean within 400 characters including spaces.""",
        "tools": [],
    },
    {
        "agent_id": "launch-advisor",
        "agent_label": "Launch Advisor Agent",
        "description": "Researcher의 handoff artifact만 바탕으로 출시 검토 방향과 다음 결정을 제안합니다.",
        "system_prompt": """You are a Food Product Launch Advisor. Consume only the declared researcher handoff artifact, then produce a compact Korean launch recommendation. Preserve stated assumptions and identify what must be validated before launch. Do not claim an external action was executed. Respond within 400 Korean characters including spaces.""",
        "tools": [],
    },
)


def list_a2a_agents() -> list[dict[str, Any]]:
    """Expose A2A agents, prompts, and tool boundaries for notebook inspection."""
    return [dict(agent, execution_boundary="AI Core LLM only; no MCP tools or external write actions.") for agent in A2A_AGENT_CATALOG]


def researcher_agent(task: str, settings: Settings) -> dict[str, Any]:
    """Create an explicit evidence handoff artifact through AI Core LLM."""
    agent = A2A_AGENT_CATALOG[0]
    evidence = chat_text(settings, [{"role": "system", "content": agent["system_prompt"]}, {"role": "user", "content": task}])
    return {"sender": agent["agent_id"], "recipient": "launch-advisor", "type": "food_product_evidence", "task": task, "payload": {"evidence_brief": evidence}}


def launch_advisor_agent(handoff: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Consume only the declared handoff contract and produce a recommendation artifact."""
    if handoff.get("recipient") != "launch-advisor" or handoff.get("type") != "food_product_evidence":
        raise ValueError("Launch Advisor는 Food Researcher의 food_product_evidence handoff만 처리합니다.")
    agent = A2A_AGENT_CATALOG[1]
    recommendation = chat_text(
        settings,
        [{"role": "system", "content": agent["system_prompt"]}, {"role": "user", "content": str(handoff["payload"]["evidence_brief"])}],
    )
    return {"sender": agent["agent_id"], "recipient": "user", "type": "launch_recommendation", "payload": {"recommendation": recommendation, "source_handoff_type": handoff["type"]}}


def run_food_handoff(task: str, settings: Settings | None = None) -> dict[str, Any]:
    """Run Food Researcher → Launch Advisor handoff using real AI Core LLM calls."""
    if not task.strip():
        raise ValueError("task는 비어 있을 수 없습니다.")
    active_settings = settings or load_settings()
    trace = [{"step": 1, "event": "a2a_task", "payload": {"sender": "user", "recipient": "food-researcher", "task": task}}]
    evidence = researcher_agent(task, active_settings)
    trace.append({"step": 2, "event": "a2a_handoff", "payload": evidence})
    report = launch_advisor_agent(evidence, active_settings)
    trace.append({"step": 3, "event": "a2a_result", "payload": report})
    return {"report": report, "handoff": evidence, "trace": trace, "execution_boundary": "AI Core LLM only; no external write actions."}
