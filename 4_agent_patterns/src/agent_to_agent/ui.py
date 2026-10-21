"""Dynamic observability UI for LLM orchestration, A2A, middleware, and artifacts."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import gradio as gr
from lab_common.config import Settings, load_settings

from .catalog import (
    AGENT_CATALOG,
    DEFAULT_REQUEST,
    SCENARIO_REQUEST_DEPARTMENTS,
    SCENARIO_REQUESTS,
    SUBAGENT_BY_LABEL,
)
from .history import persist_a2a_conversation, persist_human_approval_action
from .human_approval import OutlookMailError, send_outlook_mail
from .orchestration import list_agents, run_handoff_stream
from .tools import schemas_for_tool_ids

_AVATAR_ASSET_DIR = Path(__file__).resolve().parents[2] / "assets" / "brand"


def _brand_avatar_html(filename: str, label: str, icon: str) -> str:
    """Return a locally served, user-supplied brand image for a chat avatar."""
    asset_path = quote((_AVATAR_ASSET_DIR / filename).as_posix(), safe="/")
    return (
        '<img class="a2a-group-chat__brand-avatar" '
        f'src="/gradio_api/file={asset_path}" alt="{label}" '
        f'data-avatar-icon="{icon}">'
    )

A2A_WORKFLOW_GRAPH_SVG = """
<svg viewBox="0 0 1800 410" width="100%" role="img" aria-label="LLM-orchestrated A2A handoff workflow" xmlns="http://www.w3.org/2000/svg">
  <style>.node{fill:#fff;stroke:#8ab4f8;stroke-width:2}.work{fill:#f8fbff;stroke:#4285f4;stroke-width:2}.end{fill:#e6f4ea;stroke:#34a853;stroke-width:2}.middleware{fill:#fffdf5;stroke:#f9ab00;stroke-width:2}.label{font:600 15px sans-serif;fill:#202124}.small{font:13px sans-serif;fill:#5f6368}.edge{fill:none;stroke:#5f6368;stroke-width:2;marker-end:url(#a2a-arrow)}</style>
  <defs><marker id="a2a-arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#5f6368"/></marker></defs>
  <text x="25" y="32" class="label" style="font-size:18px">LLM-Orchestrated A2A Workflow</text>

  <rect x="25" y="180" width="155" height="76" rx="12" class="node"/><text x="102" y="210" text-anchor="middle" class="label">User request</text><text x="102" y="232" text-anchor="middle" class="small">message</text>
  <rect x="260" y="38" width="225" height="76" rx="12" class="work"/><text x="372" y="68" text-anchor="middle" class="label">ReAct Observation</text><text x="372" y="90" text-anchor="middle" class="small">artifacts · open decisions</text>
  <rect x="265" y="165" width="230" height="104" rx="12" class="work"/><text x="380" y="199" text-anchor="middle" class="label">Orchestration Agent</text><text x="380" y="222" text-anchor="middle" class="small">LLM decide: delegate / handoff</text><text x="380" y="244" text-anchor="middle" class="small">/ complete</text>
  <rect x="570" y="52" width="210" height="76" rx="12" class="work"/><text x="675" y="82" text-anchor="middle" class="label">Grounding &amp; Approval</text><text x="675" y="104" text-anchor="middle" class="small">LLM Tool Calling</text>
  <rect x="570" y="180" width="180" height="76" rx="12" class="work"/><text x="660" y="210" text-anchor="middle" class="label">A2A Handoff</text><text x="660" y="232" text-anchor="middle" class="small">Message + envelope</text>
  <rect x="825" y="155" width="225" height="126" rx="12" class="node"/><text x="937" y="188" text-anchor="middle" class="label">Selected A2A Team</text><text x="937" y="211" text-anchor="middle" class="small">LLM-selected Team Agent</text><text x="937" y="234" text-anchor="middle" class="small">internal sub-agents + tools</text><text x="937" y="257" text-anchor="middle" class="small">A2A Task updates</text>
  <rect x="1125" y="180" width="190" height="76" rx="12" class="work"/><text x="1220" y="210" text-anchor="middle" class="label">Task &amp; Artifact</text><text x="1220" y="232" text-anchor="middle" class="small">TextPart · DataPart</text>
  <rect x="1390" y="165" width="205" height="104" rx="12" class="middleware"/><text x="1492" y="199" text-anchor="middle" class="label">Middleware</text><text x="1492" y="222" text-anchor="middle" class="small">Task events · artifact received</text><text x="1492" y="244" text-anchor="middle" class="small">handoff audit</text>
  <rect x="1665" y="180" width="110" height="76" rx="12" class="end"/><text x="1720" y="210" text-anchor="middle" class="label">Response</text><text x="1720" y="232" text-anchor="middle" class="small">to Field</text>

  <path d="M180 218 H265" class="edge"/><text x="222" y="204" text-anchor="middle" class="small">Field Agent handoff</text><path d="M372 114 V165" class="edge"/><path d="M495 218 H570" class="edge"/><path d="M750 218 H825" class="edge"/><path d="M1050 218 H1125" class="edge"/><path d="M1315 218 H1390" class="edge"/><path d="M1595 218 H1665" class="edge"/>
  <path d="M495 190 C525 190 530 90 570 90" class="edge"/><text x="526" y="122" class="small">tool call</text>
  <path d="M675 128 C675 148 570 148 495 185" class="edge"/><text x="575" y="151" class="small">evidence</text>
  <path d="M1492 269 C1492 355 380 355 380 269" class="edge"/><text x="935" y="352" text-anchor="middle" class="small">artifact event → observe → next ReAct decision</text>
</svg>
"""

_A2A_GROUP_CHAT_SCROLL_JS = """
() => {
  const root = document.getElementById("a2a-group-chat");
  const payloadRoot = document.getElementById("a2a-chat-payload");
  const modal = document.getElementById("a2a-agent-cards-modal");
  const modalOpen = document.getElementById("a2a-agent-cards-open");
  if (modal && modalOpen && !modalOpen.dataset.modalBound) {
    modalOpen.dataset.modalBound = "true";
    const selectTeam = (teamId) => {
      modal.querySelectorAll("[data-a2a-team-select]").forEach((button) => {
        button.setAttribute("aria-selected", String(button.dataset.a2aTeamSelect === teamId));
      });
      modal.querySelectorAll("[data-a2a-team-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.a2aTeamPanel !== teamId;
      });
    };
    modal.querySelectorAll("[data-a2a-team-select]").forEach((button) => {
      button.addEventListener("click", () => selectTeam(button.dataset.a2aTeamSelect));
    });
    modalOpen.addEventListener("click", () => {
      const selected = modal.querySelector('[data-a2a-team-select][aria-selected="true"]');
      if (selected) selectTeam(selected.dataset.a2aTeamSelect);
      modal.showModal();
    });
    modal.querySelectorAll("[data-a2a-modal-close]").forEach((button) => {
      button.addEventListener("click", () => modal.close());
    });
    modal.addEventListener("click", (event) => {
      if (event.target === modal) modal.close();
    });
  }
  const toolbar = document.getElementById("a2a-page-toolbar");
  if (toolbar && !toolbar.dataset.toolbarBound) {
    toolbar.dataset.toolbarBound = "true";
    toolbar.addEventListener("click", (event) => {
      const action = event.target.closest("[data-a2a-chat-toolbar-action]");
      if (!action || !toolbar.contains(action)) return;
      const selector = action.dataset.a2aChatToolbarAction === "reset"
        ? "#a2a-chat-reset-action button, button#a2a-chat-reset-action"
        : "#a2a-chat-pause-action button, button#a2a-chat-pause-action";
      document.querySelector(selector)?.click();
    });
  }
  if (!root || !payloadRoot || root.dataset.chatBound) return;
  root.dataset.chatBound = "true";
  const invokeHiddenAction = (selector) => {
    document.querySelector(selector)?.click();
  };
  root.addEventListener("click", (event) => {
    const approvalAction = event.target.closest("[data-a2a-approval-action]");
    if (approvalAction && root.contains(approvalAction)) {
      event.preventDefault();
      if (approvalAction.dataset.a2aActionPending === "true") return;
      approvalAction.dataset.a2aActionPending = "true";
      approvalAction.disabled = true;
      const isSend = approvalAction.dataset.a2aApprovalAction === "send";
      approvalAction.textContent = isSend ? "발송 요청 중…" : "처리 중…";
      invokeHiddenAction(
        isSend
          ? "#a2a-approval-send button, button#a2a-approval-send"
          : "#a2a-approval-cancel button, button#a2a-approval-cancel"
      );
      return;
    }

    const trigger = event.target.closest("[data-a2a-human-review-complete]");
    if (!trigger || !root.contains(trigger)) return;
    event.preventDefault();
    if (trigger.dataset.a2aReviewRecorded === "true") return;
    trigger.dataset.a2aReviewRecorded = "true";
    trigger.disabled = true;
    trigger.textContent = "검토 완료를 기록하는 중…";
    invokeHiddenAction(
      "#a2a-human-review-complete button, button#a2a-human-review-complete"
    );
  });

  const state = {
    messages: root.querySelector(".a2a-group-chat__messages"),
    messageCount: 0,
    atLatest: true,
    unread: 0,
    badge: null,
    typingHtml: "",
  };
  if (!state.messages) return;
  const isAtLatest = (messages) =>
    messages.scrollHeight - messages.scrollTop - messages.clientHeight < 24;
  const updateBadge = () => {
    if (!state.badge) return;
    const visible = state.unread > 0 && !state.atLatest;
    const text = `새 메시지 ${state.unread}개`;
    if (state.badge.hidden === visible) state.badge.hidden = !visible;
    if (state.badge.textContent !== text) state.badge.textContent = text;
  };
  const scrollToLatest = (messages) => {
    messages.scrollTop = messages.scrollHeight;
    state.atLatest = true;
    state.unread = 0;
    updateBadge();
  };
  const ensureBadge = () => {
    const existing = root.querySelector(".a2a-group-chat__new-message");
    if (existing) {
      state.badge = existing;
      return;
    }
    const badge = document.createElement("button");
    badge.type = "button";
    badge.className = "a2a-group-chat__new-message";
    badge.hidden = true;
    badge.addEventListener("click", () => {
      if (state.messages) scrollToLatest(state.messages);
    });
    root.appendChild(badge);
    state.badge = badge;
  };
  const typingContainer = () => {
    let container = state.messages.querySelector(".a2a-group-chat__typing-container");
    if (!container) {
      container = document.createElement("div");
      container.className = "a2a-group-chat__typing-container";
      state.messages.appendChild(container);
    }
    return container;
  };
  const applyPayload = () => {
    const dataNode = payloadRoot.querySelector(".a2a-group-chat__payload-data");
    const serialized = dataNode?.dataset.payload;
    if (!serialized) return;
    let payload;
    try {
      payload = JSON.parse(serialized);
    } catch (_) {
      return;
    }
    const messageHtml = Array.isArray(payload.messages) ? payload.messages : [];
    const count = Number(payload.message_count) || 0;
    if (count < state.messageCount) {
      state.messages.replaceChildren();
      state.messageCount = 0;
    }
    const added = Math.max(0, count - state.messageCount);
    if (added) {
      if (state.messageCount === 0) state.messages.replaceChildren();
      const typing = typingContainer();
      for (let index = state.messageCount; index < count; index += 1) {
        typing.insertAdjacentHTML("beforebegin", messageHtml[index] || "");
      }
      state.messageCount = count;
    }
    const typing = typingContainer();
    const nextTypingHtml = typeof payload.typing_html === "string" ? payload.typing_html : "";
    const typingChanged = state.typingHtml !== nextTypingHtml;
    if (typingChanged) {
      typing.innerHTML = nextTypingHtml;
      state.typingHtml = nextTypingHtml;
    }
    if (state.atLatest && (added || typingChanged)) {
      requestAnimationFrame(() => {
        if (state.atLatest) scrollToLatest(state.messages);
      });
    } else if (added) {
      state.unread += added;
      updateBadge();
    }
  };
  ensureBadge();
  state.atLatest = isAtLatest(state.messages);
  state.messages.addEventListener("scroll", () => {
    state.atLatest = isAtLatest(state.messages);
    if (state.atLatest) state.unread = 0;
    updateBadge();
  }, { passive: true });
  new MutationObserver(() => requestAnimationFrame(applyPayload)).observe(
    payloadRoot, { childList: true, subtree: true, attributes: true }
  );
  applyPayload();
}
"""


def _display_text(value: Any) -> str:
    """Normalize readable values without omitting any supplied text."""
    rendered = _readable_value(value)
    lines = [" ".join(line.split()) for line in rendered.splitlines() if line.strip()]
    return "\n".join(lines)


def _display_sections(*sections: tuple[str, Any]) -> list[dict[str, str]]:
    """Keep complete values, while retaining their semantic labels for the UI."""
    return [
        {"label": title, "text": text}
        for title, value in sections
        if (text := _display_text(value))
    ]


def _sections_text(sections: list[dict[str, str]], heading: str | None = None) -> str:
    """Create a complete plain-text counterpart for persisted conversation logs."""
    parts = [heading] if heading else []
    for section in sections:
        parts.append(f"{section['label']}\n{section['text']}")
    return "\n\n".join(parts)


def _sectioned_chat_message(
    sender: str,
    kind: str,
    *sections: tuple[str, Any],
    heading: str | None = None,
) -> dict[str, Any]:
    """Return one complete chat message with separately renderable sections."""
    rendered_sections = _display_sections(*sections)
    return {
        "sender": sender,
        "kind": kind,
        "heading": heading,
        "sections": rendered_sections,
        "text": _sections_text(rendered_sections, heading),
    }


def _subagent_tool_html(subagent_label: str) -> str:
    """Render Tool availability from the same role-scoped schemas as execution."""
    subagent = SUBAGENT_BY_LABEL.get(subagent_label)
    tool_ids = subagent.get("tool_ids", ()) if subagent else ()
    schemas = schemas_for_tool_ids(tool_ids)
    if not schemas:
        return (
            '<span class="a2a-topology__no-tool">연동 Tool 없음 · LLM 분석 전용</span>'
        )

    cards = []
    for schema in schemas:
        function = schema.get("function", {})
        name = str(function.get("name", "Tool"))
        description = str(function.get("description", ""))
        cards.append(
            '<article class="a2a-topology__tool">'
            f"<code>{html.escape(name)}</code>"
            f"<span>{html.escape(description)}</span>"
            "</article>"
        )
    return "".join(cards)


def _agent_card_modal_html() -> str:
    """Build a Team sidebar with a selected Team's Sub-agent detail panel."""
    team_buttons = []
    team_panels = []
    for index, team in enumerate(AGENT_CATALOG):
        team_id = str(team["agent_id"])
        selected = index == 0
        subagents = []
        for subagent_label in team["sub_agents"]:
            subagents.append(
                '<li class="a2a-topology__subagent">'
                '<div class="a2a-topology__node-label">'
                f"<b>Sub-agent · {html.escape(subagent_label)}</b>"
                "</div>"
                '<div class="a2a-topology__tools">'
                '<span class="a2a-topology__tools-label">사용 가능 Tool</span>'
                f"{_subagent_tool_html(subagent_label)}"
                "</div></li>"
            )
        team_buttons.append(
            '<button type="button" class="a2a-topology__team-select" '
            f'data-a2a-team-select="{html.escape(team_id)}" '
            f'aria-selected="{str(selected).lower()}">'
            f"<b>{html.escape(team['agent_label'])}</b>"
            f"<span>{html.escape(team['description'])}</span>"
            "</button>"
        )
        team_panels.append(
            '<section class="a2a-topology__team-panel" '
            f'data-a2a-team-panel="{html.escape(team_id)}"'
            f"{' hidden' if not selected else ''}>"
            '<header class="a2a-topology__team-header">'
            f"<span>Team Agent</span><b>{html.escape(team['agent_label'])}</b>"
            f"<code>{html.escape(team['agent_id'])}</code>"
            "</header>"
            f"<p>{html.escape(team['description'])}</p>"
            '<div class="a2a-topology__subagent-heading">Sub-agent와 역할별 Tool</div>'
            f'<ul class="a2a-topology__subagents">{"".join(subagents)}</ul>'
            "</section>"
        )
    return (
        '<dialog id="a2a-agent-cards-modal">'
        '<section class="a2a-topology">'
        '<header class="a2a-topology__modal-header">'
        "<div><span>03 · 기본 A2A 카드</span><h2>조직 Team · Sub-agent · Tool</h2></div>"
        '<button type="button" data-a2a-modal-close aria-label="닫기">×</button>'
        "</header>"
        '<p class="a2a-topology__intro">이 목록은 03 기본 A2A 실습 전용 Card입니다. Team Agent는 LLM으로 필요한 Sub-agent를 선택하고, Tool은 표시된 역할에서만 선택적으로 호출됩니다. 04 Advanced 실습의 Codex 통합 Agent는 이 목록에 포함되지 않습니다.</p>'
        '<div class="a2a-topology__layout">'
        f'<aside class="a2a-topology__sidebar">{"".join(team_buttons)}</aside>'
        f'<main class="a2a-topology__detail">{"".join(team_panels)}</main>'
        "</div>"
        "</section></dialog>"
    )


