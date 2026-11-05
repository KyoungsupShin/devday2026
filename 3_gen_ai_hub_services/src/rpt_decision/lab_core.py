"""Public read-only workflow for the SAP RPT Decision API lab."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

RPT_DECISION_ENDPOINT = "https://rpt.cloud.sap/api/systemone"
DEFAULT_RPT_DECISION_MODEL = "sap-rpt-1.6"
DEFAULT_DECISION_STATE = (
    "주문 PO-1042의 납품 예정일이 지났지만 입고되지 않았습니다. "
    "생산 라인이 오늘 멈출 수 있으니 공급망 현황과 새 납기일을 확인해 주세요."
)
NEXT_AGENT_CANDIDATES = {
    "hr_agent": "HR Agent · People & Workforce Operations",
    "scm_agent": "SCM Agent · Supply Chain & Logistics",
    "rnd_agent": "R&D Agent · Product & Technology Development",
}
HANDOFF_MODE_CANDIDATES = {
    "delegate_now": "즉시 위임",
    "request_evidence": "증거 요청 후 위임",
    "request_human_approval": "사람 승인 요청",
}
RISK_CANDIDATES = {
    "low": "낮음 · 일반 운영 영향",
    "medium": "중간 · 일정·비용 영향 가능",
    "high": "높음 · 생산·계약 영향",
}
PRIORITY_CANDIDATES = {
    "0": "대기 가능",
    "1": "이번 주",
    "2": "오늘",
}
NEXT_AGENT_CRITERIA = {
    "hr_agent": (
        "Investigate employee, organization, recruiting, staffing, attendance, leave, capability, workforce planning, or HR policy facts in read-only mode and return an HR artifact. "
        "Choose this agent when the unresolved fact concerns people, organization, or workforce operations. "
        "Materials, supply, and delivery belong to SCM; product specifications, experiments, and technical design belong to R&D."
    ),
    "scm_agent": (
        "Investigate demand and supply, inventory, warehousing, procurement, suppliers, production materials, order fulfilment, transport, delivery, ETA, or logistics facts in read-only mode and return an SCM artifact. "
        "Choose this agent when the unresolved fact concerns where materials or goods are, or how they will be sourced, moved, or delivered. "
        "People and organization questions belong to HR; new product design, experiments, and technical validation belong to R&D."
    ),
    "rnd_agent": (
        "Investigate product or service requirements, research, experiments, prototypes, formulation, design, quality characteristics, technical feasibility, validation, or improvement opportunities in read-only mode and return an R&D artifact. "
        "Choose this agent when the unresolved fact concerns what must be developed, designed, tested, or technically validated. "
        "Supply, inventory, and delivery of finished goods belong to SCM; employee and organization operations belong to HR."
    ),
}
HANDOFF_MODE_CRITERIA = {
    "delegate_now": (
        "Choose this only when the task state contains the minimum identifier and purpose needed for the selected agent to begin a read-only investigation. "
        "Immediate delegation passes a research task; it does not authorize an order change, purchase, compensation, or other external write."
    ),
    "request_evidence": (
        "Choose this when a required identifier or operational context is missing, or the request is ambiguous. "
        "State specifically which employee, order, item, warehouse, supplier, contract, date, product, or test result is needed. "
        "Do not guess or invoke agents repeatedly until the missing information is added to the task state."
    ),
    "request_human_approval": (
        "Choose this when a budget, contract, policy, legal liability, safety concern, or irreversible exception requires an authorized decision before delegation. "
        "The approval task must include evidence, expected impact, alternatives, and the decision required. "
        "Approval does not replace investigation; another agent may still need to collect facts."
    ),
}
RISK_CRITERIA = {
    "low": "A bounded inquiry, evidence request, policy explanation, or normal planning task without an immediate interruption to operations, people, customers, product safety, or delivery commitments.",
    "medium": "A schedule, cost, customer commitment, staffing, product milestone, or operational-plan impact that needs investigation and adjustment while business continuity remains intact.",
    "high": "An imminent production stop, safety issue, contract breach, critical customer or workforce disruption, product-release blocker, major cost exposure, or supply-chain interruption that will cause real harm without prompt action.",
}
PRIORITY_CRITERIA = [
    "0: Can wait within normal operating cadence; no immediate impact to operations, people, customers, product delivery, or release commitments.",
    "1: Needs a plan or resolution this week to prevent a growing schedule, cost, customer, staffing, or product-development impact.",
    "2: Needs action today because a production stop, critical workforce or customer disruption, contract breach, safety issue, release blocker, or irrecoverable loss is occurring or imminent.",
]
CALIBRATION_EXAMPLES = [
    {
        "state": "For an organizational redesign, confirm each team's current headcount and required roles.",
        "answers": {"next_agent": "hr_agent", "handoff_mode": "delegate_now", "risk": "medium", "priority": "1"},
    },
    {
        "state": "There is a leave request, but the employee identifier and requested dates are missing; collect the required information first.",
        "answers": {"next_agent": "hr_agent", "handoff_mode": "request_evidence", "risk": "low", "priority": "0"},
    },
    {
        "state": "A shortage of safety-qualified staff may stop site operations today; check the availability of replacement staff immediately.",
        "answers": {"next_agent": "hr_agent", "handoff_mode": "delegate_now", "risk": "high", "priority": "2"},
    },
    {
        "state": "Check available inventory by warehouse to determine whether this week's orders can be fulfilled.",
        "answers": {"next_agent": "scm_agent", "handoff_mode": "delegate_now", "risk": "medium", "priority": "1"},
    },
    {
        "state": "A transport delay is reported, but the order number and shipment identifier are absent; gather the missing evidence first.",
        "answers": {"next_agent": "scm_agent", "handoff_mode": "request_evidence", "risk": "low", "priority": "0"},
    },
    {
        "state": "A supplier outage may leave production materials short today; check alternative sourcing and delivery feasibility.",
        "answers": {"next_agent": "scm_agent", "handoff_mode": "delegate_now", "risk": "high", "priority": "2"},
    },
    {
        "state": "Create an experiment plan to define a new product's material formulation and performance targets.",
        "answers": {"next_agent": "rnd_agent", "handoff_mode": "delegate_now", "risk": "medium", "priority": "1"},
    },
    {
        "state": "A product defect must be analyzed, but the product identifier and test results are missing; request the required evidence first.",
        "answers": {"next_agent": "rnd_agent", "handoff_mode": "request_evidence", "risk": "low", "priority": "0"},
    },
    {
        "state": "A product design change with a safety concern must be reviewed before release, and an authorized decision is needed today.",
        "answers": {"next_agent": "rnd_agent", "handoff_mode": "request_human_approval", "risk": "high", "priority": "2"},
    },
]
# Keep role examples interleaved to avoid positional bias in few-shot evaluation.
CALIBRATION_EXAMPLES = [
    CALIBRATION_EXAMPLES[index]
    for index in (0, 3, 6, 1, 4, 7, 2, 5, 8)
]
Requester = Callable[..., Any]
StateTranslator = Callable[[str], str]

TASK_STATE_TRANSLATION_INSTRUCTION = """Translate the user's Korean business task state into concise English for an enterprise routing model.
Preserve every identifier, date, amount, urgency, approval requirement, missing-information condition, and business meaning.
Do not classify, summarize away details, add facts, or answer the request. Return only the English task state."""


SEMANTIC_COORDINATOR_CONTRACT = """You are an A2A semantic coordinator.
Choose from the candidate contracts by interpreting the task's meaning and lifecycle, not by matching words or candidate order. Return JSON only with next_agent, handoff_mode, risk, and priority.

