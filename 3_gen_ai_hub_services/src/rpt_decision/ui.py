"""Thin Gradio adapter for the SAP RPT Decision API lab."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .lab_core import (
    DEFAULT_DECISION_STATE,
    HANDOFF_MODE_CANDIDATES,
    HANDOFF_MODE_CRITERIA,
    NEXT_AGENT_CANDIDATES,
    NEXT_AGENT_CRITERIA,
    PRIORITY_CANDIDATES,
    PRIORITY_CRITERIA,
    RISK_CANDIDATES,
    RISK_CRITERIA,
    run_translated_rpt_decision,
)


def _light_theme(gr):
    base = gr.themes.Base(primary_hue=gr.themes.colors.blue)
    values = base.to_dict()["theme"]
    return base.set(**{f"{name}_dark": value for name, value in values.items() if not name.endswith("_dark") and f"{name}_dark" in values})


def _candidate_scores(answer: dict[str, Any], candidates: dict[str, str]) -> list[float | None]:
    """Return API-provided candidate probabilities as percentages."""
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict):
        return [None] * len(candidates)
    scores: list[float | None] = []
    for candidate in candidates:
        try:
            value = float(probabilities[candidate])
        except (KeyError, TypeError, ValueError):
            scores.append(None)
            continue
        scores.append(round(max(0.0, min(100.0, value * 100 if value <= 1 else value)), 2))
    return scores


def _candidate_modal_markup() -> str:
    """Build the read-only candidate settings dialog shown by the UI."""
    priority_criteria = {
        item.split(":", 1)[0]: item.split("—", 1)[-1].strip()
        for item in PRIORITY_CRITERIA
    }
    groups = [
        ("다음 A2A Agent", NEXT_AGENT_CANDIDATES, NEXT_AGENT_CRITERIA),
        ("Handoff 방식", HANDOFF_MODE_CANDIDATES, HANDOFF_MODE_CRITERIA),
        ("운영 위험", RISK_CANDIDATES, RISK_CRITERIA),
        ("처리 우선순위", PRIORITY_CANDIDATES, priority_criteria),
    ]
    sections = "".join(
        (
            "<section style='margin: 0 0 16px;'>"
            f"<h3 style='margin: 0 0 7px; font-size: 1em; color: #202124;'>{title}</h3>"
            "<table style='width: 100%; border-collapse: collapse; font-size: .92em;'>"
            "<thead><tr style='background: #f8fafc; text-align: left;'>"
            "<th style='padding: 8px; border-bottom: 1px solid #d0d5dd;'>키</th>"
            "<th style='padding: 8px; border-bottom: 1px solid #d0d5dd;'>후보</th>"
            "<th style='padding: 8px; border-bottom: 1px solid #d0d5dd;'>선택 기준</th>"
            "</tr></thead><tbody>"
            + "".join(
                f"<tr><td style='padding: 8px; border-bottom: 1px solid #eaecf0;'><code>{key}</code></td>"
                f"<td style='padding: 8px; border-bottom: 1px solid #eaecf0;'>{label}</td>"
                f"<td style='padding: 8px; border-bottom: 1px solid #eaecf0; line-height: 1.45; color: #475467;'>{criteria[key]}</td></tr>"
                for key, label in candidates.items()
            )
            + "</tbody></table></section>"
        )
        for title, candidates, criteria in groups
    )
    return (
        "<dialog id='rpt-decision-candidate-dialog' style='width: min(920px, 92vw); max-height: 80vh; "
        "padding: 22px; border: 1px solid #98a2b3; border-radius: 12px; box-shadow: 0 18px 50px rgba(16,24,40,.24);'>"
        "<h2 style='margin: 0 0 8px; color: #202124; font-size: 1.2em;'>Coordinator 판단 후보</h2>"
        "<p style='margin: 0 0 18px; color: #475467; line-height: 1.5;'>"
        "RPT Decision API 요청에 전달되는 고정 후보입니다. 이 화면은 조회 전용이며 후보를 변경하지 않습니다.</p>"
        f"{sections}"
        "<form method='dialog' style='margin-top: 4px; text-align: right;'><button style='padding: 8px 14px; "
        "border: 1px solid #98a2b3; border-radius: 6px; background: #fff; cursor: pointer;'>닫기</button></form>"
        "</dialog>"
    )


def _decision_figure(result: dict[str, Any]) -> Any:
    """Render RPT candidate probabilities without conflating them with the final choice."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError as error:
        raise RuntimeError("RPT 판단 결과 표시에 plotly가 필요합니다. requirements.txt를 설치하세요.") from error

    answers = result["answers"]
    rpt_answers = result.get("rpt_answers", answers)
    sections = [
        ("다음 A2A Agent", "next_agent", NEXT_AGENT_CANDIDATES, "#1A73E8"),
        ("Handoff 방식", "handoff_mode", HANDOFF_MODE_CANDIDATES, "#E5484D"),
        ("운영 위험", "risk", RISK_CANDIDATES, "#9334E6"),
        ("처리 우선순위", "priority", PRIORITY_CANDIDATES, "#E37400"),
    ]
    chart_labels = {
        "hr_agent": "HR", "scm_agent": "SCM", "rnd_agent": "R&D",
        "delegate_now": "즉시 위임", "request_evidence": "근거 요청", "request_human_approval": "승인 요청",
        "low": "낮음", "medium": "중간", "high": "높음",
        "0": "대기", "1": "이번 주", "2": "오늘",
    }
    figure = make_subplots(
        rows=2, cols=2,
        subplot_titles=[title for title, _name, _candidates, _color in sections],
        horizontal_spacing=0.22, vertical_spacing=0.20,
    )
    positions = [(1, 1), (1, 2), (2, 1), (2, 2)]
    for index, ((title, name, candidates, color), (row, column)) in enumerate(zip(sections, positions, strict=True)):
        answer = answers[name]
        selected = str(
            answer.get("semantic_score", answer.get("score"))
            if name == "priority"
            else answer.get("semantic_choice", answer.get("choice", ""))
        )
        selected_label = candidates.get(selected, "미확정")
        rpt_answer = rpt_answers.get(name, {})
        scores = _candidate_scores(rpt_answer if isinstance(rpt_answer, dict) else {}, candidates)
        raw_choice = max(
            candidates,
            key=lambda candidate: scores[list(candidates).index(candidate)] if scores[list(candidates).index(candidate)] is not None else -1,
        )
        labels = [chart_labels.get(candidate, candidates[candidate]) for candidate in candidates]
        values = [score if score is not None else 0 for score in scores]
        figure.add_trace(go.Bar(
            x=values, y=labels, orientation="h",
            marker_color=[color if candidate == raw_choice else "#D0D5DD" for candidate in candidates],
            text=[f"{value:.1f}%" if score is not None else "미제공" for value, score in zip(values, scores, strict=True)],
            textposition="auto",
            hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
            showlegend=False,
        ), row=row, col=column)
        figure.layout.annotations[index].update(text=f"{title} · 최종 판단: {selected_label}")
        figure.update_xaxes(range=[0, 100], showgrid=False, showticklabels=False, showline=False, zeroline=False, row=row, col=column)
        figure.update_yaxes(autorange="reversed", tickfont={"size": 12}, showline=False, row=row, col=column)
    figure.update_layout(
        title={"text": "Coordinator 판단 결과 · SAP RPT 후보 확률과 최종 선택", "x": 0.02, "xanchor": "left", "font": {"size": 18}},
        height=610, margin={"l": 105, "r": 35, "t": 75, "b": 35}, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
    )
    figure.add_shape(type="line", xref="paper", yref="paper", x0=0.5, x1=0.5, y0=0, y1=1, line={"color": "#EAECF0", "width": 1})
    figure.add_shape(type="line", xref="paper", yref="paper", x0=0, x1=1, y0=0.5, y1=0.5, line={"color": "#EAECF0", "width": 1})
    return figure