def _decode_status(task: dict[str, Any]) -> dict[str, Any]:
    text = (
        task.get("status", {}).get("message", {}).get("parts", [{}])[0].get("text", "")
    )
    try:
        value = json.loads(text)
        return (
            value
            if isinstance(value, dict)
            else {"event": "task_status", "message": text}
        )
    except json.JSONDecodeError:
        return {"event": "task_status", "message": text}


def _actor_name(actor_id: str, agents: dict[str, str]) -> str:
    return (
        "Orchestration Agent"
        if actor_id == "orchestration-agent"
        else agents.get(actor_id, actor_id)
    )


def _team_display_details(artifact: dict[str, Any]) -> dict[str, str]:
    """Extract the values rendered in a compact Team synthesis card."""
    payload = artifact.get("payload", {}) if isinstance(artifact, dict) else {}
    synthesis = payload.get("team_synthesis", {}) if isinstance(payload, dict) else {}
    if not isinstance(synthesis, dict):
        return {
            "summary": "",
            "evidence": "",
            "next_action": "",
            "chat_summary": "",
            "display_summary_error": False,
        }
    return {
        "summary": _display_text(synthesis.get("summary") or synthesis.get("analysis")),
        "evidence": _display_text(synthesis.get("evidence")),
        "next_action": _display_text(
            synthesis.get("next_action")
            or synthesis.get("recommendation")
            or synthesis.get("required_inputs")
        ),
        "chat_summary": _display_text(synthesis.get("chat_summary")),
        "display_summary_error": synthesis.get("display_summary_error") is True,
    }


def _team_sections(artifact: dict[str, Any]) -> list[dict[str, str]]:
    """Expose the complete, compact Team synthesis as labelled chat sections."""
    details = _team_display_details(artifact)
    return _display_sections(
        ("팀 요약", details["summary"]),
        ("근거", details["evidence"]),
        ("다음 조치", details["next_action"]),
    )


def _readable_artifact_text(artifact: dict[str, Any]) -> str:
    """Plain-text Team synthesis used by logs and tests."""
    sections = _team_sections(artifact)
    return _sections_text(sections) if sections else "검토 결과를 공유했습니다."


def _subagent_sections(artifact: dict[str, Any]) -> list[dict[str, str]]:
    """Expose the complete compact Sub-agent result as labelled chat sections."""
    details = _subagent_display_details(artifact)
    return _display_sections(
        ("핵심 판단", details["finding"]),
        ("근거", details["evidence"]),
        ("참고 정보", ", ".join(details["tool_names"])),
        ("추가 확인 사항", details["next_input"]),
    )


def _subagent_display_details(artifact: dict[str, Any]) -> dict[str, Any]:
    """Extract the values rendered in a compact Sub-agent review card."""
    tool_calls = artifact.get("tool_calls")
    tool_names = []
    profitability_calculation: dict[str, Any] | None = None
    if isinstance(tool_calls, list):
        tool_names = [
            str(call["name"])
            for call in tool_calls
            if isinstance(call, dict) and isinstance(call.get("name"), str)
        ]
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            result = call.get("result")
            if (
                call.get("name") == "calculate_profitability_scenarios"
                and isinstance(result, dict)
                and result.get("state") == "found"
                and isinstance(result.get("scenario_summaries"), list)
                and isinstance(result.get("monthly_forecasts"), list)
            ):
                profitability_calculation = result
                break
    return {
        "finding": _display_text(artifact.get("finding") or artifact.get("analysis")),
        "evidence": _display_text(artifact.get("evidence")),
        "tool_names": list(dict.fromkeys(tool_names)),
        "profitability_calculation": profitability_calculation,
        "next_input": _display_text(
            artifact.get("next_input") or artifact.get("required_inputs")
        ),
        "chat_summary": _display_text(artifact.get("chat_summary")),
        "display_summary_error": artifact.get("display_summary_error") is True,
    }


def _readable_subagent_text(artifact: dict[str, Any]) -> str:
    """Plain-text Sub-agent result used by logs and tests."""
    sections = _subagent_sections(artifact)
    return _sections_text(sections) if sections else "검토 결과를 공유했습니다."


def _delegation_chat_message(
    status: dict[str, Any], team_labels: dict[str, str]
) -> dict[str, Any]:
    """Make an LLM-selected Team delegation visible in the group chat."""
    team_id = str(status.get("team", "A2A Team"))
    delegations = status.get("delegations", [])
    requests = []
    goals = []
    if isinstance(delegations, list):
        for item in delegations:
            if isinstance(item, dict):
                agent, goal = item.get("agent"), item.get("goal")
                if isinstance(agent, str) and isinstance(goal, str):
                    requests.append(agent)
                    goals.append(goal)
    message = _sectioned_chat_message(
        team_labels.get(team_id, team_id),
        "agent",
        ("검토 담당", [*requests]),
        ("검토 목표", goals),
        heading="담당자 확인 요청",
    )
    if not message["sections"]:
        return {
            "sender": team_labels.get(team_id, team_id),
            "kind": "agent",
            "text": "담당자에게 확인을 요청합니다.",
        }
    return message


def _subagent_chat_message(
    status: dict[str, Any], team_labels: dict[str, str]
) -> dict[str, Any] | None:
    """Make a completed Sub-agent's complete artifact visible in the group chat."""
    artifact = status.get("artifact")
    agent, team_id = status.get("agent"), status.get("team")
    if not isinstance(artifact, dict) or not isinstance(agent, str):
        return None
    team_label = team_labels.get(str(team_id), str(team_id or "A2A Team"))
    sections = _subagent_sections(artifact)
    details = _subagent_display_details(artifact)
    if not sections and not any(details.values()):
        return {
            "sender": f"{team_label} · {agent}",
            "kind": "agent",
            "text": "검토 결과를 공유했습니다.",
        }
    message = _sectioned_chat_message(
        f"{team_label} · {agent}",
        "agent",
        *((section["label"], section["text"]) for section in sections),
        heading="담당자 검토 결과",
    )
    # Keep every artifact field in the message text for logs, while the chat uses
    # one compact card and exposes the long evidence only on demand.
    message["subagent_result"] = details
    return message


def _requester_label(request_department: str | None) -> str:
    """Name the requester from explicit UI context, never from request text."""
    department = (
        request_department.strip() if isinstance(request_department, str) else ""
    )
    return f"요청 부서 · {department}" if department else "요청 부서"


def _field_response_chat_message(
    message: str | dict[str, Any], request_department: str | None = None
) -> dict[str, Any]:
    """Show the final Orchestration response at the original requester's endpoint."""
    if isinstance(message, dict):
        sections = (
            ("현재 상태", message.get("status")),
            ("확인된 내용", message.get("summary")),
            ("다음 할 일", message.get("next_action")),
        )
        rendered = _sectioned_chat_message(
            _requester_label(request_department),
            "field",
            *sections,
            heading="최종 업데이트",
        )
        if rendered["sections"]:
            return rendered
    return _sectioned_chat_message(
        _requester_label(request_department),
        "field",
        ("현재 상태", "현업용 요약을 준비하지 못했습니다. 상세 기록을 확인해 주세요."),
        heading="최종 업데이트",
    )


def _orchestration_decision_chat_message(
    decision: dict[str, Any], target_label: str
) -> dict[str, str]:
    """Render one compact request from Orchestration to the selected Team."""
    message = _sectioned_chat_message(
        "Orchestration Agent",
        "orchestrator",
        ("요청 대상", target_label),
        ("검토 목적", decision.get("purpose")),
        ("판단 근거", decision.get("reason")),
        heading="다음 검토 요청",
    )
    if not message["sections"]:
        return {
            "sender": "Orchestration Agent",
            "kind": "orchestrator",
            "text": "다음 검토를 요청합니다.",
        }
    return message


def _task_plan_chat_message(decision: dict[str, Any]) -> dict[str, Any]:
    """Show the LLM's grounded, current task plan before the next handoff."""
    task_plan = decision.get("task_plan")
    if isinstance(task_plan, dict):
        grounding_basis = _display_text(task_plan.get("grounding_basis"))
        summary = _display_text(task_plan.get("summary"))
        tasks = task_plan.get("planned_tasks")
        if grounding_basis and summary and isinstance(tasks, list):
            planned_tasks = [
                task.strip() for task in tasks if isinstance(task, str) and task.strip()
            ]
            if planned_tasks:
                return _sectioned_chat_message(
                    "Orchestration Agent",
                    "orchestrator",
                    ("업무 기준에서 확인한 원칙", grounding_basis),
                    ("이번 검토 계획", summary),
                    ("예정된 확인", planned_tasks),
                    heading="업무 기준 기반 검토 계획",
                )
    return _sectioned_chat_message(
        "Orchestration Agent",
        "orchestrator",
        (
            "계획 상태",
            "현업용 검토 계획을 준비하지 못했습니다. 다음 검토 요청을 확인해 주세요.",
        ),
        heading="검토 계획",
    )


