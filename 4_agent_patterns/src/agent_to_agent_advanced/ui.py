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
from .harness import (
    COMPONENT_LABELS,
    active_runtime_overlays_for_request,
    analyse_trace,
    apply_human_selection,
    adopt_variant,
    evaluate_comparison,
    load_revision_library,
    record_live_verification,
    rollback_active_revision,
    rollback_adoption,
    run_harness_experiment,
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

ADVANCED_A2A_WORKFLOW_GRAPH_SVG = """
<svg viewBox="0 0 1800 455" width="100%" role="img" aria-label="Advanced LLM-orchestrated A2A workflow with Codex App Server" xmlns="http://www.w3.org/2000/svg">
  <style>.node{fill:#fff;stroke:#8ab4f8;stroke-width:2}.work{fill:#f8fbff;stroke:#4285f4;stroke-width:2}.end{fill:#e6f4ea;stroke:#34a853;stroke-width:2}.middleware{fill:#fffdf5;stroke:#f9ab00;stroke-width:2}.codex{fill:#edf9f5;stroke:#10a37f;stroke-width:2}.harness{fill:#f5eef8;stroke:#7b1fa2;stroke-width:2}.label{font:600 15px sans-serif;fill:#202124}.small{font:13px sans-serif;fill:#5f6368}.edge{fill:none;stroke:#5f6368;stroke-width:2;marker-end:url(#advanced-a2a-arrow)}.harness-edge{fill:none;stroke:#7b1fa2;stroke-width:2;stroke-dasharray:6 4;marker-end:url(#advanced-a2a-arrow)}</style>
  <defs><marker id="advanced-a2a-arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#5f6368"/></marker></defs>
  <text x="25" y="32" class="label" style="font-size:18px">Advanced LLM-Orchestrated A2A Workflow</text>

  <rect x="25" y="180" width="155" height="76" rx="12" class="node"/><text x="102" y="210" text-anchor="middle" class="label">User request</text><text x="102" y="232" text-anchor="middle" class="small">message</text>
  <rect x="260" y="38" width="225" height="76" rx="12" class="work"/><text x="372" y="68" text-anchor="middle" class="label">ReAct Observation</text><text x="372" y="90" text-anchor="middle" class="small">artifacts · open decisions</text>
  <rect x="265" y="165" width="230" height="104" rx="12" class="work"/><text x="380" y="199" text-anchor="middle" class="label">Orchestration Agent</text><text x="380" y="222" text-anchor="middle" class="small">LLM decide: Team / Codex</text><text x="380" y="244" text-anchor="middle" class="small">/ complete</text>
  <rect x="570" y="52" width="210" height="76" rx="12" class="work"/><text x="675" y="82" text-anchor="middle" class="label">Grounding &amp; Approval</text><text x="675" y="104" text-anchor="middle" class="small">LLM Tool Calling</text>
  <rect x="835" y="52" width="230" height="76" rx="12" class="harness"/><text x="950" y="82" text-anchor="middle" class="label">Harness Labs</text><text x="950" y="104" text-anchor="middle" class="small">trace review · human apply</text>
  <rect x="570" y="180" width="180" height="76" rx="12" class="work"/><text x="660" y="210" text-anchor="middle" class="label">A2A Handoff</text><text x="660" y="232" text-anchor="middle" class="small">Message + envelope</text>
  <rect x="825" y="155" width="225" height="126" rx="12" class="node"/><text x="937" y="188" text-anchor="middle" class="label">Selected A2A Agent</text><text x="937" y="211" text-anchor="middle" class="small">Team Agent or Codex Agent</text><text x="937" y="234" text-anchor="middle" class="small">A2A Task status updates</text><text x="937" y="257" text-anchor="middle" class="small">artifact production</text>
  <rect x="1115" y="315" width="205" height="76" rx="12" class="codex"/><text x="1217" y="345" text-anchor="middle" class="label">Codex App Server</text><text x="1217" y="367" text-anchor="middle" class="small">read-only SQL draft</text>
  <rect x="1125" y="180" width="190" height="76" rx="12" class="work"/><text x="1220" y="210" text-anchor="middle" class="label">Task &amp; Artifact</text><text x="1220" y="232" text-anchor="middle" class="small">TextPart · DataPart</text>
  <rect x="1390" y="165" width="205" height="104" rx="12" class="middleware"/><text x="1492" y="199" text-anchor="middle" class="label">Middleware</text><text x="1492" y="222" text-anchor="middle" class="small">Task events · artifact received</text><text x="1492" y="244" text-anchor="middle" class="small">handoff audit</text>
  <rect x="1665" y="180" width="110" height="76" rx="12" class="end"/><text x="1720" y="210" text-anchor="middle" class="label">Response</text><text x="1720" y="232" text-anchor="middle" class="small">to Field</text>

  <path d="M180 218 H265" class="edge"/><text x="222" y="204" text-anchor="middle" class="small">Field Agent handoff</text><path d="M372 114 V165" class="edge"/><path d="M495 218 H570" class="edge"/><path d="M750 218 H825" class="edge"/><path d="M1050 218 H1125" class="edge"/><path d="M1315 218 H1390" class="edge"/><path d="M1595 218 H1665" class="edge"/>
  <path d="M495 190 C525 190 530 90 570 90" class="edge"/><text x="526" y="122" class="small">tool call</text><path d="M675 128 C675 148 570 148 495 185" class="edge"/><text x="575" y="151" class="small">evidence</text>
  <path d="M950 128 C950 150 650 145 495 175" class="harness-edge"/><text x="755" y="140" text-anchor="middle" class="small" style="fill:#7b1fa2">approved revision overlay</text>
  <path d="M937 281 C937 330 1060 352 1115 352" class="edge"/><text x="1022" y="330" class="small">when Codex selected</text><path d="M1217 315 V256" class="edge"/><text x="1243" y="292" class="small">SQL artifact</text>
  <path d="M1492 269 C1492 425 380 425 380 269" class="edge"/><text x="935" y="422" text-anchor="middle" class="small">artifact event → observe → next ReAct decision</text>
</svg>
"""

_A2A_GROUP_CHAT_SCROLL_JS = """
() => {
  const root = document.getElementById("a2a-group-chat");
  const harnessRoots = document.querySelectorAll("#a2a-harness-chat");
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
  harnessRoots.forEach((harnessRoot) => {
    const harnessScope = harnessRoot.closest(".gradio-container") || document;
    const harnessSidebar = harnessScope.querySelector("#a2a-harness-sidebar");
    if (!harnessRoot.dataset.harnessBound) {
    harnessRoot.dataset.harnessBound = "true";
    const syncHarnessSidebar = () => {
      const collapsed = harnessSidebar?.classList.contains("is-collapsed") || false;
      harnessRoot.querySelectorAll("[data-a2a-harness-sidebar-toggle]").forEach((button) => {
        button.setAttribute("aria-expanded", String(!collapsed));
        button.setAttribute("aria-label", collapsed ? "Harness Labs 펼치기" : "Harness Labs 접기");
      });
    };
    const invokeHarnessAction = (selector) => {
      harnessScope.querySelector(selector)?.click();
    };
    const syncHarnessChoice = (choice) => {
      const input = harnessScope.querySelector(
        "#a2a-harness-choice textarea, #a2a-harness-choice input"
      );
      if (!input || !choice) return;
      input.value = choice.value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const syncHarnessComment = (comment) => {
      const input = harnessScope.querySelector(
        "#a2a-harness-comment textarea, #a2a-harness-comment input"
      );
      if (!input || !comment) return;
      input.value = comment.value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    };
    harnessRoot.addEventListener("change", (event) => {
      const choice = event.target.closest("[data-a2a-harness-choice]");
      if (choice && harnessRoot.contains(choice)) syncHarnessChoice(choice);
      const comment = event.target.closest("[data-a2a-harness-comment]");
      if (comment && harnessRoot.contains(comment)) syncHarnessComment(comment);
    });
    harnessRoot.addEventListener("click", (event) => {
      const sidebarToggle = event.target.closest("[data-a2a-harness-sidebar-toggle]");
      if (sidebarToggle && harnessRoot.contains(sidebarToggle)) {
        event.preventDefault();
        harnessSidebar?.classList.toggle("is-collapsed");
        syncHarnessSidebar();
        return;
      }
      const action = event.target.closest("[data-a2a-harness-action]");
      if (!action || !harnessRoot.contains(action)) return;
      event.preventDefault();
      if (action.dataset.a2aActionPending === "true") return;
      const kind = action.dataset.a2aHarnessAction;
      if (kind === "adopt" || kind === "apply") {
        const choice = harnessRoot.querySelector("[data-a2a-harness-choice]");
        if (!choice?.value) {
          choice?.focus();
          return;
        }
        syncHarnessChoice(choice);
        syncHarnessComment(harnessRoot.querySelector("[data-a2a-harness-comment]"));
      }
      action.dataset.a2aActionPending = "true";
      action.disabled = true;
      action.textContent = kind === "analyse" ? "로그 분석 중…"
        : kind === "run" ? "비교 실행 중…"
        : kind === "apply" ? "의견 반영 중…"
        : kind === "adopt" ? "세션에 채택 중…" : "기본 흐름으로 롤백 중…";
      invokeHarnessAction(
        kind === "analyse"
          ? "#a2a-harness-analyse button, button#a2a-harness-analyse"
          : kind === "run"
          ? "#a2a-harness-run button, button#a2a-harness-run"
          : kind === "apply"
            ? "#a2a-harness-apply button, button#a2a-harness-apply"
            : kind === "adopt"
            ? "#a2a-harness-adopt button, button#a2a-harness-adopt"
            : "#a2a-harness-rollback button, button#a2a-harness-rollback"
      );
    });
    new MutationObserver(syncHarnessSidebar).observe(harnessRoot, {
      childList: true,
      subtree: true,
    });
    syncHarnessSidebar();
    }
  });
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
    """Build the 04-only Team and integration Agent Card panels."""
    team_buttons = []
    team_panels = []
    for index, team in enumerate(AGENT_CATALOG):
        team_id = str(team["agent_id"])
        selected = index == 0
        integration_agent = team.get("executor") == "codex_app_server"
        card_kind = "통합 Agent" if integration_agent else "조직 Team Agent"
        subagents = []
        for subagent_label in team["sub_agents"]:
            if integration_agent:
                subagents.append(
                    '<li class="a2a-topology__subagent">'
                    '<div class="a2a-topology__node-label">'
                    f"<b>App Server · {html.escape(subagent_label)}</b>"
                    "</div>"
                    '<p>기본 HANA 스키마 메타데이터와 단일 SELECT를 읽기 전용·무승인으로 조회합니다. '
                    "파일·명령·외부 쓰기는 수행하지 않습니다.</p>"
                    "</li>"
                )
                continue
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
            f"<small>04 · {card_kind}</small>"
            f"<span>{html.escape(team['description'])}</span>"
            "</button>"
        )
        subagent_heading = (
            '<div class="a2a-topology__subagent-heading">'
            "Codex App Server 실행 경계</div>"
            if integration_agent
            else '<div class="a2a-topology__subagent-heading">Sub-agent와 역할별 Tool</div>'
        )
        team_panels.append(
            '<section class="a2a-topology__team-panel" '
            f'data-a2a-team-panel="{html.escape(team_id)}"'
            f"{' hidden' if not selected else ''}>"
            '<header class="a2a-topology__team-header">'
            f"<span>04 · {card_kind}</span><b>{html.escape(team['agent_label'])}</b>"
            f"<code>{html.escape(team['agent_id'])}</code>"
            "</header>"
            f"<p>{html.escape(team['description'])}</p>"
            + subagent_heading
            + f'<ul class="a2a-topology__subagents">{"".join(subagents)}</ul>'
            + "</section>"
        )
    return (
        '<dialog id="a2a-agent-cards-modal">'
        '<section class="a2a-topology">'
        '<header class="a2a-topology__modal-header">'
        "<div><span>04 · Advanced A2A 카드</span><h2>조직 Team · Codex 통합 Agent</h2></div>"
        '<button type="button" data-a2a-modal-close aria-label="닫기">×</button>'
        "</header>"
        '<p class="a2a-topology__intro">이 목록은 04 Advanced 실습 전용 Card입니다. 조직 Team Card는 LLM으로 필요한 Sub-agent를 선택합니다. Codex 통합 Agent는 기본 HANA 스키마 메타데이터와 단일 SELECT를 읽기 전용으로 조회하며, 03 기본 A2A Card와 별도 921x 포트에서 실행됩니다.</p>'
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
    payload = artifact.get("payload", {}) if isinstance(artifact, dict) else {}
    if isinstance(payload, dict) and isinstance(payload.get("sql_generation"), dict):
        sql_generation = payload["sql_generation"]
        hana_result = payload.get("hana_result")
        result_text = ""
        if isinstance(hana_result, dict):
            rows = hana_result.get("rows")
            row_count = hana_result.get("row_count", 0)
            result_text = f"{row_count}건 반환"
            if isinstance(rows, list) and rows:
                result_text += "\n" + json.dumps(rows, ensure_ascii=False, indent=2)
        error_text = _display_text(payload.get("schema_error") or payload.get("hana_error"))
        return _display_sections(
            ("조회 상태", _display_text(payload.get("team_synthesis", {}).get("summary"))),
            ("생성 SQL", _display_text(sql_generation.get("sql"))),
            ("조회 결과", result_text),
            ("추가 확인 사항", error_text or _display_text(sql_generation.get("missing_inputs"))),
        )
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
    generated_sql = message.get("generated_sql")
    sql_html = (
        '<section class="a2a-group-chat__team-sql">'
        "<span>생성 SQL</span>"
        f"<pre><code>{html.escape(generated_sql)}</code></pre>"
        "</section>"
        if isinstance(generated_sql, str) and generated_sql.strip()
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
        + sql_html
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
    harness_html = message.get("harness_html")
    if isinstance(harness_html, str):
        return harness_html
    harness_action = message.get("harness_action")
    if harness_action == "analyse":
        return (
            '<div class="a2a-harness-action">'
            '<span>완료된 실행 로그를 분석해 개선안을 만듭니다. A2A를 다시 실행하지 않습니다.</span>'
            '<button type="button" data-a2a-harness-action="analyse">실행 로그로 개선안 만들기</button></div>'
        )
    if harness_action == "apply":
        choices = message.get("choices") if isinstance(message.get("choices"), list) else []
        option_html = "".join(
            f'<option value="{html.escape(choice[0], quote=True)}">{html.escape(choice[0].replace("option_", ""))}. {html.escape(choice[1])}{" · AI 추천" if choice[2] else ""}</option>'
            for choice in choices if isinstance(choice, tuple) and len(choice) == 3
        )
        return (
            '<div class="a2a-harness-action"><span>개선 방향 선택</span>'
            f'<select data-a2a-harness-choice aria-label="Harness 개선 방향">{option_html}</select>'
            '<textarea data-a2a-harness-comment rows="2" placeholder="Comment (선택)"></textarea>'
            '<button type="button" data-a2a-harness-action="apply">선택·의견 반영</button></div>'
        )
    if harness_action == "run":
        return (
            '<div class="a2a-harness-action">'
            '<span>기준 실행이 완료되었습니다. 익명 후보를 비교해 볼 수 있습니다.</span>'
            '<button type="button" data-a2a-harness-action="run">Harness² 비교 실행</button>'
            "</div>"
        )
    if harness_action == "adopt":
        choices = message.get("choices")
        choices = choices if isinstance(choices, list) else []
        option_html = '<option value="">사람 채택 후보 선택</option>' + "".join(
            f'<option value="{html.escape(str(choice), quote=True)}">{html.escape(str(choice))}</option>'
            for choice in choices
        )
        return (
            '<div class="a2a-harness-action">'
            '<span>익명 결과를 비교한 뒤, 사람 판단으로 하나를 채택합니다.</span>'
            f'<select data-a2a-harness-choice aria-label="사람 채택 후보">{option_html}</select>'
            '<button type="button" data-a2a-harness-action="adopt">선택 후보를 세션에 채택</button>'
            "</div>"
        )
    if harness_action == "rollback":
        return (
            '<div class="a2a-harness-action a2a-harness-action--rollback">'
            '<span>기대와 다를 때만 기본 흐름으로 되돌립니다.</span>'
            '<button type="button" data-a2a-harness-action="rollback">롤백</button>'
            "</div>"
        )
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
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path d="M7 3v7M10 3v7M7 7h3M8.5 10v11M16 3v18M16 3c3 1.5 3 6.5 0 8"/>'
        "</svg>"
    ),
    "harness": (
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path d="M9 3h6M12 3v6l5 8.5A2.5 2.5 0 0 1 14.8 21H9.2A2.5 2.5 0 0 1 7 17.5L12 9"/>'
        '<path d="M9.5 15h5M18.5 4.5v3M17 6h3"/>'
        "</svg>"
    ),
}


_MESSAGE_AVATAR_ICONS = {
    "department": (
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path d="M4 21V5.5A2.5 2.5 0 0 1 6.5 3h7A2.5 2.5 0 0 1 16 5.5V21M2 21h20M8 7h1M12 7h1M8 11h1M12 11h1M9 21v-5h2v5"/>'
        "</svg>"
    ),
    "orchestrator": _brand_avatar_html("sap_logo.png", "SAP", "sap"),
    "codex": _brand_avatar_html("openai.jpeg", "OpenAI", "codex"),
    "agent": _brand_avatar_html("joule.png", "Joule", "joule"),
    "human": (
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<circle cx="12" cy="8" r="3"/><path d="M5 21a7 7 0 0 1 14 0M17 5l1.3 1.3L21 3.7"/>'
        "</svg>"
    ),
    "mail": (
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/>'
        "</svg>"
    ),
    "harness": _ROOM_AVATAR_ICONS["harness"],
}


def _message_avatar_html(sender: str, kind: str) -> str:
    """Map every chat actor to a fixed role icon instead of an initial letter."""
    normalized = f"{sender} {kind}".lower()
    if kind == "field" or "요청부서" in normalized:
        icon = "department"
    elif "orchestration" in normalized or kind == "orchestrator":
        icon = "orchestrator"
    elif "codex" in normalized:
        icon = "codex"
    elif "harness" in normalized:
        icon = "harness"
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
    sidebar_toggle: bool = False,
) -> str:
    """Render the stable A2A chat shell; later events append in the browser."""
    bubbles = "".join(_chat_message_html(message) for message in messages)
    typing = _typing_bubbles_html(typing_agents)
    toggle = (
        '<button type="button" class="a2a-group-chat__sidebar-toggle" '
        'data-a2a-harness-sidebar-toggle aria-expanded="true" '
        'aria-label="Harness Labs 접기">'
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path d="m14 6-6 6 6 6"/>'
        "</svg></button>"
        if sidebar_toggle
        else ""
    )
    return (
        f'<section class="a2a-group-chat {extra_class}" data-message-count="{len(messages)}">'
        '<header class="a2a-group-chat__header">'
        '<div class="a2a-group-chat__room-title">'
        f'<span class="a2a-group-chat__room-avatar">{_room_avatar_html(avatar_icon)}</span>'
        f"<div><b>{room_title}</b><span>{room_subtitle}</span></div>"
        "</div>"
        f'<span class="a2a-group-chat__room-status">{html.escape(status)}</span>'
        f"{toggle}"
        "</header>"
        f'<div class="a2a-group-chat__messages">{bubbles}<div class="a2a-group-chat__typing-container">{typing}</div></div></section>'
    )


def _harness_messages(
    experiment: dict[str, Any] | None = None,
    adoption: dict[str, Any] | None = None,
    *,
    baseline_ready: bool = False,
) -> list[dict[str, Any]]:
    """Render the separate Harness² panel without exposing a candidate pre-selection."""
    messages: list[dict[str, Any]] = [
        {
            "sender": "Harness²",
            "kind": "system",
            "text": "기준 실행 후 후보 2개와 조합 후보를 비교합니다. 채택 전에는 후보 지침을 공개하지 않습니다.",
        }
    ]
    if not isinstance(experiment, dict):
        if baseline_ready:
            messages.append(
                {
                    "sender": "Harness²",
                    "kind": "system",
                    "harness_action": "run",
                }
            )
        return messages
    if adoption is None:
        stored_adoption = experiment.get("adoption")
        adoption = stored_adoption if isinstance(stored_adoption, dict) else None
    comparison = experiment.get("comparison")
    rows = comparison if isinstance(comparison, list) else []
    messages.append(
        _sectioned_chat_message(
            "Harness Editor",
            "agent",
            ("실험 상태", "기준 실행을 재사용해 후보 2개와 조합 후보를 실행했습니다."),
            ("비교 대상", f"익명 후보 {len(rows)}개"),
            heading="Propose · Probe · Compose",
        )
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("candidate_id") or "?")
        requester_update = row.get("requester_update")
        requester_update = requester_update if isinstance(requester_update, dict) else {}
        team_order = row.get("team_order")
        team_order = team_order if isinstance(team_order, list) else []
        messages.append(
            _sectioned_chat_message(
                f"Probe {candidate_id}",
                "agent",
                ("실행 상태", row.get("status", "unknown")),
                ("Team 순서", " → ".join(str(team) for team in team_order) or "없음"),
                ("Artifact", str(row.get("artifact_count", 0))),
                ("종료 상태", row.get("termination_state", "-")),
                ("요청자 업데이트", requester_update.get("summary", "-")),
                ("근거 요약", row.get("evidence_summaries", [])),
                ("오류", row.get("error", "")),
                heading="익명 실행 결과",
            )
        )
    if isinstance(adoption, dict):
        messages.append(
            _sectioned_chat_message(
                "Human Reviewer",
                "field",
                ("채택 후보", adoption.get("candidate_id", "-")),
                ("하네스", adoption.get("title", "기준 하네스")),
                ("생성 근거", adoption.get("rationale", "-")),
                ("세션용 보조 지침", adoption.get("active_harness") or "기준 하네스 유지"),
                heading="사람 채택 완료",
            )
        )
        messages.append(
            {
                "sender": "Harness²",
                "kind": "system",
                "harness_action": "rollback",
            }
        )
    elif isinstance(experiment.get("rollback"), dict):
        rollback = experiment["rollback"]
        messages.append(
            {
                "sender": "Harness²",
                "kind": "system",
                "text": f"{rollback.get('candidate_id', '-')} 후보의 세션 적용을 롤백했습니다. 이후 요청은 기본 흐름으로 실행됩니다.",
            }
        )
    else:
        choices = [
            str(row.get("candidate_id"))
            for row in rows
            if isinstance(row, dict) and row.get("status") == "ok"
        ]
        if choices:
            messages.append(
                {
                    "sender": "Harness²",
                    "kind": "system",
                    "harness_action": "adopt",
                    "choices": choices,
                }
            )
    return messages


def _harness_chat_html(
    experiment: dict[str, Any] | None = None,
    adoption: dict[str, Any] | None = None,
    *,
    baseline_ready: bool = False,
) -> str:
    return _group_chat_html(
        _harness_messages(experiment, adoption, baseline_ready=baseline_ready),
        room_title="Harness Labs",
        room_subtitle="런타임 오케스트레이션 비교",
        avatar_icon="harness",
        status="세션 전용",
        extra_class="a2a-harness-chat",
        sidebar_toggle=True,
    )


def _harness_dashboard_html(experiment: dict[str, Any] | None = None) -> str:
    """Render deterministic, observable flow metrics for the Harness² lab."""
    if not isinstance(experiment, dict):
        return (
            '<section class="a2a-harness-dashboard">'
            '<b>흐름 개선 대시보드</b><p>기준 실행 후 후보별 실행 흐름을 같은 기준으로 비교합니다.</p>'
            "</section>"
        )
    rows = experiment.get("comparison")
    rows = rows if isinstance(rows, list) else []
    table_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        metrics = evaluate_comparison(row)
        candidate = html.escape(str(row.get("candidate_id", "?")))
        state = html.escape(str(row.get("status", "unknown")))
        table_rows.append(
            "<tr>"
            f"<th>{candidate}</th><td>{state}</td><td>{metrics['score']}/100</td>"
            f"<td>{metrics['team_count']}</td><td>{metrics['evidence_count']}/3</td>"
            f"<td>{metrics['requester_update_fields']}/3</td>"
            f"<td>{metrics['duplicate_team_calls']}</td>"
            "</tr>"
        )
    verification = experiment.get("verification")
    verification_html = ""
    if isinstance(verification, dict):
        state = str(verification.get("state", ""))
        baseline = verification.get("baseline", {})
        applied = verification.get("applied", {})
        labels = {
            "improved": "개선 확인",
            "unchanged": "동일",
            "regressed": "개선 미확인 — 롤백 검토",
            "not_comparable": "비교 불가 — 기준과 동일한 요청을 다시 실행하세요",
        }
        verification_html = (
            '<div class="a2a-harness-dashboard__verification">'
            f"<b>{html.escape(labels.get(state, '검증 대기'))}</b>"
            f"<span>기준 {html.escape(str(baseline.get('score', '-')))}점 → 적용 후 {html.escape(str(applied.get('score', '-')))}점"
            f" (Δ {html.escape(str(verification.get('delta', '-')))})</span>"
            "</div>"
        )
    rollback = experiment.get("rollback")
    rollback_html = (
        '<p class="a2a-harness-dashboard__rollback">현재 기본 흐름으로 롤백됨</p>'
        if isinstance(rollback, dict)
        else ""
    )
    return (
        '<section class="a2a-harness-dashboard">'
        '<b>흐름 개선 대시보드</b>'
        '<p>점수는 완료(25), 요청자 업데이트(30), 근거 요약(30), 중복 Team 호출 없음(15)의 관찰 지표입니다. 업무 정답을 자동 판정하지 않습니다.</p>'
        '<table><thead><tr><th>후보</th><th>실행</th><th>흐름 점수</th><th>Team</th><th>근거</th><th>업데이트</th><th>중복 호출</th></tr></thead>'
        f"<tbody>{''.join(table_rows) or '<tr><td colspan=\"7\">비교 결과가 없습니다.</td></tr>'}</tbody></table>"
        + verification_html
        + rollback_html
        + "</section>"
    )


def _trace_option_html(option: dict[str, Any]) -> str:
    """Render one human-reviewable Harness proposal without exposing unsafe HTML."""
    badge = '<span class="a2a-harness-recommendation">AI 추천</span>' if option.get("recommended") else ""
    evidence = "".join(f"<li>{html.escape(str(item))}</li>" for item in option.get("evidence", []))
    changes = "".join(
        "<li><b>" + html.escape(COMPONENT_LABELS.get(str(change.get("component")), "Runtime"))
        + "</b> · " + html.escape(str(change.get("target", "runtime")))
        + "<br>" + html.escape(str(change.get("instruction", ""))) + "</li>"
        for change in option.get("changes", []) if isinstance(change, dict)
    )
    impact = option.get("impact") if isinstance(option.get("impact"), dict) else {}
    benefit = html.escape(str(impact.get("expected_benefit") or "실행 로그에서 확인된 누락 또는 반복을 줄입니다."))
    controls = html.escape(str(impact.get("mandatory_controls") or "기존 승인·읽기 전용·필수 검증을 유지합니다."))
    build_required = bool(impact.get("build_required"))
    build_badge = "Build 필요" if build_required else "런타임 반영 가능"
    return (
        '<section class="a2a-harness-option">'
        f'<div><b>{html.escape(str(option.get("option_id", "-")))}. {html.escape(str(option.get("title", "개선안")))}</b>{badge}</div>'
        f'<p>{html.escape(str(option.get("rationale", "")))}</p>'
        '<div class="a2a-harness-option__meta">'
        f'<span><b>효과</b> {benefit}</span>'
        f'<span><b>유지 통제</b> {controls}</span>'
        f'<em class="a2a-harness-option__build{" a2a-harness-option__build--required" if build_required else ""}">{build_badge}</em>'
        '</div>'
        f'<span>실행 근거</span><ul>{evidence}</ul>'
        f'<span>변경 사항</span><ul>{changes}</ul>'
        "</section>"
    )


def _trace_harness_chat_html(
    analysis: dict[str, Any] | None = None, *, baseline_ready: bool = False
) -> str:
    messages: list[dict[str, Any]] = [{
        "sender": "Harness Labs", "kind": "system",
        "text": "실제 A2A 실행 로그를 분석해 개선안을 제안합니다. 별도 Probe 실행은 하지 않습니다.",
    }]
    if not isinstance(analysis, dict):
        if baseline_ready:
            messages.append({"sender": "Harness Labs", "kind": "system", "harness_action": "analyse"})
    else:
        decision = str(analysis.get("decision", ""))
        labels = {"no_change": "변경 불필요", "insufficient_evidence": "근거 부족", "propose": "개선안 제안"}
        messages.append(_sectioned_chat_message(
            "Harness Labs", "agent",
            ("분석 결과", labels.get(decision, "분석 완료")),
            ("판단", analysis.get("rationale", "-")),
            ("근거", analysis.get("evidence", [])), heading="실행 로그 분석",
        ))
        if decision == "propose":
            options = [item for item in analysis.get("options", []) if isinstance(item, dict)]
            for option in options:
                messages.append({"sender": "Harness Labs", "kind": "agent", "harness_html": _trace_option_html(option)})
            messages.append({
                "sender": "Human Reviewer", "kind": "field", "harness_action": "apply",
                "choices": [(str(item.get("option_id")), str(item.get("title")), bool(item.get("recommended"))) for item in options],
            })
        elif decision == "no_change":
            messages.append({"sender": "Harness Labs", "kind": "system", "text": "현재 Harness를 유지합니다. Revision은 생성되지 않았습니다."})
        else:
            messages.append({"sender": "Harness Labs", "kind": "system", "text": "충분한 실행 근거가 없어 변경안을 만들지 않았습니다. 다음 실제 실행 후 다시 분석할 수 있습니다."})
        revision = analysis.get("adoption")
        if isinstance(revision, dict):
            reflection = (
                "Build artifact 생성·검토 필요 (원본 소스는 변경하지 않음)"
                if revision.get("build_required")
                else "런타임 overlay 반영 (원본 소스는 변경하지 않음)"
            )
            messages.append(_sectioned_chat_message(
                "Human Reviewer", "field", ("활성 revision", revision.get("title", "-")),
                ("Comment", revision.get("comment") or "없음"),
                ("반영 상태", reflection),
                ("도메인", revision.get("domain", "-")), heading="선택·의견 반영 완료",
            ))
            messages.append({"sender": "Harness Labs", "kind": "system", "harness_action": "rollback"})
    return _group_chat_html(messages, room_title="Harness Labs", room_subtitle="실행 로그 기반 개선", avatar_icon="harness", status="사람 검토", extra_class="a2a-harness-chat", sidebar_toggle=True)


def _trace_harness_dashboard_html(analysis: dict[str, Any] | None = None) -> str:
    if not isinstance(analysis, dict):
        return '<section class="a2a-harness-dashboard"><b>Harness Revision Library</b><p>A2A 실행을 완료하면 로그 기반 개선안을 만들 수 있습니다.</p></section>'
    domain = html.escape(str(analysis.get("domain", "-")))
    library = load_revision_library()
    revisions = [item for item in library.get("revisions", []) if isinstance(item, dict) and item.get("domain") == analysis.get("domain")]
    active_id = library.get("active_by_domain", {}).get(analysis.get("domain"))
    history = "".join(
        f'<li>{html.escape(str(item.get("title", "revision")))} · {html.escape(str(item.get("status", "-")))}</li>'
        for item in revisions[-5:]
    ) or "<li>저장된 revision이 없습니다.</li>"
    return (
        '<section class="a2a-harness-dashboard"><b>Harness Revision Library</b>'
        f'<p>도메인: {domain} · 활성 revision: {html.escape(str(active_id or "없음"))}</p>'
        f'<ul>{history}</ul></section>'
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
    payload = artifact.get("payload", {}) if isinstance(artifact, dict) else {}
    sql_generation = payload.get("sql_generation") if isinstance(payload, dict) else {}
    if isinstance(sql_generation, dict) and isinstance(sql_generation.get("sql"), str):
        message["generated_sql"] = sql_generation["sql"]
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
        active_harness: str | None = None,
        active_grounding: str | None = None,
        experiment: dict[str, Any] | None = None,
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
        if active_harness:
            runtime_harness, runtime_grounding = active_harness, active_grounding or ""
        else:
            runtime_harness, runtime_grounding = active_runtime_overlays_for_request(
                clean_request, settings=settings
            )

        def workflow_output(outcome: dict[str, Any] | None = None):
            active_experiment = experiment if isinstance(experiment, dict) else None
            if (
                outcome is not None and (runtime_harness or runtime_grounding) and active_experiment is not None
                and isinstance(active_experiment.get("trials"), dict)
            ):
                record_live_verification(active_experiment, outcome, clean_request)
            return (
                _chat_payload_html(chat_messages, sorted(typing_agents)),
                chat_messages,
                pending_approvals,
                outcome if outcome is not None else previous_outcome,
                _trace_harness_chat_html(
                    active_experiment,
                    baseline_ready=outcome is not None or previous_outcome is not None,
                ),
                _trace_harness_dashboard_html(active_experiment),
                active_experiment,
            )

        try:
            for event in run_handoff_stream(
                clean_request,
                settings=settings,
                harness_addendum=runtime_harness or None,
                grounding_overlay=runtime_grounding or None,
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
        """Clear this session's A2A chat, approval, and Harness² state."""
        return (
            _chat_payload_html([]),
            [],
            [],
            None,
            _trace_harness_chat_html(),
            _trace_harness_dashboard_html(),
            None,
            "",
            "",
        )

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
        mail_message = {
            "sender": "Outlook",
            "kind": "system",
            "text": "검토자가 메일 발송을 승인했고 Outlook으로 전송했습니다.",
        }
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

    def run_harness_panel(
        request: str | None,
        baseline_result: dict[str, Any] | None,
        chat_log: list[dict[str, Any]] | None = None,
    ):
        """Analyse a completed trace only; never run an additional A2A probe."""
        clean_request = request.strip() if isinstance(request, str) else ""
        if not clean_request or not isinstance(baseline_result, dict):
            raise gr.Error("먼저 왼쪽 협업방에서 기준 A2A 실행을 완료하세요.")
        experiment = analyse_trace(
            clean_request, baseline_result, settings=settings, chat_log=chat_log
        )
        return (
            _trace_harness_chat_html(experiment),
            experiment,
            "",
            _trace_harness_dashboard_html(experiment),
            "",
            "",
        )

    def adopt_harness_panel(
        experiment: dict[str, Any] | None, candidate_id: str | None, comment: str | None
    ):
        if not isinstance(experiment, dict) or not isinstance(candidate_id, str):
            raise gr.Error("개선 방향을 선택하세요.")
        try:
            adoption = apply_human_selection(experiment, candidate_id, comment or "")
        except ValueError as error:
            raise gr.Error(str(error)) from error
        experiment["adoption"] = adoption
        return (
            _trace_harness_chat_html(experiment),
            experiment,
            adoption["overlay"],
            adoption["grounding_overlay"],
            _trace_harness_dashboard_html(experiment),
        )

    def rollback_harness_panel(experiment: dict[str, Any] | None):
        if not isinstance(experiment, dict):
            raise gr.Error("롤백할 Harness revision이 없습니다.")
        try:
            rollback_active_revision(str(experiment.get("domain") or "fnb-general"))
        except ValueError as error:
            raise gr.Error(str(error)) from error
        experiment.pop("adoption", None)
        experiment["rollback"] = True
        return (
            _trace_harness_chat_html(experiment),
            experiment,
            "",
            "",
            _trace_harness_dashboard_html(experiment),
        )

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
    .a2a-group-chat__team-card{padding:10px;border:0;border-radius:9px;background:#f3f6f8;box-shadow:inset 0 0 0 1px rgba(101,121,136,.12)}.a2a-group-chat__team-summary>span,.a2a-group-chat__team-next>span,.a2a-group-chat__team-sql>span{display:block;margin-bottom:4px;color:#587086;font-size:10px;font-weight:800;letter-spacing:.02em}.a2a-group-chat__team-summary p,.a2a-group-chat__team-next p{margin:0}.a2a-group-chat__team-summary ul,.a2a-group-chat__team-next ul{margin:0;padding-left:17px}.a2a-group-chat__team-sql{margin-top:9px;padding-top:9px;border-top:1px solid #dbe3e9}.a2a-group-chat__team-sql pre,.a2a-group-chat__team-sql pre code{max-height:230px;margin:0;overflow:auto;padding:9px;border-radius:7px;background:#202b36!important;color:#eaf2f8!important;font:10px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace!important;white-space:pre}.a2a-group-chat__team-sql pre code{display:block;padding:0}.a2a-group-chat__team-next{margin-top:9px;padding-top:9px;border-top:1px solid #dbe3e9}.a2a-group-chat__team-meta{display:flex;justify-content:flex-end;margin-top:10px;padding-top:9px;border-top:1px solid #dbe3e9}
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
    .a2a-dual-chat-layout{align-items:stretch!important;gap:16px!important}.a2a-dual-chat-layout>.a2a-chat-shell{min-width:0!important}.a2a-dual-chat-layout>.a2a-chat-shell:first-child{display:flex!important;flex-direction:column!important}.a2a-dual-chat-layout>.a2a-chat-shell:first-child>#a2a-group-chat{display:flex!important;min-height:0!important;flex:1 1 auto!important;flex-direction:column!important}.a2a-dual-chat-layout>.a2a-chat-shell:first-child>#a2a-group-chat>.wrap{display:flex!important;min-height:0!important;flex:1 1 auto!important;flex-direction:column!important}.a2a-dual-chat-layout>.a2a-chat-shell:first-child .a2a-group-chat{display:flex!important;height:100%!important;min-height:0!important;flex-direction:column!important}.a2a-dual-chat-layout>.a2a-chat-shell:first-child .a2a-group-chat__messages{height:auto!important;min-height:0!important;flex:1 1 auto!important}.a2a-harness-shell{background:#e7e4f5!important}.a2a-harness-shell .a2a-group-chat{border-radius:16px!important;background:#e7e4f5!important}.a2a-harness-shell .a2a-group-chat__header{background:#e2dcff!important;color:#322965!important}.a2a-harness-shell .a2a-group-chat__room-avatar{background:#5d4d9b!important;color:#fff!important}.a2a-harness-shell .a2a-group-chat__room-title span:not(.a2a-group-chat__room-avatar),.a2a-harness-shell .a2a-group-chat__room-status{color:#5d4d8b!important}.a2a-harness-shell .a2a-group-chat__room-status::before{background:#806ad0!important}.a2a-harness-shell .a2a-group-chat__messages{height:800px;background:#e7e4f5!important}.a2a-harness-shell .a2a-group-chat__section{background:#f5f2ff!important}.a2a-harness-shell .a2a-group-chat__title{color:#55438f!important}.a2a-harness-action{display:grid;gap:7px;min-width:min(100%,340px);padding:3px 1px;text-align:left}.a2a-harness-action span{color:#fff;font-size:11px;line-height:1.45}.a2a-harness-action select,.a2a-harness-action button{width:100%;min-height:34px;padding:7px 9px;border:0;border-radius:8px;background:#fff;color:#4c3e84;font:inherit;font-size:11px;font-weight:800}.a2a-harness-action select{border:1px solid #c8bff2;font-weight:600}.a2a-harness-action button{cursor:pointer}.a2a-harness-action button:hover{background:#f0ecff}.a2a-harness-shell .a2a-group-chat__system:has(.a2a-harness-action){max-width:min(92%,360px);padding:9px 10px;border-radius:11px;background:#7766b3!important}.a2a-harness-shell .a2a-group-chat__system:has(.a2a-harness-action) button:disabled{opacity:.72;cursor:default}@media(max-width:900px){.a2a-dual-chat-layout{flex-direction:column!important}.a2a-dual-chat-layout>.a2a-chat-shell{width:100%!important}.a2a-harness-shell .a2a-group-chat__messages{height:400px!important}}
    """
    css += """
    .a2a-group-chat__room-avatar svg{width:22px;height:22px;fill:none;stroke:#fff!important;stroke-linecap:round;stroke-linejoin:round;stroke-width:2.25}
    """
    css += """
    .a2a-group-chat__avatar svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.9}
    """
    css += """
    .a2a-harness-dashboard{margin:10px 12px 12px;padding:11px;border:1px solid #cfc6f0;border-radius:10px;background:#faf9ff;color:#443876;font-size:11px;line-height:1.45}.a2a-harness-dashboard>b{display:block;font-size:12px}.a2a-harness-dashboard>p{margin:4px 0 9px;color:#665b90}.a2a-harness-dashboard table{width:100%;border-collapse:collapse;background:#fff;font-size:10px}.a2a-harness-dashboard th,.a2a-harness-dashboard td{padding:5px;border:1px solid #e2dcf5;text-align:center}.a2a-harness-dashboard thead th{background:#eeeaff;color:#514281}.a2a-harness-dashboard tbody th{background:#f7f5ff}.a2a-harness-dashboard__verification{display:flex;gap:6px;align-items:baseline;flex-wrap:wrap;margin-top:9px;padding:8px;border-radius:7px;background:#e9f7ed;color:#17683c}.a2a-harness-dashboard__verification span{font-size:10px}.a2a-harness-dashboard__rollback{margin-bottom:0!important;color:#7a4f1b!important;font-weight:800}@media(max-width:700px){.a2a-harness-dashboard{margin:8px}.a2a-harness-dashboard table{font-size:9px}.a2a-harness-dashboard th,.a2a-harness-dashboard td{padding:4px 2px}}
    """
    css += """
    #a2a-harness-sidebar{transition:flex-basis .2s ease,max-width .2s ease,min-width .2s ease}.a2a-group-chat__sidebar-toggle{display:grid;place-items:center;flex:none;width:28px;height:28px;padding:0;border:0;border-radius:8px;background:rgba(70,55,133,.12);color:#4d3c86;cursor:pointer}.a2a-group-chat__sidebar-toggle:hover{background:rgba(70,55,133,.22)}.a2a-group-chat__sidebar-toggle svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round;stroke-width:2;transition:transform .2s ease}#a2a-harness-sidebar.is-collapsed{align-self:flex-start!important;min-width:74px!important;max-width:74px!important;flex:0 0 74px!important;background:transparent!important;box-shadow:none!important}#a2a-harness-sidebar.is-collapsed .a2a-group-chat{border-radius:16px!important}#a2a-harness-sidebar.is-collapsed .a2a-group-chat__header{justify-content:center;padding:9px 7px!important}#a2a-harness-sidebar.is-collapsed .a2a-group-chat__room-title{gap:5px}#a2a-harness-sidebar.is-collapsed .a2a-group-chat__room-title>div,#a2a-harness-sidebar.is-collapsed .a2a-group-chat__room-status,#a2a-harness-sidebar.is-collapsed .a2a-group-chat__messages{display:none!important}#a2a-harness-sidebar.is-collapsed .a2a-group-chat__sidebar-toggle svg{transform:rotate(180deg)}.a2a-dual-chat-layout:has(#a2a-harness-sidebar.is-collapsed)>.a2a-chat-shell:first-child{flex:1 1 auto!important}
    """
    css += """
    .a2a-dual-chat-layout>.a2a-chat-shell:first-child .a2a-group-chat__messages{min-height:800px!important}@media(max-width:900px){.a2a-dual-chat-layout>.a2a-chat-shell:first-child .a2a-group-chat__messages{min-height:400px!important}}
    """
    css += """
    /* Keep both conversations stable in the notebook: messages scroll inside a fixed viewport. */
    .a2a-dual-chat-layout .a2a-group-chat__messages{box-sizing:border-box!important;height:600px!important;min-height:600px!important;max-height:600px!important;flex:0 0 600px!important;overflow-x:hidden!important;overflow-y:auto!important;overscroll-behavior:contain}@media(max-width:900px){.a2a-dual-chat-layout .a2a-group-chat__messages{height:400px!important;min-height:400px!important;max-height:400px!important;flex-basis:400px!important}}
    """
    css += """
    /* SAP Joule / Fiori conversation surface, shared with the base A2A chat. */
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
    .a2a-harness-shell{border-color:#d8d0ec!important;background:#fff!important}.a2a-harness-shell .a2a-group-chat{background:#fff!important}.a2a-harness-shell .a2a-group-chat__header{background:linear-gradient(105deg,#5b3fa9,#8a5cd1)!important;color:#fff!important}.a2a-harness-shell .a2a-group-chat__room-avatar{background:rgba(255,255,255,.2)!important;color:#fff!important}.a2a-harness-shell .a2a-group-chat__room-title span:not(.a2a-group-chat__room-avatar),.a2a-harness-shell .a2a-group-chat__room-status{color:rgba(255,255,255,.84)!important}.a2a-harness-shell .a2a-group-chat__room-status::before{background:#c4b5fd!important}.a2a-harness-shell .a2a-group-chat__messages{background:#fbfaff!important}.a2a-harness-shell .a2a-group-chat__section{background:#f4f0ff!important}.a2a-harness-action select{border-color:#cfc2ee!important}.a2a-harness-action button{background:#5d3ec1!important;color:#fff!important}.a2a-harness-action button:hover{background:#4c30aa!important}.a2a-harness-shell .a2a-group-chat__system:has(.a2a-harness-action){background:#6c50bb!important;color:#fff!important}.a2a-harness-dashboard{border-color:#d9cfef!important;background:#fbfaff!important;color:#49377a!important}.a2a-harness-dashboard>p{color:#6b5a96!important}.a2a-harness-dashboard thead th{background:#eee8ff!important;color:#50398e!important}
    .a2a-harness-option{padding:10px;border:1px solid #ded5f0;border-radius:10px;background:#fff}.a2a-harness-option>div{display:flex;gap:7px;align-items:center;color:#443177}.a2a-harness-option p{margin:7px 0;color:#4e4661;font-size:12px;line-height:1.5}.a2a-harness-option>span{display:block;margin-top:8px;color:#7059a0;font-size:10px;font-weight:800}.a2a-harness-option ul{margin:4px 0 0;padding-left:17px;color:#5a526b;font-size:11px;line-height:1.5}.a2a-harness-option__meta{display:grid!important;gap:5px!important;margin-top:8px;padding:8px!important;border-radius:8px!important;background:#f8f6ff!important}.a2a-harness-option__meta span{display:block!important;margin:0!important;color:#5a4d7d!important;font-size:10px!important;font-weight:500!important;line-height:1.4!important}.a2a-harness-option__meta b{color:#4a3980}.a2a-harness-option__build{justify-self:start;padding:3px 6px;border-radius:999px;background:#e9f7ed;color:#17683c;font-size:10px;font-style:normal;font-weight:800}.a2a-harness-option__build--required{background:#fff0d6;color:#8a5200}.a2a-harness-recommendation{display:inline-block!important;margin:0!important;padding:3px 6px;border-radius:999px;background:#ede6ff;color:#5133a0!important;font-size:10px!important;white-space:nowrap}.a2a-harness-chat .a2a-group-chat__row--field .a2a-group-chat__bubble:has(.a2a-harness-action){width:min(100%,480px);padding:12px!important;border:1px solid #d9cfef!important;border-radius:12px!important;background:#fff!important;color:#31294a!important;box-shadow:0 2px 6px rgba(72,49,151,.09)!important}.a2a-harness-action{display:grid;gap:8px;color:#31294a!important;text-align:left}.a2a-harness-action>span{display:block!important;margin:0!important;color:#51486a!important;font-size:12px!important;font-weight:800!important;line-height:1.35!important}.a2a-harness-action select{box-sizing:border-box;width:100%;height:36px!important;padding:0 10px!important;border:1px solid #cfc2ee!important;border-radius:8px!important;background:#fff!important;color:#413464!important;font-size:12px!important;font-weight:700!important}.a2a-harness-action textarea{display:block;box-sizing:border-box;width:100%;min-height:48px!important;height:48px!important;margin:0!important;padding:8px 10px!important;border:1px solid #cfc2ee;border-radius:8px;background:#fff;color:#342a4f;font:12px/1.35 inherit;resize:vertical}.a2a-harness-action textarea::placeholder{color:#7e7494;opacity:1}.a2a-harness-action textarea:focus{outline:0;border-color:#7452cc;box-shadow:0 0 0 2px rgba(116,82,204,.18)}.a2a-harness-action button{width:fit-content!important;min-width:128px!important;height:32px!important;margin-top:0!important;padding:6px 12px!important;border-radius:8px!important;font-size:12px!important}.a2a-harness-shell .a2a-group-chat__system:has(.a2a-harness-action--rollback){box-sizing:border-box!important;width:min(100%,500px)!important;max-width:calc(100% - 24px)!important;margin:10px auto 14px!important;padding:10px 12px!important;border:1px solid #d9cfef!important;border-radius:10px!important;background:#fff!important;color:#31294a!important;box-shadow:0 1px 3px rgba(72,49,151,.08)!important}.a2a-harness-action--rollback{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;min-width:0!important}.a2a-harness-action--rollback>span{flex:1!important;color:#5d5470!important;font-size:11px!important;font-weight:600!important}.a2a-harness-action--rollback button{flex:none!important;min-width:0!important;height:30px!important;padding:5px 11px!important;border:1px solid #d1c5ed!important;background:#f6f2ff!important;color:#5838aa!important}.a2a-harness-action--rollback button:hover{border-color:#9f87dc!important;background:#ece5ff!important}
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
        with gr.Row(elem_classes=["a2a-dual-chat-layout"]):
            with gr.Column(scale=3, elem_classes=["a2a-chat-shell"]):
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
            with gr.Column(
                scale=2,
                elem_id="a2a-harness-sidebar",
                elem_classes=["a2a-chat-shell", "a2a-harness-shell"],
            ):
                harness_chat = gr.HTML(
                    _trace_harness_chat_html(),
                    label="Harness² comparison conversation",
                    elem_id="a2a-harness-chat",
                )
                harness_dashboard = gr.HTML(
                    _trace_harness_dashboard_html(),
                    label="Harness² flow improvement dashboard",
                    elem_id="a2a-harness-dashboard",
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
        harness_choice = gr.Textbox(
            "",
            elem_id="a2a-harness-choice",
            elem_classes=["a2a-hidden-chat-action"],
            container=False,
        )
        harness_comment = gr.Textbox(
            "",
            elem_id="a2a-harness-comment",
            elem_classes=["a2a-hidden-chat-action"],
            container=False,
        )
        harness_analyse_button = gr.Button(
            "실행 로그로 개선안 만들기",
            elem_id="a2a-harness-analyse",
            elem_classes=["a2a-hidden-chat-action"],
        )
        harness_run_button = gr.Button(
            "Harness² 비교 실행",
            elem_id="a2a-harness-run",
            elem_classes=["a2a-hidden-chat-action"],
        )
        harness_adopt_button = gr.Button(
            "선택·의견 반영",
            elem_id="a2a-harness-adopt",
            elem_classes=["a2a-hidden-chat-action"],
        )
        harness_apply_button = gr.Button(
            "선택·의견 반영",
            elem_id="a2a-harness-apply",
            elem_classes=["a2a-hidden-chat-action"],
        )
        harness_rollback_button = gr.Button(
            "Harness² 세션 적용 롤백",
            elem_id="a2a-harness-rollback",
            elem_classes=["a2a-hidden-chat-action"],
        )
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
        harness_experiment = gr.State(None)
        active_harness = gr.State("")
        active_grounding = gr.State("")
        with (
            gr.Accordion("업무 시나리오", open=True),
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
            harness_chat,
            harness_dashboard,
            harness_experiment,
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
                active_harness,
                active_grounding,
                harness_experiment,
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
            outputs=[*workflow_outputs, active_harness, active_grounding],
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
        harness_analyse_button.click(
            run_harness_panel,
            inputs=[request, last_outcome, chat_history],
            outputs=[
                harness_chat,
                harness_experiment,
                harness_choice,
                harness_dashboard,
                active_harness,
                active_grounding,
            ],
            queue=True,
            scroll_to_output=False,
        )
        harness_apply_button.click(
            adopt_harness_panel,
            inputs=[harness_experiment, harness_choice, harness_comment],
            outputs=[
                harness_chat,
                harness_experiment,
                active_harness,
                active_grounding,
                harness_dashboard,
            ],
            queue=False,
            scroll_to_output=False,
        )
        harness_rollback_button.click(
            rollback_harness_panel,
            inputs=harness_experiment,
            outputs=[
                harness_chat,
                harness_experiment,
                active_harness,
                active_grounding,
                harness_dashboard,
            ],
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
