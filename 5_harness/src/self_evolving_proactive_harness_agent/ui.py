"""Timeline-first Gradio UI for the autonomous cognitive cycle lesson."""

from __future__ import annotations

import html
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any, Iterator

import gradio as gr

from .capabilities import discover_capabilities
from .models import CognitiveState
from .runtime import CognitiveCore


REACT_STEPS = (
    ("react_observation", "현황 파악"),
    ("react_thinking", "업무 판단"),
    ("react_action", "분석 조치"),
    ("react_evaluation", "효과 평가"),
)
TURN_STAGE_LABELS = {
    1: {
        "react_observation": "데이터 이해",
        "react_thinking": "분석 설계",
        "react_action": "읽기 전용 분석 실행",
        "react_evaluation": "분석 결과 해석",
    },
    2: {
        "react_observation": "분석 근거 재검토",
        "react_thinking": "가설 갱신 및 우선순위 판단",
        "react_action": "후속 검증 또는 대응 설계",
        "react_evaluation": "학습 반영 및 업무 지속 여부 판단",
    },
    3: {
        "react_observation": "가설과 검증 기준 확인",
        "react_thinking": "시뮬레이션 판단",
        "react_action": "가설 검증 시뮬레이션 실행",
        "react_evaluation": "가설 평가 및 선제 대응 결정",
    },
}

ACTION_LABELS = {
    "EXPLORE": "추가 현황 확인",
    "SIMULATE": "가설 검증 시뮬레이션",
    "CREATE_GOAL": "개선 목표 등록",
    "CREATE_TASK": "분석 과제 생성",
    "DELEGATE": "전문 분석 요청",
    "REFLECT": "분석 결과 재검토",
    "REVISE_GOAL": "개선 목표 조정",
    "WAIT": "이번 실행 종료",
    "REQUEST_APPROVAL": "담당자 승인 요청",
    "INVESTIGATE": "근거 추가 조사",
    "VALIDATE": "가설 검증",
    "COMPLETE": "목표 검토 완료",
}
TERMINAL_LABELS = {
    "WAIT": "이번 실행 종료",
    "REQUEST_APPROVAL": "담당자 승인 필요",
    "DECISION_BUDGET_REACHED": "이번 회차 분석 완료",
    "COMPLETE_REJECTED": "완료 근거 부족: 업무 유지",
    "FAILED": "분석 실행 실패",
    "PAUSED": "일시 중지 상태",
    "CANCELLED": "사용자가 실행 중단",
    "DUPLICATE_RUN": "이미 실행 중",
}


