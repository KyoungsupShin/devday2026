"""Gradio presentation adapter for the 01 agent workflow lab."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gradio as gr
import mistune
from lab_common.ai_core import chat_text
from lab_common.config import Settings, load_settings

from .food_agents import FOOD_AGENT_DEFINITIONS
from .food_tools import (
    latest_marketing_html_draft,
    marketing_image_asset,
    tool_catalog_for_food_agent,
)
from .lab_core import build_contextual_request, run_workflow_stream

STEP_META = {
    "fast_route": ("①", "빠른 경로 판별"),
    "agent_started": ("②", "Agent 실행 시작"),
    "agent_completed": ("③", "Agent 응답 완료"),
    "chat_response": ("②", "Chat response"),
    "evaluation_started": ("④", "Execution 평가"),
    "evaluation_completed": ("⑤", "평가 완료"),
    "revision_started": ("⑥", "보완 실행"),
}

DEFAULT_WORKFLOW_REQUEST = (
    "편의점용 고단백 닭가슴살 도시락을 출시하려고 합니다. 판매가 4,500원, 단백질 30g 이상, "
    "전자레인지 조리 가능 조건으로 콘셉트·레시피·원가·공급망·식품안전·마케팅·손익분기점을 "
    "종합 검토해 출시 권고안을 작성해주세요. 모든 수치에는 가정을 표시해주세요."
)

DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "debug" / "latest_workflow_conversation.json"


def write_latest_workflow_debug_log(snapshot: dict[str, Any], path: Path = DEBUG_LOG_PATH) -> Path:
    """Atomically replace the latest UI conversation snapshot for local debugging.

    The snapshot deliberately contains prompts, responses, trace and tool metadata,
    but never `Settings`, environment variables, or credentials.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **snapshot,
    }
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary_path.replace(path)
    return path