def _decision_api_key() -> str:
    """Read the project-root API key even if the kernel value is blank."""
    token = os.getenv("SAP_RPT_API_KEY", "").strip()
    if token:
        return token
    try:
        from dotenv import dotenv_values
    except ImportError:
        return ""
    project_root = Path(__file__).resolve().parents[3]
    return str(dotenv_values(project_root / ".env").get("SAP_RPT_API_KEY") or "").strip()


def build_rpt_decision_ui() -> Any:
    """Build the local, read-only Decision API UI."""
    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError("gradio가 없습니다. requirements.txt를 설치하세요.") from error

    def decide(state: str) -> Any:
        if not state.strip():
            raise ValueError("주문 예외 task state를 입력하세요.")
        api_key = _decision_api_key()
        if not api_key:
            raise RuntimeError("프로젝트 루트 .env에 SAP_RPT_API_KEY를 설정한 뒤 UI 셀을 다시 실행하세요.")
        result = run_translated_rpt_decision(state, api_key)
        return _decision_figure(result)

    with gr.Blocks(title="SAP RPT Decision API", theme=_light_theme(gr)) as app:
        gr.Markdown("# SAP RPT Decision API · A2A Coordinator")
        with gr.Row(equal_height=True):
            state = gr.Textbox(
                label="주문 예외 task state",
                value=DEFAULT_DECISION_STATE,
                lines=5,
                scale=5,
            )
            with gr.Column(scale=1):
                settings = gr.Button(
                    "판단 후보 설정",
                    variant="secondary",
                    elem_id="rpt-decision-candidates-button",
                )
                run = gr.Button("Coordinator 판단", variant="primary")
        result = gr.Plot(label="Coordinator 판단 결과")
        gr.HTML(_candidate_modal_markup())
        run.click(decide, inputs=state, outputs=result)
        settings.click(
            fn=None,
            inputs=None,
            outputs=None,
            js="""() => {
                const dialog = document.getElementById('rpt-decision-candidate-dialog');
                if (dialog && !dialog.open) dialog.showModal();
            }""",
        )
    return app