def build_proactive_harness_ui(core: CognitiveCore) -> gr.Blocks:
    """Build a demo UI whose main surface explains one autonomous cycle."""
    repository = core.repository
    active_cancel: Event | None = None
    active_lock = Lock()

    def snapshot() -> tuple[CognitiveState, list[dict[str, Any]]]:
        return repository.load_state("default"), discover_capabilities()

    def reset() -> tuple[str, str, str, str, dict[str, Any], dict[str, Any]]:
        state = CognitiveState(cognitive_id="default")
        repository.save_state(state)
        return (
            _overview(state, discover_capabilities()), _react_loop([], state), _portfolio(state), _next_action(state),
            state.model_dump(mode="json"), {},
        )

    def pause() -> tuple[str, str, str, dict[str, Any], dict[str, Any]]:
        state = core.pause("default")
        return _overview(state, discover_capabilities()), _react_loop([], state), _next_action(state), state.model_dump(mode="json"), {}

    def resume() -> tuple[str, str, str, dict[str, Any], dict[str, Any]]:
        state = core.resume("default")
        return _overview(state, discover_capabilities()), _react_loop([], state), _next_action(state), state.model_dump(mode="json"), {}

    def add_observation(message: str) -> tuple[str, str, dict[str, Any]]:
        state = repository.load_state("default")
        normalized = (message or "").strip()
        if normalized:
            state.remember_observation(normalized)
            repository.save_state(state)
        return "", _overview(state, discover_capabilities()), state.model_dump(mode="json")

    def cycle_updates() -> Iterator[tuple[str, str, str, str, dict[str, Any], dict[str, Any]]]:
        nonlocal active_cancel
        events: list[dict[str, Any]] = []
        queue: Queue[dict[str, Any]] = Queue()
        result: dict[str, Any] = {}
        cancel_event = Event()
        with active_lock:
            active_cancel = cancel_event

        def record(event: dict[str, Any]) -> None:
            queue.put(event)

        def execute() -> None:
            result["run"] = core.run_cycle("default", on_event=record, is_cancelled=cancel_event.is_set)

        worker = Thread(target=execute, daemon=True)
        worker.start()
        initial, inventory = snapshot()
        yield _overview(initial, inventory), _react_loop(events, initial), _portfolio(initial), _next_action(initial), initial.model_dump(mode="json"), {}
        while worker.is_alive() or not queue.empty():
            try:
                event = queue.get(timeout=0.2)
            except Empty:
                continue
            events.append(event)
            current, inventory = snapshot()
            yield (
                _overview(current, inventory), _react_loop(events, current), _portfolio(current),
                _next_action(current), current.model_dump(mode="json"),
                result.get("run").model_dump(mode="json") if result.get("run") else {"events": events},
            )
        worker.join()
        with active_lock:
            active_cancel = None
        state, inventory = snapshot()
        run = result["run"]
        yield (
            _overview(state, inventory), _react_loop(events, state), _portfolio(state), _next_action(state),
            state.model_dump(mode="json"), run.model_dump(mode="json"),
        )

    def cancel_cycle() -> None:
        with active_lock:
            if active_cancel is not None:
                active_cancel.set()

    initial_state, initial_inventory = snapshot()
    with gr.Blocks(css=_CSS) as interface:
        gr.HTML("<h2 class='cognitive-title'>자율 운영 분석</h2><p class='cognitive-subtitle'>사용자 메시지 없이 저장된 분석 이력과 등록 데이터를 바탕으로 다음 검토를 시작합니다.</p>")
        overview = gr.HTML(_overview(initial_state, initial_inventory))
        stepper = gr.HTML(_react_loop([], initial_state))
        with gr.Row():
            run = gr.Button("Proactive cycle 실행", variant="primary", scale=2)
            cancel_button = gr.Button("실행 중단", variant="stop", scale=1)
            pause_button = gr.Button("일시 중지", scale=1)
            resume_button = gr.Button("재개", scale=1)
            reset_button = gr.Button("새 데이터 기준으로 다시 시작", scale=1)
        insights = gr.HTML(_portfolio(initial_state))
        next_action = gr.HTML(_next_action(initial_state))
        # Retained as invisible callback targets; raw state is not part of the lesson UI.
        state_view = gr.JSON(value=initial_state.model_dump(mode="json"), visible=False)
        run_view = gr.JSON(value={}, visible=False)

        outputs = [overview, stepper, insights, next_action, state_view, run_view]
        run.click(cycle_updates, outputs=outputs)
        cancel_button.click(cancel_cycle)
        pause_button.click(pause, outputs=[overview, stepper, next_action, state_view, run_view])
        resume_button.click(resume, outputs=[overview, stepper, next_action, state_view, run_view])
        reset_button.click(reset, outputs=outputs)
    return interface


def _overview(state: CognitiveState, inventory: list[dict[str, Any]]) -> str:
    dataset_count = sum(item.get("kind") == "dataset" for item in inventory)
    wakeup = state.next_wakeup_at.isoformat(sep=" ", timespec="minutes") if state.next_wakeup_at else "Not scheduled"
    return "<div class='summary-grid'>" + "".join((
        _card("현재 상태", state.lifecycle_status.value, "state"),
        _card("등록 데이터셋", str(dataset_count), "data"),
        _card("실행 방식", "수동 또는 Worker 호출", "schedule"),
    )) + "</div>"


def _card(label: str, value: str, kind: str) -> str:
    return f"<div class='summary-card {kind}'><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>"