def _orchestration_completion_chat_message(decision: dict[str, Any]) -> dict[str, str]:
    """Make the terminal orchestration decision visible before final delivery."""
    update = decision.get("requester_update")
    status = _display_text(update.get("status")) if isinstance(update, dict) else ""
    return _sectioned_chat_message(
        "Orchestration Agent",
        "orchestrator",
        ("진행 상태", status or "최종 업데이트를 준비합니다."),
        heading="검토 마무리",
    )


def _observation_chat_message(observation: dict[str, Any]) -> dict[str, str]:
    """Render the operations-facing observation summary as a chat bubble."""
    summary = _display_text(observation.get("chat_summary"))
    if summary:
        return _sectioned_chat_message(
            "Orchestration Agent",
            "orchestrator",
            ("현재 상황", summary),
            heading="현재 확인 결과",
        )
    return _sectioned_chat_message(
        "Orchestration Agent",
        "orchestrator",
        (
            "현재 상황",
            "현업용 요약을 준비하지 못했습니다. 상세 기록을 확인해 주세요.",
        ),
        heading="현재 확인 결과",
    )


def _grounding_chat_message(audit: dict[str, Any]) -> dict[str, str]:
    """Show a concise business-reference check without exposing raw evidence."""
    state = str(audit.get("state", "unknown"))
    document_count = audit.get("document_count", 0)
    if state == "grounded":
        text = f"관련 업무 기준 문서 {document_count}건을 확인했습니다."
    elif state == "empty_repository":
        text = "확인할 업무 기준 문서가 아직 등록되지 않았습니다."
    elif state == "not_configured":
        text = "업무 기준 문서 확인이 설정되지 않았습니다."
    else:
        text = "관련 업무 기준을 확인하지 못했습니다."
    return {"sender": "업무 기준 확인", "kind": "system", "text": text}


def _human_approval_chat_message(draft: dict[str, Any]) -> dict[str, Any]:
    """Keep a mail draft in the chat while exposing only explicit actions."""
    message = _sectioned_chat_message(
        "Orchestration Agent",
        "orchestrator",
        ("검토 대상", draft.get("recipient_role")),
        ("제목", draft.get("subject")),
        ("본문", draft.get("body")),
        ("발송 전 확인 사항", draft.get("reason")),
        heading="확인 요청 메일 초안",
    )
    message["human_approval_request"] = {
        key: draft.get(key)
        for key in (
            "recipient_role",
            "subject",
            "body",
            "reason",
            "chat_summary",
            "display_summary_error",
        )
        if isinstance(draft.get(key), (str, bool))
    }
    return message


def _human_approval_fallback_chat_message() -> dict[str, Any]:
    """Offer an explicit in-chat review path when Outlook delivery is unavailable."""
    return {
        "sender": "Outlook",
        "kind": "system",
        "human_approval_fallback": True,
        "text": (
            "Outlook 연결 또는 인증에 실패해 메일은 발송되지 않았습니다. "
            "아래에서 사람 검토 완료를 직접 기록할 수 있습니다."
        ),
    }


def _human_approval_sent_chat_message() -> dict[str, Any]:
    """Keep the explicit human decision visible after Graph delivery succeeds."""
    return {
        "sender": "Human in the loop",
        "kind": "human",
        "text": (
            "사람 검토자가 발송을 명시적으로 승인했고 Microsoft Graph를 통해 메일을 전송했습니다."
        ),
    }


def _delivery_failed_for_chat_review(draft: dict[str, Any]) -> dict[str, Any]:
    """Keep the draft pending for an explicit in-chat review without retrying mail."""
    return {
        **draft,
        "state": "pending_chat_human_review",
        "delivery_result": {
            "state": "delivery_failed",
            "provider": "outlook",
            "failure_kind": "outlook_delivery",
        },
    }


def _human_reviewed_in_chat(draft: dict[str, Any]) -> dict[str, Any]:
    """Record the reviewer action only; this does not send mail or write ERP data."""
    return {
        **draft,
        "state": "human_reviewed",
        "review_result": {
            "state": "human_reviewed",
            "provider": "chat_human_in_the_loop",
        },
    }


def _default_outlook_recipient() -> str:
    """Use the connected Graph mailbox as the explicit-send destination."""
    return os.getenv("GRAPH_FORWARDER_B_MAILBOX", "").strip()


def _readable_value(value: Any, depth: int = 0) -> str:
    """Render LLM JSON as chat text without discarding structured findings."""
    indent = "  " * depth
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        items = []
        for item in value:
            rendered = _readable_value(item, depth + 1)
            if rendered:
                items.append(rendered)
        return "\n".join(f"{indent}- {item}" for item in items)
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            rendered = _readable_value(item, depth + 1)
            if not rendered:
                continue
            label = str(key).replace("_", " ")
            if isinstance(item, (dict, list)):
                lines.append(f"{indent}{label}:\n{rendered}")
            else:
                lines.append(f"{indent}{label}: {rendered}")
        return "\n".join(lines)
    return ""


def _append_status_once(events: list[dict[str, Any]], status: dict[str, Any]) -> None:
    """A2A streaming can replay its current status with later updates."""
    if not events or events[-1] != status:
        events.append(status)


def _section_body_html(text: str) -> str:
    """Render complete section text as paragraphs and real bullet lists."""
    parts: list[str] = []
    bullets: list[str] = []

    def flush_bullets() -> None:
        if bullets:
            parts.append("<ul>" + "".join(bullets) + "</ul>")
            bullets.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            bullets.append(f"<li>{html.escape(stripped[2:])}</li>")
        else:
            flush_bullets()
            parts.append(f"<p>{html.escape(stripped)}</p>")
    flush_bullets()
    return "".join(parts) or f"<p>{html.escape(text)}</p>"


def _tooltip_html(label: str, content: str) -> str:
    """Render an accessible text tooltip without adding another chat card."""
    if not content:
        return ""
    escaped_label = html.escape(label)
    escaped_content = html.escape(content, quote=True)
    return (
        '<span class="a2a-group-chat__evidence-tooltip" tabindex="0" '
        f'role="note" aria-label="{escaped_label}: {escaped_content}" '
        f'title="{escaped_content}" data-tooltip="{escaped_content}">'
        f'{escaped_label} <span aria-hidden="true">ⓘ</span></span>'
    )


def _evidence_tooltip_html(evidence: str) -> str:
    """Keep complete evidence accessible without turning it into a chat card."""
    return _tooltip_html("근거", evidence)


def _human_approval_request_body_html(message: dict[str, Any]) -> str | None:
    """Render draft details in a tooltip and only send/cancel controls in chat."""
    draft = message.get("human_approval_request")
    if not isinstance(draft, dict):
        return None

    detail_lines = [
        f"{label}: {_display_text(draft.get(key))}"
        for label, key in (
            ("검토 대상", "recipient_role"),
            ("제목", "subject"),
            ("본문", "body"),
            ("발송 전 확인 사항", "reason"),
        )
        if _display_text(draft.get(key))
    ]
    if not detail_lines:
        return None
    heading = message.get("heading")
    title = (
        f'<div class="a2a-group-chat__title">{html.escape(heading)}</div>'
        if isinstance(heading, str) and heading
        else ""
    )
    tooltip = _tooltip_html("내용 보기", "\n\n".join(detail_lines))
    summary = _display_text(draft.get("chat_summary"))
    summary_html = (
        f'<p class="a2a-group-chat__approval-summary">{html.escape(summary)}</p>'
        if summary
        else '<p class="a2a-group-chat__display-error">현업용 요약을 준비하지 못했습니다. 상세 내용을 확인해 주세요.</p>'
    )
    return (
        title
        + summary_html
        + '<div class="a2a-group-chat__approval-actions">'
        + tooltip
        + '<button type="button" class="a2a-group-chat__approval-button '
        'a2a-group-chat__approval-button--send" data-a2a-approval-action="send">'
        "Outlook 메일 발송</button>"
        + '<button type="button" class="a2a-group-chat__approval-button '
        'a2a-group-chat__approval-button--cancel" data-a2a-approval-action="cancel">'
        "발송하지 않음</button>" + "</div>"
    )


def _team_review_body_html(message: dict[str, Any]) -> str | None:
    """Render a Team synthesis as one compact card with evidence on demand."""
    details = message.get("team_result")
    if not isinstance(details, dict):
        return None
    summary = details.get("summary")
    next_action = details.get("next_action")
    evidence = details.get("evidence")
    chat_summary = details.get("chat_summary")
    if not all(isinstance(value, str) for value in (summary, next_action, evidence)):
        return None

    title = message.get("heading")
    heading = (
        f'<div class="a2a-group-chat__title">{html.escape(title)}</div>'
        if isinstance(title, str) and title
        else ""
    )
    summary_html = (
        _section_body_html(chat_summary)
        if isinstance(chat_summary, str) and chat_summary
        else '<p class="a2a-group-chat__display-error">현업용 요약을 준비하지 못했습니다. 상세 내용을 확인해 주세요.</p>'
    )
    next_action_html = (
        '<div class="a2a-group-chat__team-next">'
        "<span>다음 조치</span>"
        f"{_section_body_html(next_action)}"
        "</div>"
        if next_action and isinstance(chat_summary, str) and chat_summary
        else ""
    )
    detail_text = "\n\n".join(
        value
        for value in (
            f"팀 요약: {summary}" if summary else "",
            f"근거: {evidence}" if evidence else "",
            f"다음 조치: {next_action}" if next_action else "",
        )
        if value
    )
    evidence_tooltip = _tooltip_html("상세 보기", detail_text) if detail_text else ""
    metadata = (
        f'<div class="a2a-group-chat__team-meta">{evidence_tooltip}</div>'
        if evidence_tooltip
        else ""
    )
    return (
        heading
        + '<section class="a2a-group-chat__team-card">'
        + '<div class="a2a-group-chat__team-summary">'
        + "<span>검토 결과</span>"
        + summary_html
        + "</div>"
        + next_action_html
        + metadata
        + "</section>"
    )


def _format_financial_value(value: Any, suffix: str = "") -> str:
    """Format a scalar calculation result for its chat table."""
    if isinstance(value, bool) or value is None:
        return "-"
    if isinstance(value, int):
        rendered = f"{value:,}"
    elif isinstance(value, float):
        rendered = f"{value:,.2f}".rstrip("0").rstrip(".")
    else:
        rendered = str(value).strip()
    return f"{rendered}{suffix}" if rendered and rendered != "-" else "-"


def _profitability_table_html(calculation: dict[str, Any]) -> str:
    """Render one compact scenario table and a collapsible monthly detail table."""
    summaries = calculation.get("scenario_summaries")
    monthly = calculation.get("monthly_forecasts")
    if not isinstance(summaries, list) or not isinstance(monthly, list):
        return ""

    summary_rows = []
    for row in summaries:
        if not isinstance(row, dict):
            continue
        summary_rows.append(
            "<tr>"
            f'<th scope="row">{html.escape(str(row.get("scenario", "-")))}</th>'
            "<td>"
            f"{_format_financial_value(row.get('average_exchange_rate_krw_per_usd'))} KRW/USD"
            "<br>"
            f"{_format_financial_value(row.get('average_material_price_usd_per_kg'))} USD/kg"
            "</td>"
            f"<td>{_format_financial_value(row.get('revenue_krw'))} KRW</td>"
            f"<td>{_format_financial_value(row.get('total_cost_krw'))} KRW</td>"
            "<td>"
            f"{_format_financial_value(row.get('operating_profit_krw'))} KRW"
            "<br>"
            f"{_format_financial_value(row.get('operating_margin_pct'), '%')}"
            "</td>"
            "<td>"
            f"{_format_financial_value(row.get('bep_quantity_ea'))} EA"
            "<br>"
            f"{_format_financial_value(row.get('bep_revenue_krw'))} KRW"
            "</td>"
            "</tr>"
        )

    monthly_rows = []
    for row in monthly:
        if not isinstance(row, dict):
            continue
        monthly_rows.append(
            "<tr>"
            "<td>"
            f"{html.escape(str(row.get('scenario', '-')))}"
            "<br>"
            f"{html.escape(str(row.get('forecast_period', '-')))}"
            "</td>"
            "<td>"
            f"{_format_financial_value(row.get('exchange_rate_krw_per_usd'))} KRW/USD"
            "<br>"
            f"{_format_financial_value(row.get('material_price_usd_per_kg'))} USD/kg"
            "</td>"
            f"<td>{_format_financial_value(row.get('forecast_quantity_ea'))} EA</td>"
            f"<td>{_format_financial_value(row.get('unit_cogs_krw'))} KRW</td>"
            f"<td>{_format_financial_value(row.get('total_cost_krw'))} KRW</td>"
            "<td>"
            f"{_format_financial_value(row.get('revenue_krw'))} KRW"
            "<br>"
            f"{_format_financial_value(row.get('operating_profit_krw'))} KRW"
            "</td>"
            "<td>"
            f"{_format_financial_value(row.get('bep_quantity_ea'))} EA"
            "<br>"
            f"{_format_financial_value(row.get('bep_revenue_krw'))} KRW"
            "</td>"
            "</tr>"
        )

    if not summary_rows:
        return ""
    horizon = calculation.get("calculation_basis", {})
    if isinstance(horizon, dict):
        horizon_label = _display_text(horizon.get("forecast_horizon"))
    else:
        horizon_label = ""
    subtitle = f"<span>{html.escape(horizon_label)}</span>" if horizon_label else ""
    return (
        '<section class="a2a-group-chat__profitability">'
        '<div class="a2a-group-chat__profitability-heading">'
        "<b>시나리오별 사업성</b>"
        + subtitle
        + "</div>"
        + '<table class="a2a-group-chat__financial-table">'
        + "<thead><tr><th>시나리오</th><th>평균 환율 · 원자재</th><th>매출</th><th>총원가</th><th>손익 · 마진</th><th>분기 BEP 수량 · 매출</th></tr></thead>"
        + f"<tbody>{''.join(summary_rows)}</tbody></table>"
        + (
            '<details class="a2a-group-chat__profitability-detail">'
            f"<summary>월별 예상원가 · BEP 보기 ({len(monthly_rows)}건)</summary>"
            '<table class="a2a-group-chat__financial-table a2a-group-chat__financial-table--monthly">'
            + "<thead><tr><th>시나리오 · 월</th><th>환율 · 원자재</th><th>예상 판매량</th><th>단위 COGS</th><th>총원가</th><th>매출 · 손익</th><th>월 BEP 수량 · 매출</th></tr></thead>"
            + f"<tbody>{''.join(monthly_rows)}</tbody></table></details>"
            if monthly_rows
            else ""
        )
        + '<p class="a2a-group-chat__profitability-boundary">로컬 CSV 스냅샷 기준의 읽기 전용 계산입니다.</p>'
        + "</section>"
    )


