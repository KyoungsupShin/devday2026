"""Gradio presentation adapter for the 01 agent workflow lab."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gradio as gr
import mistune
from .lesson_support.config import Settings, load_settings

from .food_agents import FOOD_AGENT_DEFINITIONS
from .lab_core import run_workflow_stream


# Pair every Gradio dark token with its light equivalent, including chat bubbles.
_BASE_THEME = gr.themes.Base(primary_hue=gr.themes.colors.blue)
_THEME_VALUES = _BASE_THEME.to_dict()["theme"]
LIGHT_THEME = _BASE_THEME.set(**{
    f"{name}_dark": value
    for name, value in _THEME_VALUES.items()
    if not name.endswith("_dark") and f"{name}_dark" in _THEME_VALUES
})

DEFAULT_WORKFLOW_REQUEST = (
    "편의점용 고단백 닭가슴살 도시락을 출시하려고 합니다. 판매가 4,500원, 단백질 30g 이상, "
    "전자레인지 조리 가능 조건으로 콘셉트·레시피·원가·공급망·식품안전·마케팅·손익분기점을 "
    "종합 검토해 출시 권고안을 작성해주세요. 모든 수치에는 가정을 표시해주세요."
)

WORKFLOW_SCENARIOS = (
    {
        "title": "신제품 출시 Go / No-Go",
        "focus": "R&D · 구매 · QA · 마케팅 · 재무 · Synthesis",
        "request": "수도권 편의점 1,200개 점포에 320g 고단백 닭가슴살 도시락을 12주간 출시하려 합니다. 조건은 판매가 4,500원, 단백질 30g 이상, 나트륨 1,200mg 이하, 냉장 0~5°C·소비기한 21일, 목표 제조원가 2,500원 이하입니다. R&D 레시피·공정, 구매 원가·공급 안정성, QA 안전·표시, 마케팅 타깃·메시지, 재무 손익분기점을 검토하고, 핵심 가정·3대 위험·Go / No-Go 결론을 포함한 출시 권고안을 작성해줘.",
        "history": [],
    },
    {
        "title": "4,900원 가격 설계",
        "focus": "R&D · 구매 · QA · 마케팅 · 재무 · Synthesis",
        "request": "20~30대 직장인용 저당 고단백 도시락의 가격안을 결정해야 합니다. 330g, 단백질 32g 이상, 당류 8g 이하, 4주 냉장 유통을 전제로 4,900원과 5,500원 중 하나를 선택해줘. 목표 공헌이익률은 35% 이상이며, 점포당 하루 8개 판매를 가정합니다. R&D 레시피·포장, 구매 단가·대체 원료, QA 표시·보관 제약, 마케팅 고객가치·경쟁 포인트, 재무 원가·손익분기점을 비교해 SKU·권장 판매가·실행 조건을 표 형식으로 종합해줘.",
        "history": [],
    },
    {
        "title": "냉장 유통 리스크 대응",
        "focus": "R&D · 구매 · QA · 마케팅 · 재무 · Synthesis",
        "request": "수도권 물류센터 2곳에서 편의점 800개 점포로 냉장 도시락을 공급합니다. 여름철 배송 중 5°C 초과가 최대 2시간 발생할 수 있고, 폐기율은 3% 이하로 유지해야 하며 소비기한은 21일입니다. R&D의 공정·포장 보완, 구매의 콜드체인·대체 공급처, QA의 미생물·온도 이탈 관리, 마케팅의 고객 안내, 재무의 폐기·물류비 영향을 검토해줘. 출시 연기·조건부 출시·즉시 출시 중 하나를 고르고 30·60·90일 조치계획을 제시해줘.",
        "history": [],
    },
    {
        "title": "원재료 인상 후 재출시",
        "focus": "Observer · R&D · 구매 · QA · 마케팅 · 재무 · Synthesis",
        "request": "기존 프로틴 런치의 닭가슴살 원가가 15% 올랐고, 현재 판매가 4,500원·단백질 30g·320g 구성·목표 공헌이익률 30%는 유지해야 합니다. 레시피를 바꾸면 단백질과 표시 기준을 유지해야 하며, 가격 인상은 최대 300원까지만 허용됩니다. R&D의 배합 대안, 구매의 대체 공급처·MOQ, QA의 알레르겐·표시 영향, 마케팅의 가격 인상 메시지, 재무의 이익 회복 효과를 비교해 재출시안 2개와 최종 권고안을 제시해줘.",
        "history": [
            {"role": "user", "content": "프로틴 런치는 단백질 30g, 판매가 4,500원인 편의점용 냉장 도시락으로 기획했어."},
            {"role": "assistant", "content": "프로틴 런치의 제품 콘셉트와 출시 메시지 초안을 만들었습니다."},
        ],
    },
    {
        "title": "알레르겐 리뉴얼 의사결정",
        "focus": "R&D · 구매 · QA · 마케팅 · 재무 · Synthesis",
        "request": "기존 도시락의 땅콩 함유 소스로 인해 학교·오피스 채널 입점이 거절되었습니다. 판매가 4,900원과 단백질 30g은 유지해야 하고, 리뉴얼 후 목표 제조원가는 2,600원 이하입니다. R&D는 땅콩 없는 대체 소스 2안을, 구매는 원료 수급·최소주문수량을, QA는 교차오염·표시·검증 항목을, 마케팅은 채널별 메시지를, 재무는 전환 비용·추가 매출을 평가해줘. 즉시 리뉴얼·파일럿 후 리뉴얼·유지 중 하나를 선택하고 단계별 의사결정 기준을 제시해줘.",
        "history": [],
    },
    {
        "title": "여름 한정 샐러드 출시",
        "focus": "R&D · 구매 · QA · 마케팅 · 재무 · Synthesis",
        "request": "6~7월 6주 동안 편의점 600개 점포에서 250g 고단백 닭가슴살 샐러드를 한정 출시합니다. 판매가 5,900원, 단백질 25g 이상, 목표 판매량은 점포당 하루 5개, 폐기율 한도는 5%, 냉장 소비기한은 5일입니다. R&D는 제품·소스·공정, 구매는 채소 계절성·대체 조달, QA는 세척·미생물·냉장 관리, 마케팅은 타깃·채널·프로모션, 재무는 원가·판매목표·손익을 제안해줘. 성공 KPI와 조기 종료 기준까지 포함한 한정 출시 실행안을 종합해줘.",
        "history": [],
    },
)

DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "debug" / "latest_workflow_conversation.json"


def write_latest_workflow_debug_log(snapshot: dict[str, Any], path: Path = DEBUG_LOG_PATH) -> Path:
    """Atomically replace the latest UI conversation snapshot for local debugging.

    The snapshot deliberately contains prompts, responses, trace and Agent metadata,
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