def _react_loop(events: list[dict[str, Any]], state: CognitiveState | None = None) -> str:
    if not events:
        return "<section class='react-timeline empty'><h3>실행 타임라인</h3><p>실행을 시작하면 데이터 관찰부터 판단, 분석 조치, 평가까지 실제 발생 순서대로 표시합니다.</p></section>"

    # Running and completed notifications for one step are emitted separately.
    # Keep its first position but show the newest version so the timeline remains readable.
    latest: dict[tuple[int, str], dict[str, Any]] = {}
    first_position: dict[tuple[int, str], int] = {}
    for position, event in enumerate(events):
        turn = int(event.get("data", {}).get("turn", 0) or 0)
        key = (turn, str(event.get("step", "")))
        latest[key] = event
        first_position.setdefault(key, position)
    ordered = sorted(latest.items(), key=lambda item: first_position[item[0]])
    items = [_timeline_item(key[0], event) for key, event in ordered]
    is_terminal = any(
        event.get("data", {}).get("terminal_reason")
        for event in events
        if isinstance(event.get("data"), dict)
    )
    conclusion = _timeline_conclusion(state, events) if state and is_terminal else ""
    return (
        "<section class='react-timeline'><h3>실행 타임라인</h3>"
        "<p class='timeline-intro'>데이터 이해 → 분석 설계 → 읽기 전용 분석 → 가설 갱신 → 다음 검증으로 발전하는 실제 실행 기록입니다.</p>"
        + "".join(items) + conclusion + "</section>"
    )


def _timeline_item(turn: int, event: dict[str, Any]) -> str:
    step = str(event.get("step", ""))
    status = str(event.get("status", "pending"))
    data = event.get("data", {})
    label = "실행 준비" if turn == 0 else TURN_STAGE_LABELS.get(turn, TURN_STAGE_LABELS[2]).get(step, step)
    if step == "react_action" and isinstance(data, dict) and data.get("action") == "SIMULATE":
        label = "가설 검증 시뮬레이션 실행"
    turn_label = "시작" if turn == 0 else f"{turn}차 판단"
    summary = str(event.get("summary", ""))
    decision = data.get("decision") if isinstance(data, dict) else None
    plan_html = ""
    if step == "react_thinking" and isinstance(decision, dict):
        action = ACTION_LABELS.get(str(decision.get("action", "")), str(decision.get("action", "")))
        summary = f"{action} · {decision.get('rationale', summary)}"
        plan = decision.get("analysis_plan", [])
        if isinstance(plan, list) and plan:
            plan_html = "<ol class='analysis-plan'>" + "".join(
                f"<li>{html.escape(str(item))}</li>" for item in plan
            ) + "</ol>"
    terminal = data.get("terminal_reason") if isinstance(data, dict) else None
    terminal_html = (
        f"<span class='timeline-terminal'>{html.escape(TERMINAL_LABELS.get(str(terminal), str(terminal)))}</span>"
        if terminal else ""
    )
    return (
        f"<article class='timeline-item {html.escape(status)}'>"
        "<div class='timeline-marker'></div><div class='timeline-content'>"
        f"<div class='timeline-meta'>{html.escape(turn_label)} · {html.escape(label)}"
        f"<span>{html.escape(status.upper())}</span>{terminal_html}</div>"
        f"<p>{html.escape(summary)}</p>{plan_html}</div></article>"
    )


