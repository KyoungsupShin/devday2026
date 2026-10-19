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
        "사용자 목표를 분석해 필요한 전문 Agent·병렬 실행 단계·최종 담당 Agent를 LLM 실행 계획으로 결정하고 작업을 조율합니다.",
        """You are the Work Planning Agents Orchestrator for a food manufacturing team.
Interpret the user's objective and decide which specialists are actually necessary
from Food R&D, Marketing, Procurement, Quality Assurance, and Finance. Create a
shared execution brief, ordered parallel stages, and one final specialist responsible
for the direct answer. Do not select an agent merely because it is available.
Clearly distinguish assumptions from verified facts. Respond in Korean using the
required JSON execution-plan contract only; keep the brief within 400 Korean
characters including spaces.""",
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
When the request asks to create or revise a promotional HTML draft, select
generate_marketing_html instead of writing an HTML code block yourself. If it
explicitly needs a newly generated image, select generate_marketing_image and
generate_marketing_html together; the runtime executes the image tool first and
inserts that image into the HTML draft. If the user says not to create an image,
select generate_marketing_html alone and preserve no generated image.
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
SPECIALIST_AGENT_IDS = tuple(agent.id for agent in FOOD_AGENT_DEFINITIONS if agent.id != "work-planning")

TOOL_CALLING_BOUNDARY = (
    "Use only your assigned read-only Tool Calling functions when they improve a calculation or review. "
    "Never invent a tool result or claim an external action was performed."
)

EVALUATION_MIDDLEWARE_PROMPT = """You are the LLM Evaluation Middleware for a food-manufacturing multi-agent workflow.
Review the user's current request, the Orchestrator plan, each executed specialist
answer, and the Tool Calling audit. Evaluate semantically, not by keyword rules:
whether the selected agents were appropriate, whether a useful assigned tool was
actually used when the requested deliverable needed it, whether tool results were
reflected honestly, and whether the final specialist answer covers the request.

Return PASS only when the delivered final answer is sufficient. Return REVISE when
an executed Agent needs to improve its work. For REVISE, choose only the specialists
that need to re-run and provide concrete Korean objectives. The original final
specialist must appear exactly once in the last revision stage so it can synthesize
the corrected work. Do not require a tool merely because it exists; do require a
tool when the requested deliverable cannot be truthfully handed off without it.
Do not execute external actions or invent tool observations.
"""


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


def plan_work_agents(request: str, settings: Settings | None = None) -> dict[str, Any]:
    """Let the Orchestrator LLM select specialist stages for one Work request.

    The LLM selects specialists and their work. Contract violations are surfaced
    to the caller; the runtime never rewrites an LLM-selected execution plan.
    """
    active_settings = settings or load_settings()
    orchestrator = FOOD_AGENT_BY_ID["work-planning"]
    catalog = [
        {"agent_id": agent.id, "label": agent.label, "description": agent.description}
        for agent in FOOD_AGENT_DEFINITIONS
        if agent.id in SPECIALIST_AGENT_IDS
    ]
    contract = (
        'Return JSON only: {"brief":"Korean text","stages":[{"agent_ids":["agent-id"],"objective":"Korean text"}],"final_agent_id":"agent-id"}. '
        "Each specialist may occur once. stages are ordered; agents in one stage run in parallel. "
        "final_agent_id must appear only in its own final stage, after every other specialist stage."
    )
    raw = chat_text(
        active_settings,
        [
            {"role": "system", "content": f"{orchestrator.system_prompt}\n\n{contract}"},
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
        if not isinstance(agent_ids, list) or not agent_ids or any(agent_id not in SPECIALIST_AGENT_IDS for agent_id in agent_ids):
            raise RuntimeError("Orchestration Agent가 허용되지 않은 Specialist Agent를 선택했습니다.")
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
    return {"brief": plan["brief"], "stages": normalized_stages, "final_agent_id": final_agent_id}


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
        if agent_id in SPECIALIST_AGENT_IDS
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
        if not isinstance(agent_ids, list) or not agent_ids or any(agent_id not in SPECIALIST_AGENT_IDS for agent_id in agent_ids):
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