def _subagent_review_body_html(message: dict[str, Any]) -> str | None:
    """Render a Sub-agent result as one card, with evidence behind a tooltip."""
    details = message.get("subagent_result")
    if not isinstance(details, dict):
        return None

    finding = details.get("finding")
    next_input = details.get("next_input")
    evidence = details.get("evidence")
    chat_summary = details.get("chat_summary")
    tool_names = details.get("tool_names")
    profitability_calculation = details.get("profitability_calculation")
    if not all(
        isinstance(value, str)
        for value in (finding or "", next_input or "", evidence or "")
    ) or not isinstance(tool_names, list):
        return None

    title = message.get("heading")
    heading = (
        f'<div class="a2a-group-chat__title">{html.escape(title)}</div>'
        if isinstance(title, str) and title
        else ""
    )
    review = (
        _section_body_html(chat_summary)
        if isinstance(chat_summary, str) and chat_summary
        else '<p class="a2a-group-chat__display-error">현업용 요약을 준비하지 못했습니다. 상세 내용을 확인해 주세요.</p>'
    )
    detail_text = "\n\n".join(
        value
        for value in (
            f"검토 결과: {finding}" if finding else "",
            f"근거: {evidence}" if evidence else "",
            f"추가 확인 사항: {next_input}" if next_input else "",
            f"참고 정보: {', '.join(tool_names)}" if tool_names else "",
        )
        if value
    )
    evidence_html = _tooltip_html("상세 보기", detail_text) if detail_text else ""
    metadata = (
        f'<div class="a2a-group-chat__subagent-meta">{evidence_html}</div>'
        if evidence_html
        else ""
    )
    profitability_html = (
        _profitability_table_html(profitability_calculation)
        if isinstance(profitability_calculation, dict)
        else ""
    )
    return (
        heading
        + '<section class="a2a-group-chat__subagent-card">'
        + '<div class="a2a-group-chat__subagent-result">'
        + "<span>검토 결과</span>"
        + review
        + "</div>"
        + profitability_html
        + metadata
        + "</section>"
    )


def _message_body_html(message: dict[str, Any]) -> str:
    """Render structured message sections without dropping any text."""
    if message.get("human_approval_fallback") is True:
        text = html.escape(str(message.get("text") or ""))
        return (
            f"<span>{text}</span>"
            '<button type="button" class="a2a-group-chat__hitl-fallback-button" '
            "data-a2a-human-review-complete>Human in the loop으로 검토 완료</button>"
        )
    if approval_body := _human_approval_request_body_html(message):
        return approval_body
    if team_body := _team_review_body_html(message):
        return team_body
    if subagent_body := _subagent_review_body_html(message):
        return subagent_body
    sections = message.get("sections")
    if not isinstance(sections, list):
        return html.escape(message.get("text", "")).replace("\n", "<br>")
    heading = message.get("heading")
    title = (
        f'<div class="a2a-group-chat__title">{html.escape(heading)}</div>'
        if isinstance(heading, str) and heading
        else ""
    )
    blocks = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        label, text = section.get("label"), section.get("text")
        if isinstance(label, str) and isinstance(text, str) and text:
            blocks.append(
                '<section class="a2a-group-chat__section">'
                f'<div class="a2a-group-chat__section-label">{html.escape(label)}</div>'
                f'<div class="a2a-group-chat__section-body">{_section_body_html(text)}</div>'
                "</section>"
            )
    return title + "".join(blocks)


def _chat_message_html(message: dict[str, Any]) -> str:
    """Render one immutable chat bubble that the browser can append safely."""
    raw_sender = str(message.get("sender", "A2A Agent"))
    sender = html.escape(raw_sender)
    body = _message_body_html(message)
    kind = str(message.get("kind", "agent"))
    if kind == "system":
        return f'<div class="a2a-group-chat__system">{body}</div>'
    bubble_class = (
        " a2a-group-chat__bubble--streaming" if message.get("streaming") else ""
    )
    return f"""<div class="a2a-group-chat__row a2a-group-chat__row--{html.escape(kind)}">
      <div class="a2a-group-chat__avatar">{_message_avatar_html(raw_sender, kind)}</div>
      <div><div class="a2a-group-chat__sender">{sender}</div><div class="a2a-group-chat__bubble{bubble_class}">{body}</div></div>
    </div>"""


def _typing_bubbles_html(typing_agents: list[str] | None = None) -> str:
    """Render only the transient typing indicators."""
    bubbles = []
    for agent in typing_agents or []:
        raw_sender = str(agent)
        sender = html.escape(raw_sender)
        bubbles.append(
            f"""<div class="a2a-group-chat__row a2a-group-chat__row--typing">
              <div class="a2a-group-chat__avatar">{_message_avatar_html(raw_sender, "typing")}</div>
              <div><div class="a2a-group-chat__sender">{sender}</div><div class="a2a-group-chat__typing" role="status" aria-live="polite" aria-label="응답 생성 중"><i></i><i></i><i></i></div></div>
            </div>"""
        )
    return "".join(bubbles)


def _chat_payload_html(
    messages: list[dict[str, Any]], typing_agents: list[str] | None = None
) -> str:
    """Send append-only chat fragments through an invisible Gradio output."""
    payload = {
        "message_count": len(messages),
        "messages": [_chat_message_html(message) for message in messages],
        "typing_html": _typing_bubbles_html(typing_agents),
    }
    serialized = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return (
        '<div class="a2a-group-chat__payload-data" data-payload="'
        f"{html.escape(serialized, quote=True)}"
        '"></div>'
    )


_ROOM_AVATAR_ICONS = {
    "fnb": (
        '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true" focusable="false">'
        '<path d="M7 3v7M10 3v7M7 7h3M8.5 10v11M16 3v18M16 3c3 1.5 3 6.5 0 8"/>'
        "</svg>"
    ),
}


_MESSAGE_AVATAR_ICONS = {
    "department": (
        '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true" focusable="false">'
        '<path d="M4 21V5.5A2.5 2.5 0 0 1 6.5 3h7A2.5 2.5 0 0 1 16 5.5V21M2 21h20M8 7h1M12 7h1M8 11h1M12 11h1M9 21v-5h2v5"/>'
        "</svg>"
    ),
    "orchestrator": _brand_avatar_html("sap_logo.png", "SAP", "sap"),
    "agent": _brand_avatar_html("joule.png", "Joule", "joule"),
    "human": (
        '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true" focusable="false">'
        '<circle cx="12" cy="8" r="3"/><path d="M5 21a7 7 0 0 1 14 0M17 5l1.3 1.3L21 3.7"/>'
        "</svg>"
    ),
    "mail": (
        '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true" focusable="false">'
        '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/>'
        "</svg>"
    ),
}


def _message_avatar_html(sender: str, kind: str) -> str:
    """Map every chat actor to a fixed role icon instead of an initial letter."""
    normalized = f"{sender} {kind}".lower()
    if kind == "field" or "요청부서" in normalized:
        icon = "department"
    elif "orchestration" in normalized or kind == "orchestrator":
        icon = "orchestrator"
    elif "outlook" in normalized or "mail" in normalized:
        icon = "mail"
    elif "human" in normalized or "reviewer" in normalized or "사람" in normalized:
        icon = "human"
    else:
        icon = "agent"
    return _MESSAGE_AVATAR_ICONS[icon]


def _room_avatar_html(icon: str) -> str:
    """Return a fixed, decorative icon; arbitrary HTML is never accepted."""
    return _ROOM_AVATAR_ICONS.get(icon, _ROOM_AVATAR_ICONS["fnb"])


def _group_chat_html(
    messages: list[dict[str, Any]],
    typing_agents: list[str] | None = None,
    *,
    room_title: str = "F&amp;B 업무 협업방",
    room_subtitle: str = "실시간 협업 대화",
    avatar_icon: str = "fnb",
    status: str = "연결됨",
    extra_class: str = "",
) -> str:
    """Render the stable A2A chat shell; later events append in the browser."""
    bubbles = "".join(_chat_message_html(message) for message in messages)
    typing = _typing_bubbles_html(typing_agents)
    return (
        f'<section class="a2a-group-chat {extra_class}" data-message-count="{len(messages)}">'
        '<header class="a2a-group-chat__header">'
        '<div class="a2a-group-chat__room-title">'
        f'<span class="a2a-group-chat__room-avatar">{_room_avatar_html(avatar_icon)}</span>'
        f"<div><b>{room_title}</b><span>{room_subtitle}</span></div>"
        "</div>"
        f'<span class="a2a-group-chat__room-status">{html.escape(status)}</span>'
        "</header>"
        f'<div class="a2a-group-chat__messages">{bubbles}<div class="a2a-group-chat__typing-container">{typing}</div></div></section>'
    )


def _artifact_chat_message(
    record: dict[str, Any], labels: dict[str, str]
) -> dict[str, Any]:
    """Turn one received A2A artifact into a human-readable group-chat post."""
    producer = str(record.get("producer", "A2A Agent"))
    sender = labels.get(producer, producer)
    artifact = record.get("artifact", {})
    sections = _team_sections(artifact) if isinstance(artifact, dict) else []
    details = _team_display_details(artifact) if isinstance(artifact, dict) else {}
    if not sections and not any(details.values()):
        return {
            "sender": sender,
            "kind": "agent",
            "text": "검토 결과를 공유했습니다.",
        }
    message = _sectioned_chat_message(
        sender,
        "agent",
        *((section["label"], section["text"]) for section in sections),
        heading="팀 검토 결과",
    )
    # Persist the complete evidence in the text/log, but keep the chat bubble compact.
    message["team_result"] = details
    return message


def _scenario_card_html(title: str, department: str, request: str) -> str:
    """Render the full request context without making the card itself a button."""
    return (
        '<article class="a2a-scenario-card__body">'
        f"<h4>{html.escape(title)}</h4>"
        '<section class="a2a-scenario-card__department">'
        "<span>요청 부서</span>"
        f"<strong>{html.escape(department)}</strong>"
        "</section>"
        '<section class="a2a-scenario-card__request">'
        f"<p>{html.escape(request)}</p>"
        "</section>"
        "</article>"
    )