def _plain_conversation_history(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Keep only the semantic conversation, never UI status/dashboard HTML."""
    plain: list[dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            plain.append({"role": role, "content": content.strip()})
    return plain


def _html_tool_draft_created(tool_calls: list[dict[str, Any]]) -> bool:
    """Detect a draft artifact without placing its potentially large image in trace data."""
    return any(
        isinstance(call, dict)
        and call.get("name") == "generate_marketing_html"
        and isinstance(call.get("result"), dict)
        and call["result"].get("html_draft_created") is True
        for call in tool_calls
    )


def _agent_tool_catalog_panel(agent_id: str) -> str:
    """Render the selected Agent's assigned local MCP-style tool contracts."""
    agent = next((item for item in FOOD_AGENT_DEFINITIONS if item.id == agent_id), None)
    if agent is None:
        return '<p style="color:#b3261e">선택한 Agent를 찾을 수 없습니다.</p>'
    tools = tool_catalog_for_food_agent(agent_id)
    tool_cards = "".join(
        f'''<article class="agent-tool-catalog__tool">
          <div><code>{html.escape(tool["name"])}</code><span>{html.escape(tool["type"])}</span></div>
          <p>{html.escape(tool["description"])}</p>
        </article>'''
        for tool in tools
    ) or '<p class="agent-tool-catalog__empty">연결된 MCP-style 도구가 없습니다.</p>'
    return f'''<section class="agent-tool-catalog">
      <p class="agent-tool-catalog__eyebrow">Agent</p>
      <h3>{html.escape(agent.label)}</h3>
      <p class="agent-tool-catalog__description">{html.escape(agent.description)}</p>
      <p class="agent-tool-catalog__boundary">MCP lesson의 로컬 읽기 전용 Tool Calling 계약입니다. Agent가 필요하다고 판단할 때만 호출합니다.</p>
      <div class="agent-tool-catalog__tools">{tool_cards}</div>
    </section>'''

WORKFLOW_GRAPH_SVG = """
<svg viewBox="0 0 1420 410" width="86%" style="display:block;margin:0 auto" role="img" aria-label="LLM-orchestrated agent workflow with evaluation middleware" xmlns="http://www.w3.org/2000/svg">
  <style>.node{fill:#fff;stroke:#8ab4f8;stroke-width:2}.work{fill:#f8fbff;stroke:#4285f4;stroke-width:2}.end{fill:#e6f4ea;stroke:#34a853;stroke-width:2}.label{font:600 15px sans-serif;fill:#202124}.small{font:13px sans-serif;fill:#5f6368}.edge{fill:none;stroke:#5f6368;stroke-width:2;marker-end:url(#arrow)}</style>
  <defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#5f6368"/></marker></defs>
  <text x="26" y="31" class="label" style="font-size:18px">LLM-Orchestrated Food Workflow</text>
  <rect x="25" y="170" width="150" height="64" rx="12" class="node"/><text x="100" y="198" text-anchor="middle" class="label">User request</text><text x="100" y="218" text-anchor="middle" class="small">message</text>
  <rect x="240" y="155" width="180" height="94" rx="12" class="work"/><text x="330" y="190" text-anchor="middle" class="label">Cohere Rerank</text><text x="330" y="213" text-anchor="middle" class="small">Chat / Work</text>
  <rect x="500" y="57" width="175" height="64" rx="12" class="end"/><text x="587" y="85" text-anchor="middle" class="label">Chat response</text><text x="587" y="105" text-anchor="middle" class="small">direct response</text>
  <rect x="500" y="270" width="175" height="76" rx="12" class="work"/><text x="587" y="300" text-anchor="middle" class="label">Work Planning Agents</text><text x="587" y="323" text-anchor="middle" class="small">LLM orchestrator</text>
  <rect x="755" y="250" width="210" height="115" rx="12" class="node"/><text x="860" y="280" text-anchor="middle" class="label">Selected Specialists</text><text x="860" y="305" text-anchor="middle" class="small">LLM-selected agents</text><text x="860" y="327" text-anchor="middle" class="small">ordered parallel stages</text>
  <rect x="1020" y="250" width="190" height="115" rx="12" class="work"/><text x="1115" y="278" text-anchor="middle" class="label">Evaluation Middleware</text><text x="1115" y="303" text-anchor="middle" class="small">LLM result + Tool audit</text><text x="1115" y="325" text-anchor="middle" class="small">pass / revise · max 3</text>
  <rect x="1265" y="270" width="130" height="76" rx="12" class="end"/><text x="1330" y="300" text-anchor="middle" class="label">Result</text><text x="1330" y="323" text-anchor="middle" class="small">approved output</text>
  <path d="M175 202 H240" class="edge"/><path d="M420 177 C450 177 450 89 500 89" class="edge"/><text x="444" y="118" class="small">chat</text><path d="M420 225 C450 225 450 308 500 308" class="edge"/><text x="440" y="271" class="small">work</text><path d="M675 308 H755" class="edge"/><path d="M965 308 H1020" class="edge"/><path d="M1210 308 H1265" class="edge"/><text x="1225" y="294" class="small">pass</text><path d="M1115 365 C1115 405 860 405 860 365" class="edge"/><text x="962" y="400" class="small">revise · max 3</text>
</svg>
"""

SETTINGS_MODAL_CSS = """
#workflow-settings-modal {
  position: fixed !important; inset: 16vh 24vw auto !important; z-index: 1000 !important;
  max-width: 620px !important; padding: 20px !important; border: 1px solid #d0d7de !important;
  border-radius: 14px !important; background: white !important;
  box-shadow: 0 18px 60px rgba(0,0,0,.22) !important;
}

#agent-tool-modal {
  position: fixed !important; inset: 8vh 12vw auto !important; z-index: 1000 !important;
  max-width: 1040px !important; max-height: 82vh; overflow: auto; padding: 20px !important;
  border: 1px solid #d0d7de !important; border-radius: 14px !important; background: white !important;
  box-shadow: 0 18px 60px rgba(0,0,0,.22) !important;
}
#agent-tool-modal .agent-tool-catalog { padding: 4px 8px; }
#agent-tool-modal .agent-tool-catalog__eyebrow { margin:0 0 4px; color:#174ea6; font-size:12px; font-weight:700; text-transform:uppercase; }
#agent-tool-modal .agent-tool-catalog h3 { margin:0; color:#202124; font-size:22px; }
#agent-tool-modal .agent-tool-catalog__description { margin:8px 0; color:#374151; line-height:1.5; }
#agent-tool-modal .agent-tool-catalog__boundary, #agent-tool-modal .agent-tool-catalog__note { margin:10px 0; padding:9px 10px; border-radius:8px; background:#f8fbff; color:#5f6368; font-size:13px; line-height:1.45; }
#agent-tool-modal .agent-tool-catalog__tools { display:grid; gap:9px; margin-top:14px; }
#agent-tool-modal .agent-tool-catalog__tool { padding:11px 12px; border:1px solid #f2c46d; border-radius:9px; background:#fffdf5; }
#agent-tool-modal .agent-tool-catalog__tool div { display:flex; align-items:center; justify-content:space-between; gap:8px; }
#agent-tool-modal .agent-tool-catalog__tool code { color:#855d00; font-weight:700; }
#agent-tool-modal .agent-tool-catalog__tool span { padding:2px 6px; border-radius:999px; background:#fff1c7; color:#855d00; font-size:11px; white-space:nowrap; }
#agent-tool-modal .agent-tool-catalog__tool p { margin:7px 0 0; color:#374151; font-size:13px; line-height:1.45; }
#agent-tool-modal .agent-tool-catalog__empty { color:#6b7280; }
@media (max-width: 700px) { #agent-tool-modal { inset:4vh 4vw auto !important; } }

.agent-dashboard { padding: 14px; border: 1px solid #c7d2e1; border-radius: 12px; background: #f8fbff; }
.agent-dashboard__header { display:flex; justify-content:space-between; align-items:baseline; gap:12px; margin-bottom:10px; }
.agent-dashboard__title { font-size:14px; font-weight:700; color:#174ea6; }
.agent-dashboard__caption { color:#5f6368; font-size:11px; }
.agent-dashboard__grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:8px; }
.agent-card { min-height:150px; border:1px solid #c7d2e1; border-radius:10px; background:#fff; overflow:hidden; }
.agent-card__header { display:flex; justify-content:space-between; align-items:center; gap:5px; padding:8px 9px; border-bottom:1px solid #e5e7eb; }
.agent-card__name { color:#174ea6; font-size:.78em; font-weight:700; }
.agent-card__badge { flex:none; border-radius:999px; padding:2px 5px; font-size:.64em; font-weight:700; }
.agent-card__badge--queued { color:#5f6368; background:#f1f3f4; }
.agent-card__badge--running { color:#b45309; background:#fff7ed; }
.agent-card__badge--completed { color:#137333; background:#e6f4ea; }
.agent-card__body { max-height:210px; overflow:auto; padding:8px 9px; color:#374151; font-size:.76em; line-height:1.45; }
.agent-card__waiting { color:#6b7280; }
@media (max-width: 1100px) { .agent-dashboard__grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
@media (max-width: 700px) { .agent-dashboard__grid { grid-template-columns:1fr; } }
/* Keep conversation text one step smaller than Gradio's 16px default. */
#workflow-conversation .message,
#workflow-conversation .prose { font-size:15px !important; }
#workflow-conversation .agent-card__body { font-size:12px; }
#workflow-chat-shell { gap:0 !important; overflow:hidden; border:1px solid #c7d2e1; border-radius:12px; background:#fff; }
#workflow-chat-shell #workflow-conversation { border:0 !important; }
#workflow-chat-shell #workflow-conversation > .wrap { border:0 !important; border-radius:0 !important; }
#workflow-composer { margin:0 !important; padding:6px 10px 8px; border-top:1px solid #d9e2f3; background:#f8fbff; }
#workflow-composer > .wrap { margin:0 !important; }
#workflow-composer textarea { min-height:32px !important; height:32px !important; background:#fff !important; }
.workflow-collapsible { margin:6px 0; border:1px solid #d9e2f3; border-radius:8px; background:#f8fbff; }
.workflow-collapsible summary { cursor:pointer; padding:8px 10px; color:#174ea6; font-size:12px; font-weight:700; }
.workflow-collapsible__content { padding:0 10px 10px; }
.workflow-final-answer { margin:20px 0 6px; padding:14px 16px; border:1px solid #86b7fe; border-radius:12px; background:#fff; box-shadow:0 2px 8px rgba(23,78,166,.10); }
.workflow-final-answer__title { margin-bottom:8px; color:#174ea6; font-size:12px; font-weight:700; }
"""

_AGENT_MARKDOWN = mistune.create_markdown(escape=True, plugins=["table", "strikethrough"])


def _status_timeline(
    trace: list[dict[str, Any]],
    running: bool = False,
    show_tool_calling: bool = False,
    collapsed: bool = False,
) -> gr.HTML:
    """Render one evolving timeline row per Agent, rather than start/completion pairs."""
    items: list[dict[str, str]] = []
    agent_item_index: dict[str, int] = {}
    evaluation_item_index: int | None = None
    for event in trace:
        event_name = event["event"]
        data = event.get("payload", event.get("data", {}))
        if event_name == "fast_route":
            detail = html.escape(str(data.get("selected", "")))
            if data.get("engine"):
                detail += f' <span style="color:#6b7280">· {html.escape(str(data["engine"]))}</span>'
            if data.get("low_confidence"):
                detail += ' <span style="color:#b45309">· 낮은 신뢰도</span>'
            items.append({"icon": "①", "title": "빠른 경로 판별", "detail": detail})
            continue
        if event_name == "agent_started":
            agent_id = str(data["agent_id"])
            agent_item_index[agent_id] = len(items)
            items.append({
                "icon": "②",
                "title": "Agent 실행",
                "detail": f'{html.escape(str(data["label"]))} <span style="color:#b45309">· 실행 중</span>',
            })
            continue
        if event_name == "agent_completed":
            agent_id = str(data["agent_id"])
            tool_detail = ""
            if show_tool_calling and data.get("tool_calls"):
                names = ", ".join(
                    html.escape(str(call.get("name", "Tool")))
                    for call in data["tool_calls"]
                    if isinstance(call, dict)
                )
                if names:
                    tool_detail = f' <span style="color:#6b7280">· Tool: {names}</span>'
            completed_item = {
                "icon": "③",
                "title": "Agent 완료",
                "detail": f'{html.escape(str(data["label"]))} <span style="color:#137333">· 완료</span>{tool_detail}',
            }
            if agent_id in agent_item_index:
                items[agent_item_index[agent_id]] = completed_item
            else:
                agent_item_index[agent_id] = len(items)
                items.append(completed_item)
            continue
        if event_name == "evaluation_started":
            loop = data.get("loop", "?")
            maximum = data.get("max_loops", "?")
            evaluation_item_index = len(items)
            items.append({
                "icon": "④",
                "title": "Execution 평가",
                "detail": f"Evaluation Middleware <span style=\"color:#b45309\">· {loop}/{maximum} 평가 중</span>",
            })
            continue
        if event_name == "evaluation_completed":
            verdict = str(data.get("verdict", ""))
            verdict_text = "승인" if verdict == "pass" else "보완 요청"
            color = "#137333" if verdict == "pass" else "#b45309"
            loop = data.get("loop", "?")
            maximum = data.get("max_loops", "?")
            reason = html.escape(str(data.get("reason", "")))
            completed_item = {
                "icon": "⑤",
                "title": "Execution 평가",
                "detail": f"Evaluation Middleware <span style=\"color:{color}\">· {loop}/{maximum} {verdict_text}</span>" + (f"<br><span style=\"color:#6b7280\">{reason}</span>" if reason else ""),
            }
            if evaluation_item_index is None:
                evaluation_item_index = len(items)
                items.append(completed_item)
            else:
                items[evaluation_item_index] = completed_item
            continue
        if event_name == "revision_started":
            stages = data.get("stages", [])
            revised_ids = [agent_id for stage in stages if isinstance(stage, dict) for agent_id in stage.get("agent_ids", [])]
            labels = {agent.id: agent.label for agent in FOOD_AGENT_DEFINITIONS}
            names = ", ".join(html.escape(labels.get(str(agent_id), str(agent_id))) for agent_id in revised_ids)
            items.append({
                "icon": "⑥",
                "title": "보완 실행",
                "detail": f"{names or '선택된 Agent'} <span style=\"color:#b45309\">· 재실행</span>",
            })
            continue
        if event_name == "evaluation_limit_reached":
            items.append({
                "icon": "!",
                "title": "Execution 평가",
                "detail": "Evaluation Middleware <span style=\"color:#b45309\">· 최대 3회 도달, 현재 결과 반환</span>",
            })

    steps: list[str] = []
    for index, item in enumerate(items):
        steps.append(
            f'''<div style="display:flex;align-items:flex-start;gap:7px"><span style="display:inline-grid;place-items:center;flex:none;width:19px;height:19px;border-radius:50%;background:#e6f4ea;color:#137333;font-size:11px;font-weight:700">{item["icon"]}</span><span style="padding-top:1px"><span style="font-weight:600;color:#174ea6;font-size:12px">{item["title"]}</span><span style="color:#374151;font-size:12px"> {item["detail"]}</span></span></div>'''
        )
        if index < len(items) - 1 or running:
            steps.append('<div style="height:10px;margin:1px 0 1px 9px;border-left:1px solid #9ca3af"></div>')
    if running:
        steps.append('<div style="display:flex;align-items:center;gap:7px;color:#174ea6;font-size:12px"><span style="font-size:14px">◌</span> 실행 중</div>')
    content = "".join(steps) or '<span style="color:#6b7280;font-size:12px">workflow를 시작합니다…</span>'
    if collapsed:
        return gr.HTML(
            f'<details class="workflow-collapsible"><summary>Workflow 상태 · {len(items)}단계 완료</summary><div class="workflow-collapsible__content">{content}</div></details>',
            container=False,
        )
    return gr.HTML(f'<div style="margin:6px 0;padding:8px 10px;border:1px solid #d9e2f3;border-radius:8px;background:#f8fbff">{content}</div>', container=False)


def _tool_calling_details(agent_id: str, tool_calls: list[dict[str, Any]]) -> str:
    """Return a compact, read-only audit view for a specialist's chosen tools."""
    tool_types = {tool["name"]: tool["type"] for tool in tool_catalog_for_food_agent(agent_id)}
    rows: list[str] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        name = html.escape(str(call.get("name", "Tool")))
        kind = html.escape(tool_types.get(str(call.get("name", "")), "Tool"))
        arguments = html.escape(json.dumps(call.get("arguments", {}), ensure_ascii=False))
        result_value = call.get("result", {})
        if kind == "Agent as a Tool" and isinstance(result_value, dict) and isinstance(result_value.get("asset_id"), str):
            image_data_url = marketing_image_asset(result_value["asset_id"])
            image_preview = (
                f'<br><img src="{html.escape(image_data_url, quote=True)}" alt="Marketing Image Agent 생성 이미지" style="margin-top:6px;width:100%;max-height:160px;object-fit:cover;border-radius:6px">'
                if image_data_url
                else '<br><span style="color:#6b7280">이미지 asset은 현재 UI 프로세스에 없습니다.</span>'
            )
            rows.append(
                f'<li><b>{name}</b> <span style="color:#6b7280">({kind})</span>'
                f'<br><span style="color:#6b7280">입력:</span> <code>{arguments}</code>'
                f'<br><span style="color:#6b7280">Marketing Image Agent · {html.escape(str(result_value["asset_id"]))}</span>{image_preview}</li>'
            )
            continue
        if kind == "Agent as a Tool" and isinstance(result_value, dict) and isinstance(result_value.get("html"), str):
            html_draft = result_value["html"]
            rows.append(
                f'<li><b>{name}</b> <span style="color:#6b7280">({kind})</span>'
                f'<br><span style="color:#6b7280">입력:</span> <code>{arguments}</code>'
                '<br><span style="color:#6b7280">Marketing HTML Agent 결과</span>'
                f'<pre style="max-height:120px;overflow:auto;white-space:pre-wrap">{html.escape(html_draft)}</pre>'
                f'<iframe title="Marketing HTML preview" sandbox="" style="width:100%;height:180px;border:1px solid #d9e2f3;border-radius:6px;background:white" srcdoc="{html.escape(html_draft, quote=True)}"></iframe></li>'
            )
            continue
        result = html.escape(json.dumps(result_value, ensure_ascii=False))
        rows.append(
            f'<li><b>{name}</b> <span style="color:#6b7280">({kind})</span>'
            f'<br><span style="color:#6b7280">입력:</span> <code>{arguments}</code>'
            f'<br><span style="color:#6b7280">결과:</span> <code>{result}</code></li>'
        )
    if not rows:
        return ""
    return (
        '<details style="margin-top:8px;font-size:.82em">'
        f'<summary style="cursor:pointer;color:#174ea6">Tool Calling · {len(rows)}개</summary>'
        f'<ul style="margin:6px 0 0;padding-left:18px">{"".join(rows)}</ul></details>'
    )


def _agent_dashboard(
    agent_states: dict[str, dict[str, Any]],
    show_tool_calling: bool = False,
    collapsed: bool = False,
) -> str:
    """Render every Work agent at once; each stream event refreshes its own card."""
    if not agent_states:
        return ""
    completed = sum(state.get("status") == "completed" for state in agent_states.values())
    cards: list[str] = []
    for agent in (agent for agent in FOOD_AGENT_DEFINITIONS if agent.id in agent_states):
        state = agent_states.get(agent.id, {"status": "queued"})
        status = state.get("status", "queued")
        if status == "completed":
            badge = "✓ 완료"
            body = _AGENT_MARKDOWN(state.get("answer", ""))
            tool_calls = state.get("tool_calls", [])
            if tool_calls:
                tool_names = ", ".join(html.escape(str(call["name"])) for call in tool_calls)
                body += f'<div style="margin-top:8px;color:#5f6368;font-size:.82em">Tool Calling: {tool_names}</div>'
                if show_tool_calling:
                    body += _tool_calling_details(agent.id, tool_calls)
        elif status == "running":
            badge = "◌ 실행 중"
            partial_answer = state.get("answer", "")
            body = (
                _AGENT_MARKDOWN(partial_answer)
                if partial_answer
                else '<span class="agent-card__waiting">AI Core LLM 응답을 생성하고 있습니다…</span>'
            )
        else:
            badge = "대기"
            body = '<span class="agent-card__waiting">선행 Agent 결과 또는 실행 순서를 기다리고 있습니다.</span>'
        cards.append(
            f'''<article class="agent-card">
              <div class="agent-card__header"><span class="agent-card__name">{html.escape(agent.label)}</span><span class="agent-card__badge agent-card__badge--{status}">{badge}</span></div>
              <div class="agent-card__body">{body}</div>
            </article>'''
        )
    dashboard = f'''<section class="agent-dashboard">
      <div class="agent-dashboard__header"><span class="agent-dashboard__title">Specialist Agents · {completed}/{len(agent_states)} 완료</span><span class="agent-dashboard__caption">각 Agent 응답은 완료되는 즉시 해당 카드에 표시됩니다.</span></div>
      <div class="agent-dashboard__grid">{''.join(cards)}</div>
    </section>'''
    if collapsed:
        return f'<details class="workflow-collapsible"><summary>Specialist Agents · {completed}/{len(agent_states)} 완료</summary><div class="workflow-collapsible__content">{dashboard}</div></details>'
    return dashboard


def _final_answer_bubble(outcome: dict[str, Any]) -> str:
    final_agent_id = str(outcome.get("final_agent_id", "선택된 Specialist Agent"))
    final_label = next((agent.label for agent in FOOD_AGENT_DEFINITIONS if agent.id == final_agent_id), final_agent_id)
    answer = _AGENT_MARKDOWN(str(outcome["result"]))
    return f'<section class="workflow-final-answer"><div class="workflow-final-answer__title">최종 답변 · {html.escape(final_label)}</div>{answer}</section>'


def _research_card(tasks: list[dict[str, str]], findings: list[dict[str, str]]) -> gr.HTML:
    """Render completed parallel research notes without exposing workflow internals."""
    completed = {finding["id"]: finding for finding in findings}
    rows: list[str] = []
    for task in tasks:
        finding = completed.get(task["id"])
        if finding:
            text = html.escape(finding["content"]).replace("\n", "<br>")
            body = f'<span style="color:#374151">{text}</span>'
            marker = "✓"
            color = "#137333"
        else:
            body = '<span style="color:#6b7280">조사 중…</span>'
            marker = "◌"
            color = "#174ea6"
        rows.append(
            f'''<div style="padding:6px 0;border-top:1px solid #e5e7eb"><span style="color:{color};font-weight:700">{marker}</span> <b>{html.escape(task["title"])}</b><div style="padding:3px 0 0 18px;font-size:.88em;line-height:1.45">{body}</div></div>'''
        )
    return gr.HTML(
        f'''<div style="margin:6px 0;padding:8px 10px;border:1px solid #c7d2e1;border-radius:8px;background:#fff"><div style="font-size:.88em;font-weight:700;color:#174ea6;margin-bottom:4px">🔬 병렬 리서처 {len(findings)}/{len(tasks)}</div>{''.join(rows)}</div>''',
        container=False,
    )


def _research_planning_card(error: str | None = None) -> gr.HTML:
    if error:
        content = f'<span style="color:#b3261e">연구 역할 계획을 만들지 못했습니다: {html.escape(error)}</span>'
    else:
        content = '<span style="color:#174ea6">🧭 요청에 맞는 병렬 리서처 역할을 계획 중…</span>'
    return gr.HTML(
        f'<div style="margin:6px 0;padding:8px 10px;border:1px solid #c7d2e1;border-radius:8px;background:#fff;font-size:.88em">{content}</div>',
        container=False,
    )


def _plan_researchers(
    request: str, settings: Settings
) -> tuple[list[dict[str, str]], str | None]:
    """Ask the model to design 3–4 independent research roles for this request."""
    messages = [
        {
            "role": "system",
            "content": (
                "너는 리서치 팀 리드다. 사용자 요청에 필요한 독립적인 병렬 리서처 3~4명을 설계한다. "
                "각 역할의 관점이 겹치지 않게 한다. JSON만 반환한다: "
                '{"researchers":[{"id":"unique-id","title":"짧은 역할명","focus":"조사 범위"}]}. '
                "id는 영문 소문자·하이픈으로 고유하게, title과 focus는 한국어로 작성한다."
            ),
        },
        {"role": "user", "content": request},
    ]
    try:
        raw = chat_text(settings, messages).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        planned = json.loads(raw).get("researchers", [])
        if not isinstance(planned, list) or not 3 <= len(planned) <= 4:
            raise ValueError("리서처 수가 3~4개가 아닙니다")
        tasks = [
            {key: str(item[key]).strip() for key in ("id", "title", "focus")}
            for item in planned
            if isinstance(item, dict) and all(str(item.get(key, "")).strip() for key in ("id", "title", "focus"))
        ]
        if len(tasks) != len(planned) or len({task["id"] for task in tasks}) != len(tasks):
            raise ValueError("리서처 역할 형식 또는 id가 유효하지 않습니다")
        return tasks, None
    except Exception as error:
        return [], type(error).__name__


def _run_researcher(
    task: dict[str, str], request: str, settings: Settings
) -> dict[str, str]:
    """Run one independent research lens; callers execute these concurrently."""
    messages = [
        {
            "role": "system",
            "content": (
                "너는 병렬 리서처 중 한 명이다. 지정된 관점만 조사해 한국어로 2~3개 짧은 bullet을 작성한다. "
                "웹 검색이나 최신 수치를 확인한 것처럼 말하지 말고, 확실하지 않은 최신 정보는 확인 필요라고 표시한다. "
                "출처·수치·사실을 지어내지 않는다."
            ),
        },
        {
            "role": "user",
            "content": f"비교 요청: {request}\n조사 관점: {task['title']} ({task['focus']})",
        },
    ]
    try:
        content = chat_text(settings, messages)
    except Exception as error:
        content = f"조사 응답을 받지 못했습니다 ({type(error).__name__})."
    return {"id": task["id"], "title": task["title"], "content": content}


def _final_reply(
    message: str,
    outcome: dict[str, Any],
    history: list[dict[str, Any]],
    settings: Settings,
    research_findings: list[dict[str, str]] | None = None,
) -> str:
    messages = [
        {
            "role": "system",
            "content": "너는 workflow 실습의 교육 보조자다. 사용자 요청에 직접 한국어로 간결히 답한다. 실행 trace, 점수, fallback, route, specialist는 내부 UI 정보이므로 사용자가 명시적으로 묻지 않으면 절대 언급하거나 나열하지 않는다. 실제 외부 작업이 실행됐다고 꾸며내지 않는다.",
        },
        *[item for item in history[-6:] if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str)],
        {
            "role": "user",
            "content": (
                f"사용자 요청: {message}\n\n참고용 workflow 결과: {json.dumps(outcome, ensure_ascii=False)}"
                f"\n\n병렬 조사 메모: {json.dumps(research_findings or [], ensure_ascii=False)}"
                "\n\n위 내부 실행을 설명하지 말고, 조사 메모가 있다면 이를 종합해 사용자 요청에 대한 답변만 작성해줘."
            ),
        },
    ]
    try:
        return chat_text(settings, messages)
    except Exception as error:
        raise RuntimeError("LLM 응답 생성에 실패했습니다. 모델 배포 상태와 AI Core 권한을 확인하세요.") from error