Execution-agent contracts:
- hr_agent: handle employee, organization, staffing, recruiting, attendance, leave, capability, workforce planning, or HR policy questions.
- scm_agent: handle demand and supply, inventory, warehouse, procurement, supplier, material, order fulfilment, transport, delivery, ETA, or logistics questions.
- rnd_agent: handle product or service requirements, research, experiments, prototypes, formulation, design, technical feasibility, validation, or improvement questions.

Handoff contracts:
- delegate_now: the selected read-only Agent has the identity and purpose required to start.
- request_evidence: a required identifier or operational context is missing.
- request_human_approval: a contract, budget, policy, liability, or irreversible exception needs authorized approval.
If approval is needed, choose the execution Agent that can collect the relevant facts and set request_human_approval; do not invent a human Agent candidate.

Risk contracts:
- low: bounded inquiry without an immediate operational impact.
- medium: schedule, cost, or commitment impact while operations can continue.
- high: an imminent production stop, safety incident, contract breach, or critical-operation failure.

Priority contracts:
- 0: can wait within normal operating cadence.
- 1: needs a plan or resolution this week to avoid growing impact.
- 2: needs action today because severe impact is occurring or imminent.

Valid values are next_agent=hr_agent|scm_agent|rnd_agent; handoff_mode=delegate_now|request_evidence|request_human_approval; risk=low|medium|high; priority=0|1|2.
"""


def _required_text(value: str, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name}을(를) 입력하세요.")
    return cleaned


def translate_task_state_to_english(
    state: str,
    *,
    translator: StateTranslator | None = None,
) -> str:
    """Translate a task state with an LLM; no routing policy is applied here."""
    cleaned = _required_text(state, "state")
    if translator is not None:
        translated = translator(cleaned)
    else:
        try:
            from src.orchestration.lesson_support.config import load_settings as load_llm_settings
            from src.orchestration.lesson_support.llm import chat_text
        except ImportError as error:
            raise RuntimeError("Task-state translation에 필요한 AI Core LLM 모듈이 없습니다.") from error
        settings = load_llm_settings()
        settings.require_ai_core()
        translated = chat_text(
            settings,
            [
                {"role": "system", "content": TASK_STATE_TRANSLATION_INSTRUCTION},
                {"role": "user", "content": cleaned},
            ],
        )
    return _required_text(str(translated), "translated state")


def _semantic_answers(state: str) -> dict[str, Any]:
    """Use an AI Core LLM to apply the candidate contracts to a task state."""
    try:
        from src.orchestration.lesson_support.config import load_settings as load_llm_settings
        from src.orchestration.lesson_support.llm import chat_text
    except ImportError as error:
        raise RuntimeError("A2A semantic coordinator에 필요한 AI Core LLM 모듈이 없습니다.") from error

    raw = chat_text(
        load_llm_settings(),
        [
            {"role": "system", "content": SEMANTIC_COORDINATOR_CONTRACT},
            {"role": "user", "content": f"Task state: {state}"},
        ],
    ).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Semantic coordinator가 JSON을 반환하지 않았습니다: {raw}") from error
    if not isinstance(parsed, Mapping):
        raise RuntimeError("Semantic coordinator 응답이 JSON 객체가 아닙니다.")

    next_agent = parsed.get("next_agent")
    handoff_mode = parsed.get("handoff_mode")
    risk = parsed.get("risk")
    priority = parsed.get("priority")
    if next_agent not in NEXT_AGENT_CANDIDATES:
        raise RuntimeError("Semantic coordinator가 유효하지 않은 next_agent를 반환했습니다.")
    if handoff_mode not in HANDOFF_MODE_CANDIDATES:
        raise RuntimeError("Semantic coordinator가 유효하지 않은 handoff_mode를 반환했습니다.")
    if risk not in RISK_CANDIDATES:
        raise RuntimeError("Semantic coordinator가 유효하지 않은 risk를 반환했습니다.")
    if str(priority) not in PRIORITY_CANDIDATES:
        raise RuntimeError("Semantic coordinator가 유효하지 않은 priority를 반환했습니다.")
    return {
        "next_agent": str(next_agent),
        "handoff_mode": str(handoff_mode),
        "risk": str(risk),
        "priority": str(priority),
    }


def build_rpt_decision_request(state: str, *, model: str = DEFAULT_RPT_DECISION_MODEL) -> dict[str, Any]:
    """Build the fixed educational multi-question Decision API request."""
    return {
        "model": _required_text(model, "model"),
        "state": _required_text(state, "state"),
        "questions": {
            "next_agent": {
                "type": "choice",
                "instructions": (
                    "Choose one A2A agent from the unresolved fact that matters most in the current task state. "
                    "Classify the business domain before selecting: people and organization belong to HR; supply, inventory, procurement, transport, and delivery belong to SCM; "
                    "product requirements, research, experiments, design, and technical validation belong to R&D. "
                    "Authority, contract, budget, and policy decisions are handled by handoff_mode, not by selecting a different agent. "
                    "Use the next fact that must be investigated or the next authority that must be obtained, not surface keywords or candidate order."
                ),
                "criteria": NEXT_AGENT_CRITERIA,
            },
            "handoff_mode": {
                "type": "choice",
                "instructions": (
                    "Decide whether the selected agent can begin a read-only investigation from the current task state. "
                    "Delegate now only when the purpose and minimum identifiers are sufficient; request evidence when a missing fact would make the result unreliable. "
                    "Request human approval only when an authorized decision is required for an irreversible budget, contract, policy, or safety exception."
                ),
                "criteria": HANDOFF_MODE_CRITERIA,
            },
            "risk": {
                "type": "choice",
                "instructions": (
                    "Assess the expected business impact from the current evidence as low, medium, or high. "
                    "Use low for a bounded inquiry, medium for a schedule, cost, staffing, customer, or product milestone impact while work continues, "
                    "and high for imminent serious harm such as an operational stop, safety issue, contract breach, critical disruption, or release blocker. "
                    "Base the decision on concrete impact and urgency, not emotional wording or request length."
                ),
                "criteria": RISK_CRITERIA,
            },
            "priority": {
                "type": "score",
                "instructions": (
                    "Score urgency as 0 (can wait), 1 (this week), or 2 (today). "
                    "Choose 0 when normal handling is sufficient, 1 when delay will grow a schedule, cost, commitment, staffing, or product-development impact, "
                    "and 2 when failing to act today will cause or imminently cause serious harm. "
                    "Priority is independent of agent selection and does not authorize an external change."
                ),
                "criteria": PRIORITY_CRITERIA,
            },
        },
        "examples": CALIBRATION_EXAMPLES,
    }


def _answer_summary(answers: Mapping[str, Any]) -> list[dict[str, Any]]:
    next_agent = answers.get("next_agent")
    handoff_mode = answers.get("handoff_mode")
    risk = answers.get("risk")
    priority = answers.get("priority")
    if not all(isinstance(answer, Mapping) for answer in (next_agent, handoff_mode, risk, priority)):
        raise RuntimeError("RPT Decision API 응답에 필수 답변이 없습니다.")
    return [
        {"question": "next_agent", "type": next_agent.get("type"), "prediction": next_agent.get("choice"), "confidence": next_agent.get("confidence")},
        {"question": "handoff_mode", "type": handoff_mode.get("type"), "prediction": handoff_mode.get("choice"), "confidence": handoff_mode.get("confidence")},
        {"question": "risk", "type": risk.get("type"), "prediction": risk.get("choice"), "confidence": risk.get("confidence")},
        {"question": "priority", "type": priority.get("type"), "prediction": priority.get("score"), "confidence": priority.get("confidence")},
    ]


def run_rpt_decision(
    state: str,
    api_key: str,
    *,
    model: str = DEFAULT_RPT_DECISION_MODEL,
    requester: Requester | None = None,
) -> dict[str, Any]:
    """Call the Decision API once and return JSON-friendly evidence."""
    token = _required_text(api_key, "SAP_RPT_API_KEY")
    request = build_rpt_decision_request(state, model=model)
    if requester is None:
        try:
            import requests
        except ImportError as error:
            raise RuntimeError("requests가 없습니다. requirements.txt를 설치하세요.") from error
        requester = requests.post

    response = requester(
        RPT_DECISION_ENDPOINT,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=request,
        timeout=60,
    )
    try:
        response.raise_for_status()
    except Exception as error:
        status = getattr(response, "status_code", "unknown")
        body = getattr(response, "text", "")
        raise RuntimeError(f"RPT Decision API 요청 실패 ({status}): {body}") from error

    response_data = response.json()
    if not isinstance(response_data, Mapping) or not isinstance(response_data.get("answers"), Mapping):
        raise RuntimeError("RPT Decision API 응답 형식에 answers 객체가 없습니다.")
    answers = response_data["answers"]
    return {
        "model": request["model"],
        "state": request["state"],
        "summary": _answer_summary(answers),
        "answers": dict(answers),
        "usage": response_data.get("usage", {}),
        "http_status": getattr(response, "status_code", None),
        "execution_boundary": "읽기 전용 SAP RPT Decision API 호출입니다. 이 결과는 Coordinator의 다음 handoff 후보일 뿐이며, 실제 A2A 메시지 전송, 사람 승인, 주문 변경 또는 외부 쓰기를 수행하지 않습니다.",
    }


def run_translated_rpt_decision(
    state: str,
    api_key: str,
    *,
    model: str = DEFAULT_RPT_DECISION_MODEL,
    requester: Requester | None = None,
    translator: StateTranslator | None = None,
) -> dict[str, Any]:
    """Translate a Korean task state with an LLM before requesting RPT."""
    original_state = _required_text(state, "state")
    translated_state = translate_task_state_to_english(original_state, translator=translator)
    result = run_rpt_decision(
        translated_state, api_key, model=model, requester=requester,
    )
    return {
        **result,
        "original_state": original_state,
        "translated_state": translated_state,
        "decision_engine": "AI Core task-state translation followed by SAP RPT Decision API",
        "execution_boundary": (
            "AI Core translates the task state and SAP RPT Decision API makes a read-only candidate decision. "
            "Neither step sends A2A messages, approves requests, changes orders, or writes externally."
        ),
    }


def run_a2a_coordinator_decision(
    state: str,
    api_key: str,
    *,
    model: str = DEFAULT_RPT_DECISION_MODEL,
    requester: Requester | None = None,
) -> dict[str, Any]:
    """Combine RPT candidate probabilities with an LLM semantic handoff decision."""
    rpt_result = run_rpt_decision(state, api_key, model=model, requester=requester)
    semantic = _semantic_answers(state)
    answers = dict(rpt_result["answers"])
    for name in ("next_agent", "handoff_mode", "risk"):
        evidence = dict(answers[name])
        evidence["choice"] = semantic[name]
        evidence["semantic_choice"] = semantic[name]
        answers[name] = evidence
    priority_evidence = dict(answers["priority"])
    priority_evidence["score"] = float(semantic["priority"])
    priority_evidence["semantic_score"] = int(semantic["priority"])
    answers["priority"] = priority_evidence
    return {
        **rpt_result,
        "answers": answers,
        "summary": _answer_summary(answers),
        "decision_engine": "AI Core semantic coordinator with SAP RPT candidate probabilities",
        "rpt_answers": rpt_result["answers"],
        "execution_boundary": (
            "AI Core LLM이 후보 계약을 해석해 A2A handoff를 판단하고, SAP RPT Decision API는 후보 확률 증거를 제공합니다. "
            "두 호출 모두 읽기 전용이며 실제 A2A 메시지 전송, 사람 승인, 주문 변경 또는 외부 쓰기를 수행하지 않습니다."
        ),
    }
