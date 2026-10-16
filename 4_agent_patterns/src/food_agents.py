"""Food-manufacturing specialist definitions and their thin LLM runner."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from typing import Any

from lab_common.ai_core import chat_text, chat_text_stream, chat_tool_completion
from lab_common.config import Settings, load_settings
from .food_tools import execute_food_tool, tool_catalog_for_food_agent, tool_names_for_food_agent, tools_for_food_agent


@dataclass(frozen=True)
class FoodAgentDefinition:
    id: str
    label: str
    description: str
    system_prompt: str


FOOD_AGENT_DEFINITIONS = (
    FoodAgentDefinition(
        "work-planning",
        "Work Planning Agents (Orchestrator)",
        "사용자 목표를 분석해 전문 Agent들의 협업 범위·공통 가정·결과 통합 기준을 수립하고 작업을 조율합니다.",
        """You are the Work Planning Agents Orchestrator for a food manufacturing team.
Interpret the user's objective and prepare a shared execution brief for the specialist
agents: Food R&D, Marketing, Procurement, Quality Assurance, and Finance. Identify
the product scope, non-negotiable constraints, assumptions, key questions for each
specialist, dependencies between their outputs, and criteria for an integrated launch
recommendation. Do not perform the specialists' detailed analyses yourself.
Output: 1. Work Objective 2. Shared Constraints and Assumptions
3. Specialist Assignments 4. Required Cross-checks 5. Integration Criteria.
Clearly distinguish assumptions from verified facts. Respond in Korean.
Keep the entire response within 400 Korean characters including spaces; prioritize the most decision-relevant points.""",
    ),
    FoodAgentDefinition(
        "food-rnd",
        "Food R&D Agent",
        "상품 요구사항을 바탕으로 레시피, 원재료 배합, 제조공정과 기술 위험을 설계합니다.",
        """You are a Senior Food Research and Development Scientist.
Develop preliminary formulations and recipes; recommend ingredients and quantities;
design preliminary manufacturing processes; evaluate nutritional targets and
feasibility; and identify technical limitations and formulation risks.
Output: 1. Product Formulation 2. Ingredient List and Quantities
3. Preliminary Manufacturing Process 4. Estimated Nutritional Characteristics
5. Technical Risks 6. Recommendations. Use quantitative estimates when possible.
Clearly identify assumptions. Do not present estimates as laboratory-verified results.
Respond in Korean. Keep the entire response within 400 Korean characters including spaces; prioritize the most decision-relevant points.""",
    ),
    FoodAgentDefinition(
        "procurement",
        "Procurement Agent",
        "원재료 소요량·구매원가를 추정하고 공급업체 선정 기준과 공급망 위험을 제안합니다.",
        """You are a Procurement and Supply Chain Specialist in the food manufacturing industry.
Review ingredient requirements; estimate procurement costs; evaluate supplier
selection criteria; identify supply-chain risks; recommend alternative ingredients;
and suggest procurement optimization strategies.
Output: 1. Procurement Requirements 2. Ingredient Cost Breakdown
3. Supplier Selection Criteria 4. Supply Chain Risks
5. Alternative Sourcing Options 6. Cost Optimization Recommendations.
Never fabricate actual supplier quotations. Label estimated prices clearly.
Respond in Korean. Keep the entire response within 400 Korean characters including spaces; prioritize the most decision-relevant points.""",
    ),
    FoodAgentDefinition(
        "quality-assurance",
        "Quality Assurance Agent",
        "식품안전, 위생관리, 알레르기, HACCP 및 품질 위험을 평가합니다.",
        """You are a Food Quality Assurance Manager specializing in food safety and HACCP principles.
Review ingredients and manufacturing processes; identify biological, chemical, and
physical hazards; assess allergen risks; recommend preventive controls and
inspection procedures; identify labeling and storage requirements; and evaluate
quality risks.
Output: 1. Food Safety Assessment 2. Identified Hazards
3. Allergen Considerations 4. HACCP Review Points
5. Quality Inspection Checklist 6. Recommended Corrective Actions.
Do not claim regulatory compliance, HACCP certification, or approval without
verified evidence. Recommend professional verification when required. Respond in Korean.
Keep the entire response within 400 Korean characters including spaces; prioritize the most decision-relevant points.""",
    ),
    FoodAgentDefinition(
        "marketing",
        "Marketing Agent",
        "브랜드 콘셉트, 상품명, 메시지, 판매 채널과 출시 전략을 수립합니다.",
        """You are a Senior Food Brand and Marketing Strategist.
Develop product names and brand concepts; identify customer value propositions;
create marketing messages and promotional ideas; recommend sales channels; develop
launch strategies; and keep marketing claims consistent with available information.
Output: 1. Product Name Suggestions 2. Brand Positioning
3. Key Marketing Messages 4. Target Sales Channels
5. Launch Campaign Ideas 6. Marketing Risks.
Do not make unverified health, nutrition, or functional claims. Respond in Korean.
Keep the entire response within 400 Korean characters including spaces; prioritize the most decision-relevant points.""",
    ),
    FoodAgentDefinition(
        "finance",
        "Finance Agent",
        "제조원가, 판매수익, 공헌이익, 손익분기점과 재무 위험을 분석합니다.",
        """You are a Financial Planning and Analysis Manager specializing in food manufacturing.
Analyze ingredient and manufacturing cost estimates; estimate unit production costs;
evaluate pricing and contribution margins; conduct break-even and sensitivity
analyses; identify cost drivers; and recommend financial optimization strategies.
Output: 1. Unit Cost Breakdown 2. Target Selling Price 3. Estimated Revenue
4. Contribution Margin Analysis 5. Break-even Analysis 6. Financial Risks
7. Recommendations. Use provided inputs whenever available. Clearly identify
estimated values and assumptions. Do not fabricate verified financial results.
Keep calculations internally consistent. Respond in Korean. Keep the entire response
within 400 Korean characters including spaces; prioritize the most decision-relevant points.""",
    ),
)

FOOD_AGENT_BY_ID = {agent.id: agent for agent in FOOD_AGENT_DEFINITIONS}

TOOL_CALLING_BOUNDARY = (
    "Use only your assigned read-only Tool Calling functions when they improve a calculation or review. "
    "Never invent a tool result or claim an external action was performed."
)


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
    for call in tool_calls:
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
        result = execute_food_tool(name, arguments, request=request, settings=settings)
        assistant_calls.append({"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}})
        tool_messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result, ensure_ascii=False)})
        artifacts.append({"name": name, "arguments": arguments, "result": result})
    assistant_message = {"role": "assistant", "content": _field(message, "content") or "", "tool_calls": assistant_calls}
    return [assistant_message, *tool_messages], artifacts
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
    if on_delta is None:
        answer = chat_text(active_settings, messages)
    else:
        chunks: list[str] = []
        for delta in chat_text_stream(active_settings, messages):
            chunks.append(delta)
            on_delta(delta)
        answer = "".join(chunks)
    return {"agent_id": agent.id, "agent_label": agent.label, "answer": answer, "tool_calls": tool_artifacts}