def build_workflow_ui(
    settings: Settings | None = None,
    *,
    title: str = "LLM-Orchestrated Agent Workflow Chat",
    show_tool_calling: bool = False,
    default_request: str = DEFAULT_WORKFLOW_REQUEST,
) -> gr.Blocks:
    """Build the UI; Cohere routes and the Orchestrator selects Work Agents."""
    settings = settings or load_settings()
    settings.require_ai_core()
    debug_source = f"{title} UI"

    def workflow_chat(
        message: str,
        display_history: list[dict[str, Any]],
        conversation_history: list[dict[str, Any]],
        marketing_html_draft: str | None,
        min_margin: float,
    ):
        display_history = list(display_history or [])
        history = _plain_conversation_history(conversation_history)
        active_marketing_html = marketing_html_draft if isinstance(marketing_html_draft, str) else None
        if not message or not message.strip():
            yield "", display_history + [{"role": "assistant", "content": "<div style='color:#b3261e'>요청을 입력하세요.</div>"}], history, active_marketing_html
            return
        pending_display_history = display_history + [{"role": "user", "content": message}]
        pending_history = history + [{"role": "user", "content": message}]
        workflow_request_with_context = build_contextual_request(message, history, active_marketing_html)
        write_latest_workflow_debug_log({
            "status": "running",
            "source": debug_source,
            "user_message": message,
            "conversation_context": history,
            "workflow_request_with_context": workflow_request_with_context,
            "min_margin": float(min_margin),
        })
        yield "", pending_display_history + [{"role": "assistant", "content": _status_timeline([], running=True, show_tool_calling=show_tool_calling)}], pending_history, active_marketing_html
        trace: list[dict[str, Any]] = []
        agent_states: dict[str, dict[str, str]] = {}
        outcome: dict[str, Any] | None = None
        try:
            for event in run_workflow_stream(
                message,
                settings=settings,
                min_margin=float(min_margin),
                conversation_history=history,
                marketing_html_draft=active_marketing_html,
            ):
                if "trace_event" in event:
                    trace.append(event["trace_event"])
                if event["type"] == "route" and event["trace_event"]["payload"]["selected"] == "work":
                    agent_states = {"work-planning": {"status": "queued"}}
                if event["type"] == "orchestration_plan":
                    for stage in event["plan"]["stages"]:
                        for agent_id in stage["agent_ids"]:
                            agent_states.setdefault(agent_id, {"status": "queued"})
                if event["type"] == "agent_started":
                    agent_states[event["trace_event"]["payload"]["agent_id"]] = {"status": "running"}
                if event["type"] == "agent_delta":
                    agent_id = event["agent_id"]
                    agent_states.setdefault(agent_id, {"status": "running", "answer": ""})
                    agent_states[agent_id]["answer"] = agent_states[agent_id].get("answer", "") + event["delta"]
                if event["type"] == "agent_completed":
                    result = event["agent_result"]
                    agent_states[result["agent_id"]] = {"status": "completed", "answer": result["answer"], "tool_calls": result.get("tool_calls", [])}
                    if _html_tool_draft_created(result.get("tool_calls", [])):
                        created_draft = latest_marketing_html_draft()
                        if created_draft and isinstance(created_draft.get("html"), str):
                            active_marketing_html = created_draft["html"]
                if event["type"] == "complete":
                    outcome = event["result"]
                if event["type"] != "complete":
                    conversation = pending_display_history + [
                        {"role": "assistant", "content": _status_timeline(trace, running=True, show_tool_calling=show_tool_calling)},
                    ]
                    if agent_states:
                        conversation.append({"role": "assistant", "content": _agent_dashboard(agent_states, show_tool_calling=show_tool_calling)})
                    yield "", conversation, pending_history, active_marketing_html
        except Exception as error:
            conversation = pending_display_history + [
                {"role": "assistant", "content": _status_timeline(trace, show_tool_calling=show_tool_calling)},
                {"role": "assistant", "content": f'<div style="color:#b3261e">{html.escape(str(error))}</div>'},
            ]
            if agent_states:
                conversation.append({"role": "assistant", "content": _agent_dashboard(agent_states, show_tool_calling=show_tool_calling)})
            write_latest_workflow_debug_log({
                "status": "workflow_error",
                "source": debug_source,
                "user_message": message,
                "conversation_context": history,
                "workflow_request_with_context": workflow_request_with_context,
                "trace": trace,
                "agent_states": agent_states,
                "error": {"type": type(error).__name__, "message": str(error)},
            })
            yield "", conversation, pending_history, active_marketing_html
            return
        if outcome is None:
            return
        if outcome["route"] == "chat":
            try:
                answer = _final_reply(message, outcome, history, settings)
            except RuntimeError as error:
                write_latest_workflow_debug_log({
                    "status": "final_response_error",
                    "source": debug_source,
                    "user_message": message,
                    "conversation_context": history,
                    "workflow_request_with_context": workflow_request_with_context,
                    "trace": trace,
                    "workflow_outcome": outcome,
                    "error": {"type": type(error).__name__, "message": str(error)},
                })
                yield "", pending_display_history + [
                    {"role": "assistant", "content": _status_timeline(trace, show_tool_calling=show_tool_calling)},
                    {"role": "assistant", "content": f'<div style="color:#b3261e">{html.escape(str(error))}</div>'},
                ], pending_history, active_marketing_html
                return
            next_history = pending_history + [{"role": "assistant", "content": answer}]
            write_latest_workflow_debug_log({
                "status": "completed",
                "source": debug_source,
                "user_message": message,
                "conversation_context": history,
                "workflow_request_with_context": workflow_request_with_context,
                "trace": trace,
                "workflow_outcome": outcome,
                "final_response": answer,
            })
            yield "", pending_display_history + [
                {"role": "assistant", "content": _status_timeline(trace, show_tool_calling=show_tool_calling)},
                {"role": "assistant", "content": answer},
            ], next_history, active_marketing_html
            return
        answer = str(outcome.get("result", ""))
        next_history = pending_history + [{"role": "assistant", "content": answer}]
        write_latest_workflow_debug_log({
            "status": "completed",
            "source": debug_source,
            "user_message": message,
            "conversation_context": history,
            "workflow_request_with_context": workflow_request_with_context,
            "trace": trace,
            "agent_states": agent_states,
            "workflow_outcome": outcome,
            "final_response": answer,
        })
        yield "", pending_display_history + [
            {"role": "assistant", "content": _status_timeline(trace, show_tool_calling=show_tool_calling, collapsed=True)},
            {"role": "assistant", "content": _agent_dashboard(agent_states, show_tool_calling=show_tool_calling, collapsed=True)},
            {"role": "assistant", "content": _final_answer_bubble(outcome)},
        ], next_history, active_marketing_html

    with gr.Blocks(css=SETTINGS_MODAL_CSS) as app:
        with gr.Row(equal_height=True):
            with gr.Column(scale=8):
                gr.Markdown(f"## {title}")
            with gr.Column(scale=1, min_width=135):
                open_agent_tools = gr.Button("🧩 Agent · MCP Tools", size="sm")
            with gr.Column(scale=1, min_width=90):
                open_settings = gr.Button("⚙️ 설정", size="sm")
        gr.HTML(WORKFLOW_GRAPH_SVG, label="Workflow graph")
        with gr.Column(elem_id="workflow-chat-shell"):
            conversation_state = gr.State([])
            marketing_html_state = gr.State(None)
            chatbot = gr.Chatbot(
                type="messages",
                label="Workflow conversation",
                elem_id="workflow-conversation",
                height=800,
            )
            message = gr.Textbox(
                show_label=False,
                elem_id="workflow-composer",
                value=default_request,
                placeholder="메시지를 입력하고 Enter를 누르세요.",
            )
        with gr.Column(visible=False, elem_id="workflow-settings-modal") as settings_modal:
            gr.Markdown("### Routing 설정")
            min_margin = gr.Slider(
                minimum=0,
                maximum=1,
                value=0.0,
                step=0.01,
                label="최소 margin",
                info="1·2위 score 차이가 이 값보다 작으면 상태 카드에 낮은 신뢰도로 표시합니다. 선택된 route는 바꾸지 않습니다.",
            )
            close_settings = gr.Button("닫기")
        with gr.Column(visible=False, elem_id="agent-tool-modal") as agent_tool_modal:
            with gr.Row(equal_height=True):
                with gr.Column(scale=2, min_width=210):
                    gr.Markdown("### Agents")
                    agent_tool_buttons = {
                        agent.id: gr.Button(agent.label, size="sm")
                        for agent in FOOD_AGENT_DEFINITIONS
                    }
                with gr.Column(scale=5):
                    gr.Markdown("### Agent · MCP Tools")
                    agent_tool_detail = gr.HTML(
                        _agent_tool_catalog_panel(FOOD_AGENT_DEFINITIONS[0].id),
                        container=False,
                    )
            close_agent_tools = gr.Button("닫기")
        open_settings.click(lambda: gr.update(visible=True), outputs=settings_modal)
        close_settings.click(lambda: gr.update(visible=False), outputs=settings_modal)
        open_agent_tools.click(lambda: gr.update(visible=True), outputs=agent_tool_modal)
        close_agent_tools.click(lambda: gr.update(visible=False), outputs=agent_tool_modal)
        for agent in FOOD_AGENT_DEFINITIONS:
            agent_tool_buttons[agent.id].click(
                lambda agent_id=agent.id: _agent_tool_catalog_panel(agent_id),
                outputs=agent_tool_detail,
            )
        chat_inputs = [message, chatbot, conversation_state, marketing_html_state, min_margin]
        message.submit(workflow_chat, inputs=chat_inputs, outputs=[message, chatbot, conversation_state, marketing_html_state])
    return app


def launch_workflow_ui() -> gr.Blocks:
    """Build and launch the notebook-local workflow UI."""
    app = build_workflow_ui()
    app.launch(inline=True, share=False, show_error=True, server_name="127.0.0.1", height=900)
    return app