def _timeline_conclusion(state: CognitiveState, events: list[dict[str, Any]]) -> str:
    """Keep the business conclusion in the same chronological surface as the run."""
    decision = next((
        event.get("data", {}).get("decision")
        for event in reversed(events)
        if event.get("step") == "react_thinking" and event.get("data", {}).get("decision")
    ), None)
    action = "이번 실행 종료"
    if isinstance(decision, dict):
        action = ACTION_LABELS.get(str(decision.get("action", "")), str(decision.get("action", action)))
    next_step = "자동 예약은 사용하지 않습니다. 필요할 때 Proactive cycle을 다시 실행하면 저장된 목표와 업무를 이어서 검토합니다."
    sections = (
        ("확인된 사실", state.recent_observations[-3:]),
        ("업무상 확인 과제", decision.get("discovered_problems", []) if isinstance(decision, dict) else []),
        ("검증할 가설", decision.get("hypotheses", []) if isinstance(decision, dict) else []),
    )
    details = "".join(
        f"<div><strong>{html.escape(title)}</strong>{_list(items or ["아직 기록된 내용이 없습니다."])}</div>"
        for title, items in sections
    )
    return (
        "<article class='timeline-item conclusion completed'><div class='timeline-marker'></div>"
        "<div class='timeline-content'><div class='timeline-meta'>이번 cycle 결론</div>"
        f"<div class='timeline-conclusion'>{details}"
        f"<div><strong>선택된 다음 행동</strong><p>{html.escape(action)}</p></div>"
        f"<div><strong>다음 실행</strong><p>{html.escape(next_step)}</p></div>"
        "</div></div></article>"
    )


def _insights(state: CognitiveState, events: list[dict[str, Any]]) -> str:
    decision = next((event.get("data", {}).get("decision") for event in reversed(events) if event["step"] == "react_thinking" and event.get("data", {}).get("decision")), None)
    observations = state.recent_observations[-4:] or ["완료된 분석 관찰이 아직 없습니다."]
    hypotheses = state.hypotheses[-3:] or ["기록된 가설이 아직 없습니다."]
    problems = state.discovered_problems[-3:] or ["정의된 문제가 아직 없습니다."]
    decision_html = "아직 결정이 반환되지 않았습니다."
    if decision:
        action = str(decision.get("action", ""))
        decision_html = f"<strong>{html.escape(ACTION_LABELS.get(action, action))}</strong> · {html.escape(str(decision.get('rationale', '')))}"
    return "".join((
        "<section class='insights'><h3>분석에서 확인된 사실</h3>" + _list(observations) + "</section>",
        "<section class='insights'><h3>업무상 확인 과제</h3>" + _list(problems) + "</section>",
        "<section class='insights'><h3>추가 확인이 필요한 가설</h3>" + _list(hypotheses) + "</section>",
        f"<section class='insights decision'><h3>이번 검토의 판단</h3><p>{decision_html}</p></section>",
    ))


def _empty_insights() -> str:
    return "<section class='insights'><h3>다음 검토에서 수행할 일</h3><p>데이터 현황을 확인하고, 업무상 확인 과제를 정리한 뒤, 필요한 분석 조치와 후속 검토 시점을 결정합니다.</p></section>"


def _portfolio(state: CognitiveState) -> str:
    """Small business-facing view of persistent work, separate from raw state."""
    active_goals = [goal for goal in state.goals if goal.status in {"PROPOSED", "ACTIVE", "PAUSED"}]
    open_tasks = [task for task in state.tasks if task.status not in {"COMPLETED", "CANCELLED"}]
    goal_text = [f"{goal.title} · {goal.status}" for goal in active_goals] or ["현재 진행 중인 개선 목표가 없습니다."]
    task_text = [f"{task.title} · {task.status}" for task in open_tasks] or ["대기 중인 업무가 없습니다."]
    return (
        "<section class='portfolio'><h3>지속 업무 현황</h3>"
        f"<div><strong>현재 목표</strong>{_list(goal_text)}</div>"
        f"<div><strong>진행·대기 업무</strong>{_list(task_text)}</div>"
        "</section>"
    )