def _conversation_history_for_handoff(
    messages: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """Return semantic user/assistant turns, excluding internal A2A event bubbles."""
    history: list[dict[str, str]] = []
    for message in messages or []:
        if not isinstance(message, dict) or message.get("kind") != "field":
            continue
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        history.append(
            {
                "role": "assistant" if message.get("heading") else "user",
                "content": text.strip(),
            }
        )
    return history


def build_a2a_ui(settings: Settings | None = None) -> gr.Blocks:
    gr.set_static_paths(_AVATAR_ASSET_DIR)
    settings = settings or load_settings()
    default_outlook_recipient = _default_outlook_recipient()

    def run_workflow(
        request: str | None,
        previous_messages: list[dict[str, Any]] | None = None,
        request_department: str | None = None,
        previous_approvals: list[dict[str, Any]] | None = None,
        previous_outcome: dict[str, Any] | None = None,
    ):
        clean_request = request.strip() if isinstance(request, str) else ""
        if not clean_request:
            raise gr.Error("요청을 입력하세요.")
        requester_label = _requester_label(request_department)
        conversation_history = _conversation_history_for_handoff(previous_messages)
        labels = {agent["agent_id"]: agent["agent_label"] for agent in list_agents()}
        event_log, middleware = [], []
        chat_messages = list(previous_messages or [])
        typing_agents: set[str] = set()
        rendered_delegations: set[str] = set()
        rendered_subagent_artifacts: set[tuple[str, str]] = set()
        pending_approvals = [
            draft for draft in (previous_approvals or []) if isinstance(draft, dict)
        ]

        def workflow_output(outcome: dict[str, Any] | None = None):
            return (
                _chat_payload_html(chat_messages, sorted(typing_agents)),
                chat_messages,
                pending_approvals,
                outcome if outcome is not None else previous_outcome,
            )

        try:
            for event in run_handoff_stream(
                clean_request,
                settings=settings,
                conversation_history=conversation_history,
            ):
                kind = event["type"]
                if kind == "field_handoff_received":
                    event_log.append({"event": "field_handoff_received"})
                    chat_messages.append(
                        {
                            "sender": requester_label,
                            "kind": "field",
                            "text": clean_request,
                        }
                    )
                elif kind == "orchestration_started":
                    # The Orchestration LLM performs both an Observe and a Decide
                    # call.  Keep its transient chat bubble visible throughout
                    # either call, including while a tool is being considered.
                    typing_agents.add("Orchestration Agent")
                    event_log.append(
                        {
                            "event": "orchestration_started",
                            "step": event.get("step"),
                            "phase": event.get("phase"),
                        }
                    )
                elif kind == "grounding_started":
                    event_log.append({"event": "grounding_started"})
                elif kind == "grounding_context":
                    audit = event["audit"]
                    middleware.append(
                        {"name": "grounding_context_collected", "data": audit}
                    )
                    event_log.append(
                        {
                            "event": "grounding_context",
                            "state": audit.get("state"),
                            "document_count": audit.get("document_count"),
                        }
                    )
                    chat_messages.append(_grounding_chat_message(audit))
                elif kind == "orchestration_observation":
                    # An observation is streamed between two Orchestration LLM
                    # calls, so its loading indicator must stay visible.
                    typing_agents.add("Orchestration Agent")
                    observation = event["observation"]
                    middleware.append(
                        {
                            "name": "orchestration_observation",
                            "data": {
                                "step": event.get("step"),
                                "observation": observation,
                            },
                        }
                    )
                    event_log.append(
                        {
                            "event": "orchestration_observation",
                            "step": event.get("step"),
                        }
                    )
                    chat_messages.append(_observation_chat_message(observation))
                elif kind == "orchestration_decision":
                    typing_agents.discard("Orchestration Agent")
                    target = event["decision"]["target_agent_id"]
                    if target != "complete":
                        chat_messages.append(_task_plan_chat_message(event["decision"]))
                        chat_messages.append(
                            _orchestration_decision_chat_message(
                                event["decision"], _actor_name(target, labels)
                            )
                        )
                    else:
                        chat_messages.append(
                            _orchestration_completion_chat_message(event["decision"])
                        )
                elif kind == "team_handoff_started":
                    team_label = _actor_name(str(event.get("agent_id", "")), labels)
                    if team_label:
                        typing_agents.add(team_label)
                    event_log.append(
                        {
                            "event": "team_handoff_started",
                            "step": event.get("step"),
                            "agent_id": event.get("agent_id"),
                        }
                    )
                elif kind == "human_approval_requested":
                    draft = event.get("draft")
                    if isinstance(draft, dict):
                        pending_approvals.append(draft)
                        chat_messages.append(_human_approval_chat_message(draft))
                        event_log.append(
                            {
                                "event": "human_approval_requested",
                                "approval_id": draft.get("approval_id"),
                            }
                        )
                elif kind == "middleware":
                    middleware.append({"name": event["name"], "data": event["data"]})
                    event_log.append({"event": "middleware." + event["name"]})
                elif kind == "field_response_delivered":
                    chat_messages.append(
                        _field_response_chat_message(
                            event["message"], request_department
                        )
                    )
                    event_log.append(
                        {
                            "event": "field_response_delivered",
                            "source": event["source"],
                            "target": event["target"],
                        }
                    )
                elif kind == "a2a_task_update":
                    agent_id, status = event["agent_id"], _decode_status(event["task"])
                    status_event = str(status.get("event", "task_status"))
                    team_id = str(status.get("team") or agent_id)
                    subagent = status.get("agent")
                    _append_status_once(event_log, status)
                    team_label = _actor_name(team_id, labels)
                    handoff_id = str(event.get("handoff", {}).get("handoff_id", ""))
                    if status_event in {"team_started", "delegation_started"}:
                        typing_agents.add(team_label)
                    elif status_event == "delegation_selected":
                        typing_agents.discard(team_label)
                        if handoff_id not in rendered_delegations:
                            chat_messages.append(
                                _delegation_chat_message(status, labels)
                            )
                            rendered_delegations.add(handoff_id)
                    elif status_event == "subagent_started" and isinstance(
                        subagent, str
                    ):
                        typing_agents.add(f"{team_label} · {subagent}")
                    elif status_event == "subagent_completed" and isinstance(
                        subagent, str
                    ):
                        sender = f"{team_label} · {subagent}"
                        typing_agents.discard(sender)
                        artifact_key = (handoff_id, subagent)
                        message = _subagent_chat_message(status, labels)
                        if (
                            message is not None
                            and artifact_key not in rendered_subagent_artifacts
                        ):
                            chat_messages.append(message)
                            rendered_subagent_artifacts.add(artifact_key)
                    elif status_event == "synthesis_started":
                        typing_agents.add(team_label)
                    elif status_event in {"synthesis_completed", "team_completed"}:
                        typing_agents.discard(team_label)
                elif kind == "artifact_received":
                    artifact_message = _artifact_chat_message(event["record"], labels)
                    typing_agents.discard(artifact_message["sender"])
                    chat_messages.append(artifact_message)
                    event_log.append({"event": "artifact_received"})
                elif kind == "complete":
                    outcome = event["result"]
                    middleware = outcome.get("middleware", middleware)
                    termination = outcome.get("termination") or {}
                    typing_agents.clear()
                    outcome["log"] = persist_a2a_conversation(
                        {
                            "status": termination.get("state", "completed"),
                            "request": clean_request,
                            "context_id": outcome.get("context_id"),
                            "conversation": chat_messages,
                            "event_log": event_log,
                            "middleware": middleware,
                            "outcome": outcome,
                        }
                    )
                    yield workflow_output(outcome)
                    return
                yield workflow_output()
        except Exception as error:
            persist_a2a_conversation(
                {
                    "status": "failed",
                    "request": clean_request,
                    "conversation": chat_messages,
                    "event_log": event_log,
                    "middleware": middleware,
                    "error": str(error),
                }
            )
            raise gr.Error(str(error)) from error

    def approval_output(
        drafts: list[dict[str, Any]] | None,
        messages: list[dict[str, Any]] | None,
    ):
        normalized = list(drafts or [])
        return (
            _chat_payload_html(list(messages or [])),
            list(messages or []),
            normalized,
        )

    def reset_chat():
        """Clear only this browser session's conversation and pending approval."""
        return _chat_payload_html([]), [], [], None

    def pause_chat():
        """Cancel the active streamed handoff while keeping messages on screen."""
        return None

    def send_approved_email(
        drafts: list[dict[str, Any]] | None,
        messages: list[dict[str, Any]] | None,
    ):
        normalized = list(drafts or [])
        pending_index = next(
            (
                index
                for index in range(len(normalized) - 1, -1, -1)
                if isinstance(normalized[index], dict)
                and normalized[index].get("state") == "pending_human_approval"
            ),
            None,
        )
        if pending_index is None:
            return approval_output(normalized, messages)
        draft = normalized[pending_index]
        try:
            result = send_outlook_mail(
                settings,
                draft,
                recipients=default_outlook_recipient,
                subject=str(draft.get("subject") or ""),
                body=str(draft.get("body") or ""),
            )
        except OutlookMailError:
            # A transport or authentication failure must never become an implicit
            # approval, retry, or business decision.  It only changes the channel
            # for the already-requested human review to an explicit chat action.
            fallback_draft = _delivery_failed_for_chat_review(draft)
            normalized[pending_index] = fallback_draft
            fallback_message = _human_approval_fallback_chat_message()
            updated_messages = [*(messages or []), fallback_message]
            fallback_result = dict(fallback_draft["delivery_result"])
            persist_human_approval_action(
                fallback_draft, fallback_result, fallback_message
            )
            return approval_output(
                normalized,
                updated_messages,
            )

        updated_draft = {**draft, "state": "sent", "send_result": result}
        normalized[pending_index] = updated_draft
        mail_message = _human_approval_sent_chat_message()
        updated_messages = [
            *(messages or []),
            mail_message,
        ]
        persist_human_approval_action(updated_draft, result, mail_message)
        return approval_output(normalized, updated_messages)

    def complete_chat_human_review(
        drafts: list[dict[str, Any]] | None,
        messages: list[dict[str, Any]] | None,
    ):
        """Record manual completion after the chat fallback button is selected."""
        normalized = list(drafts or [])
        pending_index = next(
            (
                index
                for index in range(len(normalized) - 1, -1, -1)
                if isinstance(normalized[index], dict)
                and normalized[index].get("state") == "pending_chat_human_review"
            ),
            None,
        )
        if pending_index is None:
            return approval_output(normalized, messages)

        reviewed_draft = _human_reviewed_in_chat(normalized[pending_index])
        normalized[pending_index] = reviewed_draft
        result = dict(reviewed_draft["review_result"])
        review_message = {
            "sender": "Human in the loop",
            "kind": "system",
            "text": (
                "사람 검토 결과가 기록됐습니다. Outlook 메일은 발송하지 않았습니다."
            ),
        }
        updated_messages = [*(messages or []), review_message]
        persist_human_approval_action(reviewed_draft, result, review_message)
        return approval_output(
            normalized,
            updated_messages,
        )

    def cancel_email_approval(
        drafts: list[dict[str, Any]] | None,
        messages: list[dict[str, Any]] | None,
    ):
        normalized = list(drafts or [])
        pending_index = next(
            (
                index
                for index in range(len(normalized) - 1, -1, -1)
                if isinstance(normalized[index], dict)
                and normalized[index].get("state") == "pending_human_approval"
            ),
            None,
        )
        if pending_index is None:
            return approval_output(normalized, messages)
        draft = normalized[pending_index]
        cancelled = {**draft, "state": "cancelled"}
        normalized[pending_index] = cancelled
        result = {"state": "cancelled", "provider": "human_reviewer"}
        cancel_message = {
            "sender": "Outlook",
            "kind": "system",
            "text": "검토자가 메일 초안을 취소했습니다.",
        }
        persist_human_approval_action(cancelled, result, cancel_message)
        updated_messages = [
            *(messages or []),
            cancel_message,
        ]
        return approval_output(normalized, updated_messages)

    css = """
    .orchestration-view{padding:16px;border:1px solid #d7e1ee;border-radius:14px;background:#f8fbff}.orchestration-view h3{margin:0 0 12px;color:#174ea6}.actor-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.actor{padding:11px;border:1px solid #d9e2f3;border-radius:10px;background:#fff}.actor b{display:block;color:#174ea6;font-size:13px}.actor span{display:inline-block;margin-top:6px;padding:2px 6px;border-radius:99px;background:#eef1f4;color:#5f6368;font-size:10px}.actor p{margin:7px 0 0;color:#4b5f78;font-size:11px}.actor-working{border:2px solid #f0a500}.actor-working span{background:#fff1cc;color:#9a6700}.actor-completed{border-color:#a9d8b6}.actor-completed span{background:#e8f5e9;color:#137333}.actor-selected{border-color:#9fc3f5}.flow-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px;padding-top:12px;border-top:1px solid #d9e2f3;font-size:12px;color:#374151}.flow-grid ul{margin:6px 0;padding-left:18px}.agent-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.agent-card{padding:10px;border:1px solid #d9e2f3;border-radius:9px;font-size:12px}.agent-card p{margin:6px 0;color:#4b5f78}.agent-card small{color:#667085}.a2a-chat-shell{gap:0!important;overflow:hidden;border:1px solid #92aeca;border-radius:14px;background:#b2c7d9}.a2a-chat-shell #a2a-group-chat{position:relative;margin:0!important;border:0!important}.a2a-chat-shell .a2a-group-chat{border:0;border-radius:0}.a2a-chat-composer{margin:0!important;padding:8px 10px 10px;background:#f6f8fa;border:0!important;border-top:1px solid #92aeca!important}.a2a-chat-composer>div{margin:0!important}.a2a-chat-composer textarea{min-height:42px!important;background:#fff}.a2a-group-chat{border:1px solid #92aeca;border-radius:14px;overflow:hidden;background:#b2c7d9;overflow-anchor:none}.a2a-group-chat__header{display:flex;justify-content:space-between;gap:8px;padding:11px 14px;background:#91abc2;color:#fff;font-size:13px}.a2a-group-chat__header span{font-size:11px;opacity:.95}.a2a-group-chat__messages{height:520px;overflow-y:auto;padding:14px;overflow-anchor:none}.a2a-group-chat__new-message{position:absolute;z-index:3;bottom:14px;left:50%;transform:translateX(-50%);padding:7px 12px;border:0;border-radius:999px;background:#425f79;color:#fff;font-size:12px;font-weight:700;box-shadow:0 2px 8px rgba(40,58,74,.28);cursor:pointer}.a2a-group-chat__new-message:hover{background:#314b64}.a2a-group-chat__row{display:flex;gap:8px;margin:0 0 12px;align-items:flex-start}.a2a-group-chat__avatar{display:grid;place-items:center;flex:none;width:31px;height:31px;border-radius:50%;background:#fff;color:#4d657d;font-size:12px;font-weight:700}.a2a-group-chat__sender{margin:1px 0 4px;color:#314b64;font-size:11px;font-weight:700}.a2a-group-chat__bubble{max-width:680px;padding:9px 11px;border-radius:3px 12px 12px 12px;background:#fff;color:#252525;font-size:13px;line-height:1.5;box-shadow:0 1px 1px rgba(0,0,0,.08)}.a2a-group-chat__bubble--streaming::after{content:"▍";display:inline-block;margin-left:2px;color:#4d657d;animation:a2a-blink .75s step-end infinite}.a2a-group-chat__row--typing .a2a-group-chat__typing{display:flex;gap:4px;padding:10px 12px;border-radius:3px 12px 12px 12px;background:#fff}.a2a-group-chat__typing i{width:6px;height:6px;border-radius:50%;background:#8093a6;animation:a2a-typing 1.1s infinite}.a2a-group-chat__typing i:nth-child(2){animation-delay:.16s}.a2a-group-chat__typing i:nth-child(3){animation-delay:.32s}@keyframes a2a-typing{0%,60%,100%{transform:translateY(0);opacity:.42}30%{transform:translateY(-4px);opacity:1}}@keyframes a2a-blink{50%{opacity:0}}.a2a-group-chat__row--orchestrator{justify-content:flex-end}.a2a-group-chat__row--orchestrator .a2a-group-chat__avatar{order:2;background:#fee500;color:#5b4d00}.a2a-group-chat__row--orchestrator .a2a-group-chat__bubble{border-radius:12px 3px 12px 12px;background:#fee500}.a2a-group-chat__row--field .a2a-group-chat__avatar{background:#dfeeff;color:#174ea6}.a2a-group-chat__system{width:max-content;max-width:90%;margin:5px auto 12px;padding:5px 9px;border-radius:999px;background:rgba(65,88,111,.32);color:#fff;font-size:11px;text-align:center}@media(max-width:700px){.flow-grid,.agent-cards{grid-template-columns:1fr}.a2a-group-chat__header span{display:none}.a2a-group-chat__messages{height:440px}.a2a-group-chat__bubble{max-width:calc(100vw - 130px)}}
    """
    css += """
    .a2a-chat-payload{display:none!important}.a2a-chat-shell{border-color:#c4d0dc;background:#edf2f6}.a2a-chat-composer{background:#f7f9fb!important;border-top-color:#c4d0dc!important}.a2a-group-chat{border-color:#c4d0dc;background:#edf2f6}.a2a-group-chat__header{background:#5d7489}.a2a-group-chat__messages{box-sizing:border-box;width:100%;max-width:980px;margin:0 auto;padding:16px 18px}.a2a-group-chat__row{margin-bottom:16px}.a2a-group-chat__row>div:last-child{max-width:min(720px,calc(100% - 42px))}.a2a-group-chat__avatar{box-shadow:0 1px 2px rgba(40,58,74,.15)}.a2a-group-chat__sender{margin-bottom:5px;font-size:12px}.a2a-group-chat__bubble{box-sizing:border-box;max-width:100%;padding:12px;border:1px solid #d7e0e8;border-radius:4px 13px 13px 13px;color:#25313d;line-height:1.55;box-shadow:0 1px 2px rgba(40,58,74,.08)}.a2a-group-chat__title{margin:0 0 9px;color:#41576b;font-size:11px;font-weight:800;letter-spacing:.02em}.a2a-group-chat__section{margin:8px 0 0;padding:8px 9px;border-radius:8px;background:#f5f8fb}.a2a-group-chat__section:first-of-type{margin-top:0}.a2a-group-chat__section-label{margin-bottom:4px;color:#587086;font-size:10px;font-weight:800;letter-spacing:.02em}.a2a-group-chat__section-body p{margin:0}.a2a-group-chat__section-body ul{margin:0;padding-left:17px}.a2a-group-chat__section-body li+li{margin-top:3px}.a2a-group-chat__subagent-card{padding:10px;border:1px solid #d8e3eb;border-radius:9px;background:#f7fafc}.a2a-group-chat__subagent-result>span,.a2a-group-chat__subagent-next>span,.a2a-group-chat__subagent-meta-label{display:block;margin-bottom:4px;color:#587086;font-size:10px;font-weight:800;letter-spacing:.02em}.a2a-group-chat__subagent-result p,.a2a-group-chat__subagent-next p{margin:0}.a2a-group-chat__subagent-result ul,.a2a-group-chat__subagent-next ul{margin:0;padding-left:17px}.a2a-group-chat__subagent-next{margin-top:9px;padding-top:9px;border-top:1px solid #e0e8ef}.a2a-group-chat__subagent-meta{display:flex;flex-wrap:wrap;gap:7px 10px;align-items:center;margin-top:10px;padding-top:9px;border-top:1px solid #e0e8ef}.a2a-group-chat__subagent-tools{display:flex;flex-wrap:wrap;gap:5px;align-items:center}.a2a-group-chat__subagent-tools .a2a-group-chat__subagent-meta-label{margin:0}.a2a-group-chat__tool-chips{display:flex;flex-wrap:wrap;gap:4px}.a2a-group-chat__tool-chip{padding:2px 6px;border:1px solid #cbdce9;border-radius:999px;background:#fff;color:#46657d;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;line-height:1.35;overflow-wrap:anywhere}.a2a-group-chat__evidence-tooltip{position:relative;display:inline-flex;align-items:center;gap:3px;padding:2px 6px;border:1px solid #cbdce9;border-radius:999px;background:#fff;color:#46657d;font-size:10px;font-weight:800;line-height:1.35;cursor:help;outline:none}.a2a-group-chat__evidence-tooltip:focus-visible{box-shadow:0 0 0 2px #8db5d8}.a2a-group-chat__evidence-tooltip::after{position:absolute;z-index:4;bottom:calc(100% + 7px);left:0;display:block;width:max-content;max-width:min(360px,calc(100vw - 84px));padding:8px 9px;border-radius:8px;background:#314b64;color:#fff;content:attr(data-tooltip);font-size:11px;font-weight:400;line-height:1.45;white-space:pre-wrap;visibility:hidden;opacity:0;pointer-events:none;box-shadow:0 4px 14px rgba(40,58,74,.22);transition:opacity .12s ease}.a2a-group-chat__evidence-tooltip:hover::after,.a2a-group-chat__evidence-tooltip:focus::after{visibility:visible;opacity:1}.a2a-group-chat__row--orchestrator .a2a-group-chat__avatar{background:#f4df72;color:#604f00}.a2a-group-chat__row--orchestrator .a2a-group-chat__bubble{border-color:#e8d277;background:#fff8d8}.a2a-group-chat__row--orchestrator .a2a-group-chat__section{background:rgba(255,255,255,.6)}.a2a-group-chat__row--field .a2a-group-chat__bubble{border-color:#c6dff5;background:#f7fbff}.a2a-group-chat__system{background:#6f8395}#a2a-scenario-card-grid{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px!important;align-items:stretch}#a2a-scenario-card-grid>.gr-column{min-width:0!important;flex:initial!important}.a2a-scenario-card{gap:0!important;min-width:0!important;border:1px solid #c9d9e7;border-radius:12px;background:#fff;box-shadow:0 1px 2px rgba(40,58,74,.08);overflow:hidden}.a2a-scenario-card__body{height:100%;min-height:214px;padding:15px 15px 11px;background:linear-gradient(145deg,#f9fcff,#eef5fb);color:#25313d}.a2a-scenario-card__eyebrow{margin-bottom:5px;color:#5b7b99;font-size:10px;font-weight:800;letter-spacing:.08em}.a2a-scenario-card__body h4{margin:0 0 13px;color:#274761;font-size:15px;line-height:1.35}.a2a-scenario-card__department{display:flex;align-items:center;gap:7px;margin-bottom:12px}.a2a-scenario-card__department span,.a2a-scenario-card__request>span{color:#71869b;font-size:10px;font-weight:800;letter-spacing:.04em}.a2a-scenario-card__department strong{display:inline-block;padding:4px 7px;border-radius:999px;background:#dcebf7;color:#365d7c;font-size:11px;line-height:1.25}.a2a-scenario-card__request{padding:10px;border-radius:8px;background:rgba(255,255,255,.8);border:1px solid #e1e9f0}.a2a-scenario-card__request p{margin:5px 0 0;color:#425d73;font-size:12px;line-height:1.55;word-break:keep-all}.a2a-scenario-card button{width:calc(100% - 24px)!important;min-height:34px;margin:0 12px 12px!important;border:1px solid #769bbc!important;border-radius:8px!important;background:#fff!important;color:#315a7b!important;font-size:12px!important;font-weight:800!important}.a2a-scenario-card button:hover{border-color:#3f78a5!important;background:#edf6ff!important;color:#1d4f78!important}@media(max-width:900px){#a2a-scenario-card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.a2a-group-chat__messages{padding:14px 10px}.a2a-group-chat__row>div:last-child{max-width:calc(100% - 42px)}.a2a-group-chat__evidence-tooltip::after{left:auto;right:0;max-width:calc(100vw - 64px)}#a2a-scenario-card-grid{grid-template-columns:1fr}.a2a-scenario-card__body{min-height:0}}
    """
    css += """
    /* Legacy group-chat treatment; the SAP Joule rules below take final precedence. */
    .a2a-chat-shell{border:0!important;border-radius:16px!important;background:#b2c7d9!important;box-shadow:0 5px 18px rgba(57,78,97,.13)}
    .a2a-group-chat{background:#b2c7d9!important;border:0!important;border-radius:16px 16px 0 0!important}
    .a2a-group-chat__header{min-height:56px;padding:9px 15px!important;background:#fee500!important;color:#1f1f1f!important;box-shadow:inset 0 -1px rgba(0,0,0,.09)}
    .a2a-group-chat__room-title{display:flex;gap:9px;align-items:center}.a2a-group-chat__room-avatar{display:grid;place-items:center;width:32px;height:32px;border-radius:12px;background:#3c1e1e;color:#fee500;font-size:14px;font-weight:900}.a2a-group-chat__room-title b{display:block;font-size:14px;line-height:1.2}.a2a-group-chat__room-title span:not(.a2a-group-chat__room-avatar){display:block;margin-top:2px;color:#665e20;font-size:10px;line-height:1.2}.a2a-group-chat__room-status{align-self:center;color:#665e20;font-size:11px;font-weight:700}.a2a-group-chat__room-status::before{display:inline-block;width:6px;height:6px;margin:0 4px 1px 0;border-radius:50%;background:#48a868;content:""}
    .a2a-group-chat__messages{max-width:980px;padding:18px!important;background:#b2c7d9}.a2a-group-chat__row{gap:9px;margin-bottom:15px}.a2a-group-chat__row>div:last-child{max-width:min(720px,calc(100% - 46px))}.a2a-group-chat__avatar{width:35px;height:35px;border:1px solid rgba(55,76,93,.16);background:#f7f7f7!important;color:#435867!important;font-size:12px;box-shadow:0 1px 2px rgba(58,75,91,.16)!important;overflow:hidden!important}.a2a-group-chat__sender{margin:1px 0 4px!important;color:#324755!important;font-size:11px!important;font-weight:800}.a2a-group-chat__bubble{position:relative;padding:10px 12px!important;border:0!important;border-radius:3px 13px 13px 13px!important;background:#fff!important;color:#202124!important;line-height:1.6!important;box-shadow:0 1px 1px rgba(50,67,82,.13)!important}.a2a-group-chat__row--agent .a2a-group-chat__bubble::before,.a2a-group-chat__row--orchestrator .a2a-group-chat__bubble::before{position:absolute;top:9px;left:-5px;width:10px;height:10px;background:inherit;content:"";clip-path:polygon(0 0,100% 0,100% 100%)}
    .a2a-group-chat__row--field{justify-content:flex-end}.a2a-group-chat__row--field .a2a-group-chat__avatar{order:2;border-color:rgba(91,77,0,.16);background:#fff3a7!important;color:#665300!important}.a2a-group-chat__row--field>div:last-child{display:flex;flex-direction:column;align-items:flex-end}.a2a-group-chat__row--field .a2a-group-chat__sender{text-align:right}.a2a-group-chat__row--field .a2a-group-chat__bubble{border-radius:13px 3px 13px 13px!important;background:#fee500!important}.a2a-group-chat__row--field .a2a-group-chat__bubble::after{position:absolute;top:9px;right:-5px;width:10px;height:10px;background:inherit;content:"";clip-path:polygon(0 0,100% 0,0 100%)}
    .a2a-group-chat__row--orchestrator{justify-content:flex-start}.a2a-group-chat__row--orchestrator .a2a-group-chat__avatar{order:initial;border-color:rgba(10,110,209,.28);background:#fff!important;color:inherit!important}.a2a-group-chat__brand-avatar{display:block;width:76%;height:76%;max-width:76%;max-height:76%;border-radius:50%;object-fit:contain;flex:none}.a2a-group-chat__row--orchestrator .a2a-group-chat__bubble{border-radius:3px 13px 13px 13px!important;background:#fff!important}.a2a-group-chat__row--orchestrator .a2a-group-chat__section{background:#f5f3fb!important}.a2a-group-chat__row--field .a2a-group-chat__section{background:rgba(255,255,255,.52)!important}
    .a2a-group-chat__title{margin-bottom:7px!important;color:#655b90!important}.a2a-group-chat__section{margin-top:6px!important;padding:7px 8px!important;border-radius:8px!important;background:#f3f6f8!important}.a2a-group-chat__section-label{color:#617586!important}.a2a-group-chat__subagent-card{border:0!important;border-radius:9px!important;background:#f3f6f8!important;box-shadow:inset 0 0 0 1px rgba(101,121,136,.12)}.a2a-group-chat__subagent-next,.a2a-group-chat__subagent-meta{border-top-color:#dbe3e9!important}.a2a-group-chat__tool-chip,.a2a-group-chat__evidence-tooltip{border-color:#d4dde4!important;background:#fff!important;color:#536a7b!important}.a2a-group-chat__system{margin:6px auto 14px!important;padding:5px 10px!important;background:rgba(71,93,111,.50)!important;color:#fff!important;font-size:10px!important;box-shadow:0 1px 1px rgba(50,67,82,.1)}
    .a2a-group-chat__team-card{padding:10px;border:0;border-radius:9px;background:#f3f6f8;box-shadow:inset 0 0 0 1px rgba(101,121,136,.12)}.a2a-group-chat__team-summary>span,.a2a-group-chat__team-next>span{display:block;margin-bottom:4px;color:#587086;font-size:10px;font-weight:800;letter-spacing:.02em}.a2a-group-chat__team-summary p,.a2a-group-chat__team-next p{margin:0}.a2a-group-chat__team-summary ul,.a2a-group-chat__team-next ul{margin:0;padding-left:17px}.a2a-group-chat__team-next{margin-top:9px;padding-top:9px;border-top:1px solid #dbe3e9}.a2a-group-chat__team-meta{display:flex;justify-content:flex-end;margin-top:10px;padding-top:9px;border-top:1px solid #dbe3e9}
    .a2a-chat-shell,.a2a-group-chat{overflow-x:hidden!important}.a2a-group-chat__messages{overflow-x:hidden!important;overflow-y:auto!important}.a2a-group-chat__row,.a2a-group-chat__row>div:last-child,.a2a-group-chat__bubble{min-width:0}.a2a-group-chat__bubble,.a2a-group-chat__section-body,.a2a-group-chat__subagent-card,.a2a-group-chat__team-card{overflow-wrap:anywhere;word-break:break-word}
    .a2a-group-chat__new-message{bottom:16px!important;background:#fee500!important;color:#3c3100!important;box-shadow:0 2px 8px rgba(50,67,82,.24)!important}.a2a-group-chat__new-message:hover{background:#f4da00!important}.a2a-chat-composer{padding:10px 12px 12px!important;background:#b2c7d9!important;border-top:1px solid rgba(67,88,105,.16)!important}.a2a-chat-composer textarea{min-height:44px!important;padding:11px 14px!important;border:0!important;border-radius:22px!important;background:#fff!important;color:#273845!important;box-shadow:0 1px 2px rgba(50,67,82,.14)!important}.a2a-chat-composer textarea:focus{box-shadow:0 0 0 2px rgba(254,229,0,.82),0 1px 2px rgba(50,67,82,.14)!important}
    @media(max-width:700px){.a2a-group-chat__messages{padding:14px 10px!important}.a2a-group-chat__room-status{display:none}.a2a-group-chat__bubble{font-size:12px}.a2a-group-chat__row>div:last-child{max-width:calc(100% - 45px)}}
    """
    css += """
    #a2a-agent-cards-modal{width:min(980px,calc(100vw - 32px));max-height:82vh;padding:0;border:0;border-radius:16px;box-shadow:0 24px 64px rgba(19,42,65,.32);background:#f8fbff;color:#25313d}#a2a-agent-cards-modal::backdrop{background:rgba(24,42,58,.5);backdrop-filter:blur(2px)}.a2a-topology{max-height:82vh;overflow:auto}.a2a-topology__modal-header{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;padding:18px 22px;border-bottom:1px solid #d9e4ee;background:#fff}.a2a-topology__modal-header span{display:block;color:#587086;font-size:11px;font-weight:800}.a2a-topology__modal-header h2{margin:3px 0 0;color:#314b64;font-size:20px}.a2a-topology__modal-header button{display:grid;place-items:center;width:32px;height:32px;border:0;border-radius:50%;background:#edf2f6;color:#41576b;font-size:22px;cursor:pointer}.a2a-topology__intro{margin:0;padding:14px 22px;background:#f3f7fa;color:#4d657d;font-size:12px;line-height:1.5}.a2a-topology__teams{display:grid;gap:14px;padding:18px 22px}.a2a-topology__team{border:1px solid #d6e1eb;border-radius:12px;background:#fff;overflow:hidden}.a2a-topology__team-header{display:grid;grid-template-columns:auto 1fr auto;gap:9px;align-items:center;padding:12px 14px;background:#edf5fb}.a2a-topology__team-header span{padding:3px 6px;border-radius:99px;background:#d9e9f8;color:#285779;font-size:10px;font-weight:800}.a2a-topology__team-header b{color:#314b64;font-size:14px}.a2a-topology__team-header code{color:#587086;font-size:10px}.a2a-topology__team>p{margin:0;padding:10px 14px;color:#4d657d;font-size:12px;line-height:1.5}.a2a-topology__children{display:grid;gap:8px;margin:0 14px 14px;padding:0 0 0 17px;border-left:2px solid #c8d9e8;list-style:none}.a2a-topology__subagent{position:relative;padding:10px 11px;border:1px solid #e0e8ef;border-radius:9px;background:#fbfdff}.a2a-topology__subagent::before{position:absolute;top:19px;left:-18px;width:16px;border-top:2px solid #c8d9e8;content:""}.a2a-topology__node-label b{color:#425f79;font-size:12px}.a2a-topology__subagent p{margin:5px 0;color:#667b90;font-size:11px;line-height:1.4}.a2a-topology__tools{display:flex;flex-wrap:wrap;gap:6px;align-items:flex-start;margin-top:8px}.a2a-topology__tools-label{padding-top:4px;color:#8093a6;font-size:10px;font-weight:800}.a2a-topology__tool{min-width:180px;max-width:100%;padding:7px 8px;border:1px solid #b8d6cb;border-radius:7px;background:#f0faf5}.a2a-topology__tool code{display:block;color:#137333;font-size:11px;font-weight:800}.a2a-topology__tool span{display:block;margin-top:3px;color:#4d657d;font-size:10px;line-height:1.35}.a2a-topology__no-tool{padding:4px 7px;border-radius:6px;background:#f0f3f6;color:#6b7e90;font-size:10px}@media(max-width:700px){#a2a-agent-cards-modal{width:calc(100vw - 16px)}.a2a-topology__modal-header,.a2a-topology__intro,.a2a-topology__teams{padding-left:14px;padding-right:14px}.a2a-topology__team-header{grid-template-columns:1fr}.a2a-topology__team-header code{word-break:break-all}}
    """
    css += """
    #a2a-agent-cards-modal{height:min(760px,82vh)}.a2a-topology{display:flex;max-height:none;height:100%;overflow:hidden;flex-direction:column}.a2a-topology__layout{display:grid;grid-template-columns:250px minmax(0,1fr);min-height:0;flex:1}.a2a-topology__sidebar{display:flex;gap:6px;min-height:0;padding:12px;border-right:1px solid #d9e4ee;background:#f3f7fa;overflow-y:auto;flex-direction:column}.a2a-topology__team-select{width:100%;padding:10px;border:1px solid transparent;border-radius:9px;background:transparent;color:#4d657d;text-align:left;cursor:pointer}.a2a-topology__team-select:hover{background:#e9f1f8}.a2a-topology__team-select[aria-selected="true"]{border-color:#9abbd8;background:#fff;color:#284b69;box-shadow:0 1px 2px rgba(40,72,100,.08)}.a2a-topology__team-select b{display:block;font-size:12px}.a2a-topology__team-select span{display:-webkit-box;margin-top:4px;color:#6a8297;font-size:10px;line-height:1.35;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}.a2a-topology__detail{min-height:0;padding:16px;overflow-y:auto}.a2a-topology__team-panel{border:1px solid #d6e1eb;border-radius:12px;background:#fff;overflow:hidden}.a2a-topology__team-panel>p{margin:0;padding:10px 14px;color:#4d657d;font-size:12px;line-height:1.5}.a2a-topology__subagent-heading{padding:10px 14px;border-top:1px solid #e2eaf1;border-bottom:1px solid #e2eaf1;background:#f8fbfd;color:#587086;font-size:11px;font-weight:800}.a2a-topology__subagents{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:9px;margin:0;padding:14px;list-style:none}.a2a-topology__subagent::before{display:none}.a2a-topology__subagent{min-width:0}.a2a-topology__tools{margin-top:7px}@media(max-width:700px){#a2a-agent-cards-modal{height:min(760px,calc(100vh - 16px))}.a2a-topology__layout{grid-template-columns:1fr;grid-template-rows:auto minmax(0,1fr)}.a2a-topology__sidebar{display:flex;max-height:116px;border-right:0;border-bottom:1px solid #d9e4ee;overflow-x:auto;overflow-y:hidden;flex-direction:row}.a2a-topology__team-select{min-width:160px}.a2a-topology__detail{padding:10px}.a2a-topology__subagents{grid-template-columns:1fr;padding:10px}}
    """
    css += """
    #a2a-page-toolbar{justify-content:flex-end!important;align-items:center!important;min-height:0!important;margin:0 0 8px!important;gap:6px!important}#a2a-page-toolbar>.gr-column{flex:0 0 auto!important;min-width:0!important}#a2a-agent-cards-open,#a2a-chat-reset,#a2a-chat-pause{width:auto!important;min-width:0!important;min-height:29px!important;padding:5px 10px!important;border:1px solid #c8d6e2!important;border-radius:8px!important;background:#fff!important;color:#425f79!important;font-size:11px!important;font-weight:800!important;box-shadow:0 1px 2px rgba(40,58,74,.08)!important}#a2a-agent-cards-open:hover,#a2a-chat-reset:hover{border-color:#789ab7!important;background:#f3f8fc!important;color:#274e70!important}#a2a-chat-pause{border-color:#d5bd80!important;color:#765c15!important}#a2a-chat-pause:hover{border-color:#b7974b!important;background:#fff9e8!important;color:#624b0d!important}
    """
    css += """
    .a2a-group-chat__approval-actions{display:flex;flex-wrap:wrap;align-items:center;gap:6px}.a2a-group-chat__approval-button{padding:6px 9px;border:0;border-radius:7px;font-size:11px;font-weight:800;line-height:1.3;cursor:pointer}.a2a-group-chat__approval-button--send{background:#fee500;color:#3c3100}.a2a-group-chat__approval-button--send:hover{background:#f4da00}.a2a-group-chat__approval-button--cancel{background:#edf1f5;color:#516373}.a2a-group-chat__approval-button--cancel:hover{background:#dfe7ed}.a2a-group-chat__approval-button:disabled{opacity:.7;cursor:default}.a2a-group-chat__system:has(.a2a-group-chat__hitl-fallback-button){display:flex;align-items:center;gap:8px;max-width:min(92%,680px);border-radius:11px;text-align:left;line-height:1.45}.a2a-group-chat__hitl-fallback-button{flex:none;padding:6px 9px;border:0;border-radius:7px;background:#fee500;color:#3c3100;font-size:11px;font-weight:800;line-height:1.3;cursor:pointer}.a2a-group-chat__hitl-fallback-button:hover{background:#f4da00}.a2a-group-chat__hitl-fallback-button:disabled{opacity:.7;cursor:default}.a2a-hidden-hitl-action,.a2a-hidden-chat-action{display:none!important}@media(max-width:700px){.a2a-group-chat__approval-actions{align-items:stretch;flex-direction:column}.a2a-group-chat__approval-button{width:100%}.a2a-group-chat__system:has(.a2a-group-chat__hitl-fallback-button){display:block}.a2a-group-chat__hitl-fallback-button{display:block;width:100%;margin-top:7px}}
    """
    css += """
    .a2a-group-chat__profitability{margin-top:10px;padding-top:10px;border-top:1px solid #dbe3e9}.a2a-group-chat__profitability-heading{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:7px;color:#405e75;font-size:11px}.a2a-group-chat__profitability-heading b{font-size:12px}.a2a-group-chat__profitability-heading span{color:#718699;font-size:10px}.a2a-group-chat__financial-table{width:100%;table-layout:fixed;border-collapse:separate;border-spacing:0;overflow:hidden;border:1px solid #d9e4ec;border-radius:8px;background:#fff;color:#394b5a;font-size:9px;line-height:1.35}.a2a-group-chat__financial-table th,.a2a-group-chat__financial-table td{padding:5px 4px;border-right:1px solid #e5edf2;border-bottom:1px solid #e5edf2;vertical-align:top;overflow-wrap:anywhere;word-break:break-word}.a2a-group-chat__financial-table th:last-child,.a2a-group-chat__financial-table td:last-child{border-right:0}.a2a-group-chat__financial-table tbody tr:last-child th,.a2a-group-chat__financial-table tbody tr:last-child td{border-bottom:0}.a2a-group-chat__financial-table thead th{background:#eaf2f7;color:#506a80;font-size:8px;font-weight:800;text-align:left}.a2a-group-chat__financial-table tbody th{background:#f7fafc;color:#3e5e77;font-size:10px;text-align:left}.a2a-group-chat__profitability-detail{margin-top:8px}.a2a-group-chat__profitability-detail summary{color:#506a80;font-size:10px;font-weight:800;cursor:pointer}.a2a-group-chat__profitability-detail[open] summary{margin-bottom:7px}.a2a-group-chat__financial-table--monthly{font-size:8px}.a2a-group-chat__financial-table--monthly thead th{font-size:8px}.a2a-group-chat__profitability-boundary{margin:7px 0 0;color:#748795;font-size:9px;line-height:1.4}
    """
    css += """
    /* SAP Joule / Fiori conversation surface. */
    .a2a-chat-shell{border:1px solid #d9d5e7!important;border-radius:16px!important;background:#fff!important;box-shadow:0 2px 10px rgba(58,42,91,.10)!important}
    .a2a-group-chat{border:0!important;border-radius:16px 16px 0 0!important;background:#fff!important}
    .a2a-group-chat__header{min-height:58px;padding:10px 16px!important;background:linear-gradient(105deg,#0a6ed1 0%,#4f36b7 56%,#805ad5 100%)!important;color:#fff!important;box-shadow:none!important}
    .a2a-group-chat__room-avatar{width:32px;height:32px;border-radius:10px;background:rgba(255,255,255,.18)!important;color:#fff!important;box-shadow:inset 0 0 0 1px rgba(255,255,255,.26)}
    .a2a-group-chat__room-title b{color:#fff!important}.a2a-group-chat__room-title span:not(.a2a-group-chat__room-avatar),.a2a-group-chat__room-status{color:rgba(255,255,255,.84)!important}.a2a-group-chat__room-status::before{background:#7ee2b8!important}
    .a2a-group-chat__messages{box-sizing:border-box!important;width:100%!important;max-width:none!important;margin:0!important;padding:18px!important;background:#f7f6fb!important}.a2a-group-chat__row{gap:10px;margin-bottom:16px}.a2a-group-chat__row>div:last-child{max-width:min(720px,calc(100% - 46px))}
    .a2a-group-chat__avatar{width:35px;height:35px;border:1px solid #ddd8e9!important;background:#fff!important;color:#536273!important;box-shadow:0 1px 3px rgba(56,43,88,.12)!important;overflow:hidden!important}.a2a-group-chat__sender{margin:1px 0 5px!important;color:#3a4655!important;font-size:11px!important;font-weight:800}
    .a2a-group-chat__bubble{padding:11px 13px!important;border:1px solid #e0ddea!important;border-radius:12px!important;background:#fff!important;color:#25313d!important;line-height:1.6!important;box-shadow:0 1px 2px rgba(55,41,85,.06)!important}.a2a-group-chat__row--agent .a2a-group-chat__bubble::before,.a2a-group-chat__row--orchestrator .a2a-group-chat__bubble::before,.a2a-group-chat__row--field .a2a-group-chat__bubble::after{display:none!important}
    .a2a-group-chat__row--orchestrator{justify-content:flex-start}.a2a-group-chat__row--orchestrator .a2a-group-chat__avatar{order:initial;border-color:#cfc3ed!important;background:#fff!important}.a2a-group-chat__row--orchestrator .a2a-group-chat__bubble{border-color:#d6c9f3!important;background:#f8f5ff!important}.a2a-group-chat__row--orchestrator .a2a-group-chat__section{background:#f0eaff!important}
    .a2a-group-chat__row--field{justify-content:flex-end}.a2a-group-chat__row--field .a2a-group-chat__avatar{order:2;border-color:#cbbcf0!important;background:#f4efff!important;color:#6143a6!important}.a2a-group-chat__row--field .a2a-group-chat__bubble{border-color:#cbbcf0!important;border-radius:12px!important;background:linear-gradient(135deg,#f4efff,#ebe3ff)!important}.a2a-group-chat__row--field>div:last-child{align-items:flex-end}.a2a-group-chat__row--field .a2a-group-chat__sender{text-align:right}
    .a2a-group-chat__title{color:#5336a6!important}.a2a-group-chat__section{margin-top:7px!important;border-radius:9px!important;background:#f5f4f8!important}.a2a-group-chat__section-label{color:#66558c!important}.a2a-group-chat__subagent-card,.a2a-group-chat__team-card{border:1px solid #e3deed!important;background:#fbfaff!important;box-shadow:none!important}.a2a-group-chat__tool-chip,.a2a-group-chat__evidence-tooltip{border-color:#d8d0e8!important;background:#fff!important;color:#5b4d7b!important}.a2a-group-chat__system{border:1px solid #dce1e8!important;border-radius:999px!important;background:#eef0f4!important;color:#526171!important;box-shadow:none!important}
    .a2a-group-chat__new-message{background:#5d3ec1!important;color:#fff!important;box-shadow:0 2px 8px rgba(72,49,151,.24)!important}.a2a-group-chat__new-message:hover{background:#4c30aa!important}.a2a-chat-composer{padding:11px 12px 12px!important;border-top:1px solid #e2deeb!important;background:#fff!important}.a2a-chat-composer textarea{min-height:44px!important;border:1px solid #cfc8df!important;border-radius:10px!important;background:#fff!important;color:#243241!important;box-shadow:none!important}.a2a-chat-composer textarea:focus{border-color:#7452cc!important;box-shadow:0 0 0 2px rgba(116,82,204,.18)!important}
    #a2a-page-toolbar-host{margin:0 0 8px!important;padding:0!important}#a2a-page-toolbar{display:flex;justify-content:flex-end;align-items:center;gap:7px;flex-wrap:wrap;margin:0;padding:0}.a2a-chat-toolbar__button{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;min-width:0;height:32px;padding:6px 10px;border:1px solid #d4cde3;border-radius:8px;background:#fff;color:#49377a;font:800 12px/1.2 inherit;white-space:nowrap;word-break:keep-all;box-shadow:none;cursor:pointer}.a2a-chat-toolbar__button:hover{border-color:#7a58cc;background:#f6f2ff;color:#432b94}.a2a-chat-toolbar__reset{min-width:82px}.a2a-chat-toolbar__pause{min-width:88px;border-color:#bca8e8;color:#5138a5}.a2a-chat-toolbar__agent{min-width:72px}
    .a2a-group-chat__approval-button--send,.a2a-group-chat__hitl-fallback-button{background:#5d3ec1!important;color:#fff!important}.a2a-group-chat__approval-button--send:hover,.a2a-group-chat__hitl-fallback-button:hover{background:#4c30aa!important}.a2a-group-chat__approval-button--cancel{background:#eef0f4!important;color:#4f5e6d!important}.a2a-group-chat__approval-button--cancel:hover{background:#e1e5ea!important}
    @media(max-width:700px){.a2a-group-chat__messages{padding:14px 10px!important}.a2a-group-chat__room-status{display:none}.a2a-group-chat__bubble{font-size:12px}.a2a-group-chat__row>div:last-child{max-width:calc(100% - 45px)}}
    """
    with gr.Blocks(title="F&B LLM Orchestration A2A", css=css) as app:
        gr.HTML(
            "<div id=\"a2a-page-toolbar\">"
            "<button type=\"button\" class=\"a2a-chat-toolbar__button a2a-chat-toolbar__reset\" data-a2a-chat-toolbar-action=\"reset\">채팅 초기화</button>"
            "<button type=\"button\" class=\"a2a-chat-toolbar__button a2a-chat-toolbar__pause\" data-a2a-chat-toolbar-action=\"pause\">⏸ 일시정지</button>"
            "<button type=\"button\" id=\"a2a-agent-cards-open\" class=\"a2a-chat-toolbar__button a2a-chat-toolbar__agent\">Agent 정보</button>"
            "</div>",
            elem_id="a2a-page-toolbar-host",
        )
        with gr.Row():
            with gr.Column(elem_classes=["a2a-chat-shell"]):
                gr.HTML(
                    _group_chat_html([]),
                    label="Agent handoff conversation",
                    elem_id="a2a-group-chat",
                )
                request = gr.Textbox(
                    show_label=False,
                    value=DEFAULT_REQUEST,
                    lines=1,
                    max_lines=1,
                    placeholder="요청을 입력하세요",
                    elem_id="a2a-chat-request",
                    elem_classes=["a2a-chat-composer"],
                    container=False,
                )
        chat_payload = gr.HTML(
            "",
            elem_id="a2a-chat-payload",
            elem_classes=["a2a-chat-payload"],
        )
        reset_chat_button = gr.Button(
            "채팅 초기화",
            elem_id="a2a-chat-reset-action",
            elem_classes=["a2a-hidden-chat-action"],
        )
        pause_chat_button = gr.Button(
            "일시정지",
            elem_id="a2a-chat-pause-action",
            elem_classes=["a2a-hidden-chat-action"],
        )
        approval_state = gr.State([])
        send_email_button = gr.Button(
            "Outlook 메일 발송",
            elem_id="a2a-approval-send",
            elem_classes=["a2a-hidden-chat-action"],
        )
        cancel_email_button = gr.Button(
            "Outlook 메일을 발송하지 않음",
            elem_id="a2a-approval-cancel",
            elem_classes=["a2a-hidden-chat-action"],
        )
        gr.HTML(_agent_card_modal_html(), elem_id="a2a-agent-cards-modal-host")
        requester_department = gr.State(
            SCENARIO_REQUEST_DEPARTMENTS["기존 설비 소모품 보충 구매"]
        )
        last_outcome = gr.State(None)
        with (
            gr.Accordion("업무 시나리오", open=False),
            gr.Row(
                elem_id="a2a-scenario-card-grid",
                elem_classes=["a2a-scenario-cards"],
            ),
        ):
            for scenario_title, scenario_request in SCENARIO_REQUESTS:
                scenario_department = SCENARIO_REQUEST_DEPARTMENTS[scenario_title]
                with gr.Column(elem_classes=["a2a-scenario-card"]):
                    gr.HTML(
                        _scenario_card_html(
                            scenario_title, scenario_department, scenario_request
                        )
                    )
                    scenario_card = gr.Button("요청 선택", variant="secondary")
                scenario_card.click(
                    lambda value=scenario_request, department=scenario_department: (
                        value,
                        department,
                    ),
                    outputs=[request, requester_department],
                    queue=False,
                )
        chat_history = gr.State([])
        workflow_outputs = [
            chat_payload,
            chat_history,
            approval_state,
            last_outcome,
        ]
        approval_outputs = [chat_payload, chat_history, approval_state]
        request.input(
            lambda _request: "",
            inputs=request,
            outputs=requester_department,
            queue=False,
        )
        workflow_event = request.submit(
            run_workflow,
            inputs=[
                request,
                chat_history,
                requester_department,
                approval_state,
                last_outcome,
            ],
            outputs=workflow_outputs,
            queue=True,
            scroll_to_output=False,
        )
        pause_chat_button.click(
            pause_chat, cancels=[workflow_event], queue=False, scroll_to_output=False
        )
        reset_chat_button.click(
            reset_chat,
            outputs=workflow_outputs,
            cancels=[workflow_event],
            queue=False,
            scroll_to_output=False,
        )
        send_email_button.click(
            send_approved_email,
            inputs=[approval_state, chat_history],
            outputs=approval_outputs,
            queue=True,
            scroll_to_output=False,
        )
        cancel_email_button.click(
            cancel_email_approval,
            inputs=[approval_state, chat_history],
            outputs=approval_outputs,
            queue=False,
            scroll_to_output=False,
        )
        chat_human_review_button = gr.Button(
            "Human in the loop 검토 완료",
            elem_id="a2a-human-review-complete",
            elem_classes=["a2a-hidden-hitl-action"],
        )
        chat_human_review_button.click(
            complete_chat_human_review,
            inputs=[approval_state, chat_history],
            outputs=approval_outputs,
            queue=False,
            scroll_to_output=False,
        )
        app.load(
            None, inputs=None, outputs=None, js=_A2A_GROUP_CHAT_SCROLL_JS, queue=False
        )
        app.queue(default_concurrency_limit=4)
    return app


def launch_a2a_ui() -> gr.Blocks:
    app = build_a2a_ui()
    app.launch(
        inline=True, share=False, show_error=True, server_name="127.0.0.1", height=1100
    )
    return app
