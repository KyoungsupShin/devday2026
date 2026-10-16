"""LLM-driven cross-team agent conversation for Business Operation Harness.

Every team-agent utterance is generated through the configured AI Core model.
There is no fixture, rule-engine decision, expected-path assertion, or fallback
answer: unavailable information stays explicitly unknown in the LLM context.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from lab_common.ai_core import chat_text
from lab_common.config import Settings, load_settings


@dataclass(frozen=True)
class TeamMessage:
    """One visible interface message between cross-team LLM agents."""

    message_id: str
    thread_id: str
    from_team: str
    from_agent: str
    to_team: str
    to_agent: str
    kind: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


TEAM_INTERFACES = {
    "business_ops_lead": {
        "team": "business_operations",
        "role": "요청을 운영 관점으로 정리하고, 다른 팀에 필요한 정보와 의사결정 맥락을 전달한다.",
    },
    "inventory_specialist": {
        "team": "business_operations",
        "role": "사용자 제공 정보와 앞선 대화만 근거로 공급·재고 영향, 미확인 정보, 후속 확인 항목을 분석한다.",
    },
    "customer_ops_lead": {
        "team": "customer_operations",
        "role": "고객 운영 관점의 영향·우선순위·협업 요청을 조율한다.",
    },
    "service_coordinator": {
        "team": "customer_operations",
        "role": "고객 커뮤니케이션과 운영 대응의 실행 초안을 작성한다.",
    },
}


def interface_catalog() -> dict[str, dict[str, str]]:
    """Expose team-agent responsibilities for the UI without imposing routes."""
    return TEAM_INTERFACES


def _message(
    *,
    thread_id: str,
    from_team: str,
    from_agent: str,
    to_team: str,
    to_agent: str,
    kind: str,
    content: str,
) -> TeamMessage:
    return TeamMessage(
        message_id=str(uuid4()),
        thread_id=thread_id,
        from_team=from_team,
        from_agent=from_agent,
        to_team=to_team,
        to_agent=to_agent,
        kind=kind,
        content=content.strip(),
    )


def _conversation_context(messages: list[TeamMessage]) -> str:
    if not messages:
        return "(아직 agent 간 메시지가 없습니다.)"
    return "\n\n".join(
        f"[{item.from_team}/{item.from_agent} → {item.to_team}/{item.to_agent}; {item.kind}]\n{item.content}"
        for item in messages
    )


def agent_prompt(
    *, role: str, task: str, user_request: str, prior_messages: list[TeamMessage]
) -> list[dict[str, str]]:
    """Build the transparent LLM prompt supplied to one team agent."""
    return [
        {
            "role": "system",
            "content": (
                f"너는 {role} 역할의 운영 협업 agent다. 한국어로 간결하게 작성한다. "
                "사용자가 제공하거나 이전 메시지에 명시된 내용만 사실로 취급한다. "
                "외부 시스템, 재고, 고객, 정책, 일정, 실행 결과를 확인했다고 주장하거나 숫자·이름을 지어내지 않는다. "
                "확인되지 않은 정보는 '미확인'으로 명시한다. 외부 행동을 실행하지 않는다."
            ),
        },
        {
            "role": "user",
            "content": (
                f"원래 사용자 요청:\n{user_request}\n\n"
                f"현재 agent 작업:\n{task}\n\n"
                f"이전 team 메시지:\n{_conversation_context(prior_messages)}\n\n"
                "다음 agent가 그대로 활용할 수 있는 협업 메시지 하나만 작성하세요."
            ),
        },
    ]


def _ask(
    *,
    settings: Settings,
    model: str | None,
    role: str,
    task: str,
    user_request: str,
    prior_messages: list[TeamMessage],
) -> str:
    return chat_text(
        settings,
        agent_prompt(role=role, task=task, user_request=user_request, prior_messages=prior_messages),
        model=model,
    )


def run_cross_team_chat(
    request: str, *, settings: Settings | None = None, model: str | None = None
) -> dict[str, Any]:
    """Run an LLM conversation across two agent teams and return its visible trace."""
    if not request or not request.strip():
        raise ValueError("운영 요청을 입력하세요.")

    configured_settings = settings or load_settings()
    selected_model = model or configured_settings.llm_model
    thread_id = str(uuid4())
    messages: list[TeamMessage] = []

    def ask_and_append(
        *, from_team: str, from_agent: str, to_team: str, to_agent: str, kind: str, task: str
    ) -> TeamMessage:
        content = _ask(
            settings=configured_settings,
            model=selected_model,
            role=TEAM_INTERFACES[from_agent]["role"],
            task=task,
            user_request=request.strip(),
            prior_messages=messages,
        )
        message = _message(
            thread_id=thread_id,
            from_team=from_team,
            from_agent=from_agent,
            to_team=to_team,
            to_agent=to_agent,
            kind=kind,
            content=content,
        )
        messages.append(message)
        return message

    messages.append(
        _message(
            thread_id=thread_id,
            from_team="user",
            from_agent="user",
            to_team="business_operations",
            to_agent="business_ops_lead",
            kind="user_request",
            content=request,
        )
    )
    ask_and_append(
        from_team="business_operations", from_agent="business_ops_lead",
        to_team="business_operations", to_agent="inventory_specialist",
        kind="delegation",
        task="요청을 분석하고 supply/inventory specialist가 확인할 질문과 필요한 근거를 위임하세요.",
    )
    ask_and_append(
        from_team="business_operations", from_agent="inventory_specialist",
        to_team="business_operations", to_agent="business_ops_lead",
        kind="business_analysis",
        task="공급·재고 운영 영향, 미확인 정보, 다른 팀에 전달할 의사결정 쟁점을 분석하세요.",
    )
    ask_and_append(
        from_team="business_operations", from_agent="business_ops_lead",
        to_team="customer_operations", to_agent="customer_ops_lead",
        kind="team_handoff",
        task="Business Operations 분석을 Customer Operations에 전달하고 필요한 고객 운영 협업을 요청하세요.",
    )
    ask_and_append(
        from_team="customer_operations", from_agent="customer_ops_lead",
        to_team="customer_operations", to_agent="service_coordinator",
        kind="delegation",
        task="고객 운영 specialist에게 대응·커뮤니케이션 초안 작성을 위임하세요.",
    )
    ask_and_append(
        from_team="customer_operations", from_agent="service_coordinator",
        to_team="customer_operations", to_agent="customer_ops_lead",
        kind="customer_operations_plan",
        task="확정되지 않은 사실을 분리해 고객 운영 대응과 커뮤니케이션 초안을 작성하세요.",
    )
    ask_and_append(
        from_team="customer_operations", from_agent="customer_ops_lead",
        to_team="business_operations", to_agent="business_ops_lead",
        kind="cross_team_response",
        task="Customer Operations의 협업 결과, 미확인 정보, Business Operations에 필요한 후속 결정을 전달하세요.",
    )
    final = ask_and_append(
        from_team="business_operations", from_agent="business_ops_lead",
        to_team="user", to_agent="inbox",
        kind="final_response",
        task="양 팀의 메시지를 종합하여 사용자에게 현황, 협업 결과, 미확인 사항, 다음 확인 항목을 간결히 답하세요.",
    )

    return {
        "summary": final.content,
        "trace": [{"event": "llm_agent_message", "message": message.to_dict()} for message in messages],
        "session": {
            "thread_id": thread_id,
            "model": selected_model,
            "llm_agent_calls": len(messages) - 1,
            "external_actions": "none",
        },
    }