def _scenario_card_html(scenario: dict[str, Any]) -> str:
    """Render one selectable educational scenario without embedding button logic."""
    return (
        '<article class="workflow-scenario-card__body">'
        f'<p class="workflow-scenario-card__focus">{html.escape(str(scenario["focus"]))}</p>'
        f'<h4>{html.escape(str(scenario["title"]))}</h4>'
        '<section class="workflow-scenario-card__request">'
        '<span>사용자 요청</span>'
        f'<p>{html.escape(str(scenario["request"]))}</p>'
        '</section>'
        '</article>'
    )

WORKFLOW_GRAPH_SVG = """
<svg viewBox="0 0 1420 410" width="86%" style="display:block;margin:0 auto" role="img" aria-label="LLM-orchestrated agent workflow with final synthesis" xmlns="http://www.w3.org/2000/svg">
  <style>.node{fill:#fff;stroke:#8ab4f8;stroke-width:2}.work{fill:#f8fbff;stroke:#4285f4;stroke-width:2}.end{fill:#e6f4ea;stroke:#34a853;stroke-width:2}.label{font:600 15px sans-serif;fill:#202124}.small{font:13px sans-serif;fill:#5f6368}.edge{fill:none;stroke:#5f6368;stroke-width:2;marker-end:url(#arrow)}</style>
  <defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#5f6368"/></marker></defs>
  <text x="26" y="31" class="label" style="font-size:18px">LLM-Orchestrated Food Workflow</text>
  <rect x="25" y="170" width="150" height="64" rx="12" class="node"/><text x="100" y="198" text-anchor="middle" class="label">User request</text><text x="100" y="218" text-anchor="middle" class="small">message</text>
  <rect x="240" y="155" width="180" height="94" rx="12" class="work"/><text x="330" y="190" text-anchor="middle" class="label">Cohere Rerank</text><text x="330" y="213" text-anchor="middle" class="small">Chat / Work</text>
  <rect x="500" y="57" width="175" height="64" rx="12" class="end"/><text x="587" y="85" text-anchor="middle" class="label">Chat response</text><text x="587" y="105" text-anchor="middle" class="small">direct response</text>
  <rect x="500" y="270" width="175" height="76" rx="12" class="work"/><text x="587" y="300" text-anchor="middle" class="label">Work Planning Agents</text><text x="587" y="323" text-anchor="middle" class="small">LLM orchestrator</text>
  <rect x="755" y="250" width="210" height="115" rx="12" class="node"/><text x="860" y="280" text-anchor="middle" class="label">Selected Agents</text><text x="860" y="305" text-anchor="middle" class="small">LLM-selected plan</text><text x="860" y="327" text-anchor="middle" class="small">ordered stages</text>
  <rect x="1020" y="270" width="190" height="76" rx="12" class="work"/><text x="1115" y="300" text-anchor="middle" class="label">Final Agent</text><text x="1115" y="323" text-anchor="middle" class="small">chosen by plan</text>
  <rect x="1265" y="270" width="130" height="76" rx="12" class="end"/><text x="1330" y="300" text-anchor="middle" class="label">Result</text><text x="1330" y="323" text-anchor="middle" class="small">final output</text>
  <path d="M175 202 H240" class="edge"/><path d="M420 177 C450 177 450 89 500 89" class="edge"/><text x="444" y="118" class="small">chat</text><path d="M420 225 C450 225 450 308 500 308" class="edge"/><text x="440" y="271" class="small">work</text><path d="M675 308 H755" class="edge"/><path d="M965 308 H1020" class="edge"/><path d="M1210 308 H1265" class="edge"/>
</svg>
"""