def _list(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def _next_action(state: CognitiveState) -> str:
    if state.lifecycle_status.value == "PAUSED":
        text = "Cognitive Core가 일시 중지되었습니다. 다음 due cycle 전에 재개하세요."
    elif state.lifecycle_status.value == "FAILED":
        text = "마지막 cycle이 실패했습니다. 다음 실행 전에 Technical details를 확인하세요."
    elif state.next_wakeup_at:
        text = f"다음 자율 검토는 {state.next_wakeup_at.isoformat(sep=' ', timespec='minutes')}에 예약되어 있습니다."
    else:
        text = "첫 Proactive cycle을 실행해 기준선을 만드세요."
    return f"<section class='next-action'><h3>다음 행동</h3><p>{html.escape(text)}</p></section>"


_CSS = """
.cognitive-title { margin-bottom: 0; color: #102a43; }
.cognitive-subtitle { margin-top: 5px; color: #526b84; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 14px 0; }
.summary-card { border: 1px solid #d7e2ee; border-radius: 12px; padding: 14px; background: white; }
.summary-card span { display:block; color:#526b84; font-size:.82rem; margin-bottom:7px; }.summary-card strong { color:#102a43; font-size:1.05rem; }
.summary-card.data { border-top: 4px solid #2d8f6f; }.summary-card.problem { border-top: 4px solid #df8b22; }.summary-card.schedule { border-top: 4px solid #5b6ee1; }.summary-card.state { border-top: 4px solid #0a6ed1; }
.react-timeline { margin:18px 0; padding:18px 20px; border:1px solid #c9d9ea; border-radius:14px; background:#fbfdff; }.react-timeline h3 { margin:0; color:#102a43; }.timeline-intro,.react-timeline.empty p { margin:6px 0 16px; color:#526b84; font-size:.88rem; }.timeline-item { position:relative; display:grid; grid-template-columns:26px minmax(0, 1fr); padding:0 0 18px; }.timeline-item:last-child { padding-bottom:0; }.timeline-item:not(:last-child)::before { content:""; position:absolute; top:19px; bottom:0; left:9px; width:2px; background:#d7e2ee; }.timeline-marker { width:12px; height:12px; margin:4px 0 0 4px; border:3px solid #95a9bd; border-radius:50%; background:#fff; z-index:1; }.timeline-content { padding:0 0 0 5px; }.timeline-meta { display:flex; align-items:center; gap:8px; color:#243b53; font-weight:700; font-size:.9rem; }.timeline-meta > span { margin-left:auto; color:#6b7c93; font-size:.7rem; letter-spacing:.04em; }.timeline-content p { margin:6px 0 0; color:#334e68; font-size:.88rem; line-height:1.45; }.analysis-plan { margin:10px 0 0; padding:9px 12px 9px 28px; border-radius:7px; background:#f1f6fb; color:#334e68; font-size:.84rem; }.analysis-plan li { margin:4px 0; }.timeline-conclusion { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:12px; margin-top:10px; padding:13px; border-radius:8px; background:#f1f8f4; color:#243b53; font-size:.86rem; }.timeline-conclusion strong { color:#102a43; }.timeline-conclusion ul { margin:6px 0 0; padding-left:18px; }.timeline-conclusion li { margin:4px 0; }.timeline-conclusion p { margin:6px 0 0; }.timeline-item.completed .timeline-marker { border-color:#2d8f6f; background:#eff9f3; }.timeline-item.running .timeline-marker { border-color:#0a6ed1; background:#edf5ff; box-shadow:0 0 0 4px #edf5ff; }.timeline-item.failed .timeline-marker,.timeline-item.blocked .timeline-marker { border-color:#b42318; background:#fff3f2; }.timeline-terminal { margin-left:0 !important; padding:3px 7px; border-radius:999px; background:#fff3f2; color:#7a271a !important; font-size:.7rem !important; letter-spacing:0 !important; }
.insights,.next-action,.portfolio { display:inline-block; width:calc(50% - 18px); min-height:138px; vertical-align:top; box-sizing:border-box; margin:8px 12px 8px 0; padding:14px 16px; border-left:4px solid #0a6ed1; border-radius:7px; background:#f5f9fd; }.insights h3,.next-action h3,.portfolio h3 { margin:0 0 8px; color:#102a43; font-size:1rem; }.insights ul,.portfolio ul { margin:0; padding-left:19px; color:#334e68; }.insights li,.portfolio li { margin:5px 0; }.portfolio > div { display:inline-block; width:48%; vertical-align:top; }.insights.decision { border-left-color:#5b6ee1; }.next-action { display:block; width:100%; border-left-color:#2d8f6f; }
@media (max-width: 900px) { .summary-grid,.timeline-conclusion { grid-template-columns: repeat(1, minmax(0, 1fr)); }.insights { width:100%; margin-right:0; } }
"""