SETTINGS_MODAL_CSS = """
#workflow-settings-modal {
  position: fixed !important; inset: 16vh 24vw auto !important; z-index: 1000 !important;
  max-width: 620px !important; padding: 20px !important; border: 1px solid #d0d7de !important;
  border-radius: 14px !important; background: white !important;
  box-shadow: 0 18px 60px rgba(0,0,0,.22) !important;
}


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

SETTINGS_MODAL_CSS += """
#workflow-scenario-card-grid { display:grid !important; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px !important; align-items:stretch; }
#workflow-scenario-card-grid > .gr-column { min-width:0 !important; flex:initial !important; }
.workflow-scenario-card { gap:0 !important; min-width:0 !important; border:1px solid #c9d9e7; border-radius:12px; background:#fff; box-shadow:0 1px 2px rgba(40,58,74,.08); overflow:hidden; }
.workflow-scenario-card__body { min-height:174px; padding:15px 15px 11px; background:linear-gradient(145deg,#f9fcff,#eef5fb); color:#25313d; }
.workflow-scenario-card__focus { margin:0 0 6px; color:#5b7b99; font-size:10px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
.workflow-scenario-card__body h4 { margin:0 0 12px; color:#274761; font-size:15px; line-height:1.35; }
.workflow-scenario-card__request { padding:10px; border:1px solid #e1e9f0; border-radius:8px; background:rgba(255,255,255,.8); }
.workflow-scenario-card__request span { color:#71869b; font-size:10px; font-weight:800; letter-spacing:.04em; }
.workflow-scenario-card__request p { margin:5px 0 0; color:#425d73; font-size:12px; line-height:1.55; word-break:keep-all; }
.workflow-scenario-card button { width:calc(100% - 24px) !important; min-height:34px; margin:0 12px 12px !important; border:1px solid #769bbc !important; border-radius:8px !important; background:#fff !important; color:#315a7b !important; font-size:12px !important; font-weight:800 !important; }
.workflow-scenario-card button:hover { border-color:#3f78a5 !important; background:#edf6ff !important; color:#1d4f78 !important; }
@media(max-width:900px) { #workflow-scenario-card-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(max-width:700px) { #workflow-scenario-card-grid { grid-template-columns:1fr; } .workflow-scenario-card__body { min-height:0; } }
"""

_AGENT_MARKDOWN = mistune.create_markdown(escape=True, plugins=["table", "strikethrough"])


def _status_timeline(
    trace: list[dict[str, Any]],
    running: bool = False,
    collapsed: bool = False,
) -> gr.HTML:
    """Render one evolving timeline row per Agent, rather than start/completion pairs."""
    items: list[dict[str, str]] = []
    agent_item_index: dict[str, int] = {}
    for event in trace:
        event_name = event["event"]
        data = event.get("payload", event.get("data", {}))
        if event_name == "fast_route":
            detail = html.escape(str(data.get("selected", "")))
            if data.get("engine"):
                detail += f' <span style="color:#6b7280">· {html.escape(str(data["engine"]))}</span>'
            if data.get("low_confidence"):
                detail += ' <span style="color:#b45309">· 낮은 신뢰도</span>'
            items.append({"icon": "①", "title": "Cohere Rerank", "detail": detail})
            continue
        if event_name == "orchestration_plan":
            final_agent_id = html.escape(str(data.get("final_agent_id", "")))
            items.append({"icon": "②", "title": "실행 계획", "detail": f"최종 Agent · {final_agent_id}"})
            continue
        if event_name == "agent_started":
            agent_id = str(data["agent_id"])
            agent_item_index[agent_id] = len(items)
            items.append({
                "icon": "③",
                "title": "Agent 실행",
                "detail": f'{html.escape(str(data["label"]))} <span style="color:#b45309">· 실행 중</span>',
            })
            continue
        if event_name == "agent_completed":
            agent_id = str(data["agent_id"])
            completed_item = {
                "icon": "④",
                "title": "Agent 완료",
                "detail": f'{html.escape(str(data["label"]))} <span style="color:#137333">· 완료</span>',
            }
            if agent_id in agent_item_index:
                items[agent_item_index[agent_id]] = completed_item
            else:
                agent_item_index[agent_id] = len(items)
                items.append(completed_item)
            continue
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


def _agent_dashboard(
    agent_states: dict[str, dict[str, Any]],
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


def build_workflow_ui(
    settings: Settings | None = None,
    *,
    title: str = "LLM-Orchestrated Agent Workflow Chat",
    default_request: str = DEFAULT_WORKFLOW_REQUEST,
    scenarios: tuple[dict[str, Any], ...] | None = None,
) -> gr.Blocks:
    """Build the UI for the LLM-authored Agent workflow."""
    settings = settings or load_settings()
    settings.require_ai_core()
    debug_source = f"{title} UI"
    active_scenarios = WORKFLOW_SCENARIOS if scenarios is None else scenarios

    def workflow_chat(
        message: str,
        display_history: list[dict[str, Any]],
        conversation_history: list[dict[str, Any]],
        min_margin: float,
    ):
        display_history = list(display_history or [])
        history = _plain_conversation_history(conversation_history)
        if not message or not message.strip():
            yield "", display_history + [{"role": "assistant", "content": "<div style='color:#b3261e'>요청을 입력하세요.</div>"}], history
            return
        pending_display_history = display_history + [{"role": "user", "content": message}]
        pending_history = history + [{"role": "user", "content": message}]
        write_latest_workflow_debug_log({
            "status": "running",
            "source": debug_source,
            "user_message": message,
            "conversation_context": history,
            "min_margin": float(min_margin),
        })
        yield "", pending_display_history + [{"role": "assistant", "content": _status_timeline([], running=True)}], pending_history
        trace: list[dict[str, Any]] = []
        agent_states: dict[str, dict[str, str]] = {}
        outcome: dict[str, Any] | None = None
        try:
            for event in run_workflow_stream(
                message,
                settings=settings,
                min_margin=float(min_margin),
                conversation_history=history,
            ):
                if "trace_event" in event:
                    trace.append(event["trace_event"])
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
                    agent_states[result["agent_id"]] = {"status": "completed", "answer": result["answer"]}
                if event["type"] == "complete":
                    outcome = event["result"]
                if event["type"] != "complete":
                    conversation = pending_display_history + [
                        {"role": "assistant", "content": _status_timeline(trace, running=True)},
                    ]
                    if agent_states:
                        conversation.append({"role": "assistant", "content": _agent_dashboard(agent_states)})
                    yield "", conversation, pending_history
        except Exception as error:
            conversation = pending_display_history + [
                {"role": "assistant", "content": _status_timeline(trace)},
                {"role": "assistant", "content": f'<div style="color:#b3261e">{html.escape(str(error))}</div>'},
            ]
            if agent_states:
                conversation.append({"role": "assistant", "content": _agent_dashboard(agent_states)})
            write_latest_workflow_debug_log({
                "status": "workflow_error",
                "source": debug_source,
                "user_message": message,
                "conversation_context": history,
                "trace": trace,
                "agent_states": agent_states,
                "error": {"type": type(error).__name__, "message": str(error)},
            })
            yield "", conversation, pending_history
            return
        if outcome is None:
            return
        answer = str(outcome.get("result", ""))
        next_history = pending_history + [{"role": "assistant", "content": answer}]
        write_latest_workflow_debug_log({
            "status": "completed",
            "source": debug_source,
            "user_message": message,
            "conversation_context": history,
            "trace": trace,
            "agent_states": agent_states,
            "workflow_outcome": outcome,
            "final_response": answer,
        })
        conversation = pending_display_history + [
            {"role": "assistant", "content": _status_timeline(trace, collapsed=True)},
        ]
        if agent_states:
            conversation.append({"role": "assistant", "content": _agent_dashboard(agent_states, collapsed=True)})
        if outcome.get("route") == "work":
            conversation.append({"role": "assistant", "content": _final_answer_bubble(outcome)})
        else:
            conversation.append({"role": "assistant", "content": _AGENT_MARKDOWN(answer)})
        yield "", conversation, next_history

    with gr.Blocks(css=SETTINGS_MODAL_CSS, theme=LIGHT_THEME) as app:
        with gr.Row(equal_height=True):
            with gr.Column(scale=8):
                gr.Markdown(f"## {title}")
            with gr.Column(scale=1, min_width=90):
                open_settings = gr.Button("⚙️ 설정", size="sm")
        gr.HTML(WORKFLOW_GRAPH_SVG, label="Workflow graph")
        with gr.Column(elem_id="workflow-chat-shell"):
            conversation_state = gr.State([])
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
                info="1·2위 score 차이가 이 값보다 작으면 Agent를 실행하지 않고, 요청을 구체화해 달라는 명확화 응답으로 종료합니다.",
            )
            close_settings = gr.Button("닫기")
        with (
            gr.Accordion("교육용 시나리오", open=True),
            gr.Row(
                elem_id="workflow-scenario-card-grid",
                elem_classes=["workflow-scenario-cards"],
            ),
        ):
            for scenario in active_scenarios:
                with gr.Column(elem_classes=["workflow-scenario-card"]):
                    gr.HTML(_scenario_card_html(scenario))
                    scenario_button = gr.Button("요청 선택", variant="secondary")
                scenario_button.click(
                    lambda request=scenario["request"], history=scenario["history"]: (
                        request,
                        list(history),
                        list(history),
                        0.0,
                    ),
                    outputs=[message, chatbot, conversation_state, min_margin],
                    queue=False,
                )
        open_settings.click(lambda: gr.update(visible=True), outputs=settings_modal)
        close_settings.click(lambda: gr.update(visible=False), outputs=settings_modal)
        chat_inputs = [message, chatbot, conversation_state, min_margin]
        message.submit(workflow_chat, inputs=chat_inputs, outputs=[message, chatbot, conversation_state])
    return app


def launch_workflow_ui() -> gr.Blocks:
    """Launch lesson 01."""
    app = build_workflow_ui()
    app.launch(inline=True, share=False, show_error=True, server_name="127.0.0.1", height=900)
    return app
