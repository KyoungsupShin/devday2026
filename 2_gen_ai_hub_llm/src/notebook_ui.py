"""Gradio views specific to the Gen AI Hub LLM notebooks.

The functions create UI blocks but never launch a public share link.  A notebook
explicitly calls ``launch(inline=True)`` when the learner is ready.
"""
from __future__ import annotations

import os
from html import escape
from collections.abc import Iterator
from typing import Any, Callable

from .prompt_model.lab_core import (
    ADAPTIVE_REACT_SYSTEM_INSTRUCTION,
    REACT_SYSTEM_INSTRUCTION,
)
from .prompt_model.lesson_support.config import load_settings
from src.reranker.demo_cases import ORDER_RISK_DEMO_CASES


MODE_SYSTEM_PROMPTS = {
    "chat": "너는 친절한 교육 보조자다. 한국어로 간결하게 답한다.",
    "react": REACT_SYSTEM_INSTRUCTION,
    "adaptive_react": ADAPTIVE_REACT_SYSTEM_INSTRUCTION,
}


def _gradio():
    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError("Gradio가 없습니다. python3 -m pip install --user -r requirements.txt 를 실행하세요.") from error
    return gr


def _history_messages(history: list[Any] | None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in history or []:
        if isinstance(item, dict) and item.get("role") in {"user", "assistant"}:
            messages.append({"role": item["role"], "content": str(item.get("content", ""))})
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            messages.extend([
                {"role": "user", "content": str(item[0])},
                {"role": "assistant", "content": str(item[1])},
            ])
    return messages


def build_chat_ui(
    chat_runner: Callable[..., dict[str, str]],
    chat_stream_runner: Callable[..., Iterator[str]] | None = None,
    react_agent_runner: Callable[..., dict[str, Any]] | None = None,
    adaptive_react_agent_runner: Callable[..., dict[str, Any]] | None = None,
):
    """Create a chat UI that can also run the bounded ReAct exercise."""
    gr = _gradio()

    def render_react_step(index: int, step: dict[str, Any]) -> str:
        plan = step.get("plan")
        if isinstance(plan, dict):
            subtasks = [
                str(task.get("goal") or task.get("id") or "작업")
                for task in plan.get("subtasks", [])
                if isinstance(task, dict)
            ]
            summary = ", ".join(subtasks) or "질문을 분석해 필요한 작업을 정했습니다."
            entries = [("Plan", summary), ("Observation", "작업 계획을 만들었습니다.")]
        else:
            entries: list[tuple[str, str]] = []
            if thinking := str(step.get("thinking", "")).strip():
                entries.append(("Thought · &lt;thinking&gt;", thinking))
            if action := str(step.get("action", "")).strip():
                entries.append(("Action", action))
            if observation := str(step.get("observation", "")).strip():
                entries.append(("Observation", observation))
            if evaluation := str(step.get("evaluation", "")).strip():
                entries.append(("Evaluation · &lt;evaluation&gt;", evaluation))
            if answer := str(step.get("answer", "")).strip():
                entries.append(("Final Answer · &lt;answer&gt;", answer))

        return "".join(
            '<li class="react-timeline__step react-timeline__step--completed">'
            '<span class="react-timeline__marker" aria-hidden="true"></span>'
            '<div class="react-timeline__content">'
            f'<div class="react-timeline__title">Step {index} · {label}</div>'
            f'<p>{escape(value).replace(chr(10), "<br>")}</p>'
            "</div></li>"
            for label, value in entries
        )

    def render_react_timeline(steps: list[Any]) -> str:
        trace = "".join(
            render_react_step(index, step)
            for index, step in enumerate(steps, start=1)
            if isinstance(step, dict)
        )
        return (
            '<section class="react-timeline" aria-label="ReAct Agent 실행 과정">'
            '<h3>ReAct Agent 실행 과정</h3>'
            '<p class="react-timeline__intro">공개 태그와 도구 호출을 실행 순서대로 표시합니다.</p>'
            f"<ol>{trace or '<li>수행한 작업이 없습니다.</li>'}</ol></section>"
        )

    def render_chat_view(history: list[dict[str, str]]) -> str:
        items: list[str] = []
        for item in history:
            role = item.get("role")
            content = str(item.get("content", ""))
            if role == "timeline":
                items.append(f'<div class="chat-feed__timeline">{content}</div>')
                continue
            if role not in {"user", "assistant"}:
                continue
            role_class = "chat-feed__message--user" if role == "user" else "chat-feed__message--assistant"
            items.append(
                f'<div class="chat-feed__message {role_class}">'
                f'<div class="chat-feed__bubble">{escape(content).replace(chr(10), "<br>")}</div></div>'
            )
        empty = "<p class=\"chat-feed__empty\">질문을 입력해 대화를 시작하세요.</p>"
        return f'<section class="chat-feed">{"".join(items) or empty}</section>'

    def reply(
        message: str, history: list[Any], chat_config: dict[str, str],
    ) -> Iterator[tuple[str, list[dict[str, str]], Any]]:
        visible_history = [
            {"role": item["role"], "content": str(item.get("content", ""))}
            for item in history or []
            if isinstance(item, dict) and item.get("role") in {"user", "assistant", "timeline"}
        ]
        if not message.strip():
            updated = [*visible_history, {"role": "assistant", "content": "질문을 입력하세요."}]
            yield "", updated, render_chat_view(updated)
            return
        next_history = [*visible_history, {"role": "user", "content": message}]
        settings = load_settings()
        selected_model = chat_config.get("model_name", "").strip() or settings.llm_model
        system_prompt = chat_config.get("system_prompt", "")
        try:
            if chat_config.get("mode") in {"react", "adaptive_react"}:
                is_adaptive = chat_config.get("mode") == "adaptive_react"
                agent_runner = adaptive_react_agent_runner if is_adaptive else react_agent_runner
                if agent_runner is None:
                    message = (
                        "Adaptive ReAct 에이전트 실행기가 연결되지 않았습니다."
                        if is_adaptive else "ReAct 에이전트 실행기가 연결되지 않았습니다."
                    )
                    updated = [*next_history, {"role": "assistant", "content": message}]
                    yield "", updated, render_chat_view(updated)
                    return
                outcome = agent_runner(
                    message=message,
                    settings=settings,
                    history=_history_messages(history),
                    system_prompt=system_prompt,
                    model=selected_model,
                )
                steps = outcome.get("trace", [])
                timeline = render_react_timeline(steps)
                timeline_history = [*next_history, {"role": "timeline", "content": timeline}]
                yield "", timeline_history, render_chat_view(timeline_history)
                updated = [
                    *timeline_history,
                    {"role": "assistant", "content": str(outcome["reply"])},
                ]
                yield "", updated, render_chat_view(updated)
                return
            if chat_stream_runner is not None:
                accumulated = ""
                yield "", next_history, render_chat_view(next_history)
                for delta in chat_stream_runner(
                    message=message,
                    settings=settings,
                    history=_history_messages(history),
                    system_prompt=system_prompt,
                    model=selected_model,
                ):
                    accumulated += delta
                    yield "", [
                        *next_history,
                        {"role": "assistant", "content": accumulated},
                    ], render_chat_view([
                        *next_history,
                        {"role": "assistant", "content": accumulated},
                    ])
                return
            outcome = chat_runner(
                message=message,
                settings=settings,
                history=_history_messages(history),
                system_prompt=system_prompt,
                model=selected_model,
            )
            yield "", [
                *next_history,
                {"role": "assistant", "content": str(outcome["reply"])},
            ], render_chat_view([
                *next_history,
                {"role": "assistant", "content": str(outcome["reply"])},
            ])
        except Exception as error:
            yield "", [
                *next_history,
                {"role": "assistant", "content": f"호출 실패: {type(error).__name__}: {error}"},
            ], render_chat_view([
                *next_history,
                {"role": "assistant", "content": f"호출 실패: {type(error).__name__}: {error}"},
            ])

    settings = load_settings()
    modal_css = """
    #chat-settings-modal {
      position: fixed !important; top: 50% !important; left: 50% !important; right: auto !important; bottom: auto !important;
      transform: translate(-50%, -50%) !important; z-index: 1000 !important;
      width: min(760px, calc(100vw - 32px)) !important; max-width: none !important;
      max-height: calc(100vh - 48px) !important; box-sizing: border-box !important;
      padding: 20px !important; border: 1px solid #d0d7de !important;
      border-radius: 14px !important; background: white !important; box-shadow: 0 18px 60px rgba(0,0,0,.22) !important;
      overflow-y: auto !important;
    }
    #chat-settings-modal > .form,
    #chat-settings-modal .form {
      display: flex !important; flex-direction: column !important; flex-wrap: nowrap !important;
      align-items: stretch !important;
    }
    #chat-settings-modal .block {
      width: 100% !important; min-width: 0 !important;
    }
    #chat-settings-modal textarea {
      max-height: 34vh !important;
    }
    .chat-feed{height:420px;overflow-y:auto;padding:16px;border:1px solid #d7e3eb;border-radius:12px;background:#edf2f6}
    .chat-feed__empty{margin:0;color:#617586;font-size:13px}.chat-feed__message{display:flex;margin:0 0 12px}.chat-feed__message--user{justify-content:flex-end}.chat-feed__bubble{max-width:min(75%,680px);padding:10px 12px;border:1px solid #d7e0e8;border-radius:4px 13px 13px 13px;background:#fff;color:#25313d;font-size:13px;line-height:1.5;box-shadow:0 1px 2px rgba(40,58,74,.08)}
    .chat-feed__message--user .chat-feed__bubble{border-color:#d4cde3;border-radius:13px 4px 13px 13px;background:#f6f2ff}.chat-feed__timeline{margin:0 0 12px}
    .react-timeline{margin:0;padding:12px 14px;border:1px solid #d7e3eb;border-radius:12px;background:#f8fbff}
    .react-timeline h3{margin:0;color:#314b64;font-size:15px}.react-timeline__intro{margin:4px 0 10px;color:#617586;font-size:12px}
    .react-timeline ol{display:grid;gap:5px;margin:0;padding:0;list-style:none}.react-timeline__step{position:relative;padding:0 0 0 26px}
    .react-timeline__step:not(:last-child)::after{position:absolute;top:18px;bottom:-7px;left:8px;width:2px;background:#d6e2e9;content:""}
    .react-timeline__marker{position:absolute;z-index:1;top:8px;left:3px;width:14px;height:14px;border:3px solid #2f9368;border-radius:50%;background:#2f9368;box-shadow:0 0 0 3px #f8fbff}
    .react-timeline__marker::after{display:block;color:#fff;content:"✓";font-size:10px;font-weight:900;line-height:14px;text-align:center}
    .react-timeline__content{min-height:0;padding:7px 10px;border:1px solid #d7e3eb;border-radius:8px;background:#fff;box-shadow:0 1px 2px rgba(48,73,94,.05)}
    .react-timeline__title{color:#314b64;font-size:12px;font-weight:800}.react-timeline__content p{margin:3px 0 0;color:#25313d;font-size:12px;line-height:1.4;overflow-wrap:anywhere}
    """
    with gr.Blocks(css=modal_css, fill_width=True) as app:
        gr.Markdown(
            "# LLM Chatbot UI\n"
            "대화 내용은 현재 Jupyter session의 브라우저 UI에만 유지됩니다. prompt, 모델, 실행 방식은 ⚙️ 설정에서 바꿀 수 있습니다."
        )
        chat_config = gr.State({
            "system_prompt": MODE_SYSTEM_PROMPTS["chat"],
            "model_name": settings.llm_model,
            "mode": "chat",
        })
        with gr.Row():
            gr.Markdown("질문을 입력해 대화를 시작하세요.")
            open_settings = gr.Button("⚙️ 설정", size="sm")
        chat_history = gr.State([])
        chat_view = gr.HTML(render_chat_view([]))
        with gr.Row(equal_height=True):
            textbox = gr.Textbox(
                placeholder="메시지를 입력하세요…", show_label=False, scale=8,
            )
            send = gr.Button("보내기", variant="primary", scale=1)
        clear = gr.Button("대화 지우기", size="sm")
        with gr.Column(visible=False, elem_id="chat-settings-modal") as settings_modal:
            gr.Markdown("### 채팅 설정")
            system_prompt = gr.Textbox(
                label="System prompt",
                value=MODE_SYSTEM_PROMPTS["chat"],
                lines=8,
            )
            model_name = gr.Textbox(label="Model (blank uses LLM_MODEL)", value=settings.llm_model)
            mode = gr.Radio(
                label="실행 방식",
                choices=[
                    ("일반 Chat", "chat"),
                    ("ReAct Agent (계산 도구)", "react"),
                    ("Adaptive ReAct Agent", "adaptive_react"),
                ],
                value="chat",
                info="ReAct Agent는 계산 도구를 사용합니다. Adaptive ReAct Agent는 먼저 질문을 분류하고 하위 작업을 역할별로 배정한 뒤 실행합니다.",
            )
            with gr.Row():
                save_settings_button = gr.Button("적용", variant="primary")
                close_settings = gr.Button("닫기")

        open_settings.click(lambda: gr.update(visible=True), outputs=settings_modal)
        close_settings.click(lambda: gr.update(visible=False), outputs=settings_modal)
        mode.change(
            lambda selected_mode: gr.update(
                value=MODE_SYSTEM_PROMPTS.get(selected_mode, MODE_SYSTEM_PROMPTS["chat"]),
            ),
            inputs=mode,
            outputs=system_prompt,
        )
        save_settings_button.click(
            lambda prompt, model, selected_mode: (
                {"system_prompt": prompt, "model_name": model, "mode": selected_mode},
                gr.update(visible=False),
            ),
            inputs=[system_prompt, model_name, mode],
            outputs=[chat_config, settings_modal],
        )
        chat_inputs = [textbox, chat_history, chat_config]
        chat_outputs = [textbox, chat_history, chat_view]
        textbox.submit(reply, inputs=chat_inputs, outputs=chat_outputs)
        send.click(reply, inputs=chat_inputs, outputs=chat_outputs)
        clear.click(
            lambda: ("", [], render_chat_view([])),
            outputs=chat_outputs,
        )
    return app


def build_embedding_reranker_comparison_ui(
    comparison_runner: Callable[..., dict[str, Any]],
):
    """Create a read-only view for the embedding retrieval/reranking lab."""
    gr = _gradio()
    headers = [
        "정책", "라벨", "Embedding 순위", "Embedding 점수",
        "Reranker 순위", "Reranker 점수",
    ]

    def run_comparison(case_text: str, top_k: int) -> tuple[str, list[list[object]], dict[str, Any]]:
        try:
            outcome = comparison_runner(case_text, load_settings(), top_k=int(top_k))
            embedding = outcome["embedding"]
            reranker = outcome["reranker"]
            agreement = "일치" if outcome["same_top_recommendation"] else "불일치"
            summary = (
                "### 추천 비교\n"
                f"- **Embedding Top-1**: `{embedding['recommended']}`  \n"
                f"- **Reranker Top-1**: `{reranker['recommendation']}`  \n"
                f"- **추천 결과**: **{agreement}**  \n"
                f"- **처리 시간**: Embedding {embedding['latency_ms']:.0f} ms · "
                f"Reranker {reranker['latency_ms']:.0f} ms"
            )
            rows = [
                [
                    row["decision"], row["label"], row["embedding_rank"],
                    round(float(row["embedding_score"]), 4), row["reranker_rank"],
                    (round(float(row["reranker_score"]), 4)
                     if row["reranker_score"] is not None else None),
                ]
                for row in outcome["comparison_rows"]
            ]
            evidence = {
                "top_k": embedding["retrieved_prototype_count"],
                "embedding_ranked_candidates": embedding["ranked_candidates"],
                "reranker_ranked_candidates": reranker["ranked_candidates"],
            }
            return summary, rows, evidence
        except Exception as error:
            return (
                f"### 분석할 수 없습니다\n`{type(error).__name__}: {error}`",
                [],
                {"error": f"{type(error).__name__}: {error}"},
            )

    with gr.Blocks(fill_width=True) as app:
        gr.Markdown(
            "# Embedding · Reranker 비교\n"
            "정책 후보를 찾는 Embedding 단계와, 찾은 후보를 다시 정렬하는 Reranker 단계를 비교합니다. "
            "이 화면은 추천 결과만 보여 주며 외부 주문 상태를 변경하지 않습니다."
        )
        with gr.Row():
            with gr.Column(scale=2):
                case = gr.Textbox(
                    label="고객 행동",
                    value=(
                        "인증된 고객이 1분에 6회 주문을 시도했습니다. "
                        "중복 주문, 결제 실패, 한도 초과, 자동화 정황은 없습니다."
                    ),
                    lines=5,
                )
                top_k = gr.Slider(
                    minimum=1, maximum=6, value=4, step=1,
                    label="Embedding Top-K",
                    info="Reranker가 다시 읽을 후보 수입니다.",
                )
                run = gr.Button("비교 실행", variant="primary")
            with gr.Column(scale=1):
                summary = gr.Markdown("실행하면 두 Top-1 추천과 처리 시간을 표시합니다.")
        ranking = gr.Dataframe(
            headers=headers, datatype=["str", "str", "number", "number", "number", "number"],
            label="정책별 순위 비교", interactive=False, wrap=True,
        )
        with gr.Accordion("후보별 점수 근거 보기", open=False):
            evidence = gr.JSON(label="검색 · 재정렬 결과")
        run.click(run_comparison, inputs=[case, top_k], outputs=[summary, ranking, evidence])
    return app


def build_embedding_ui(comparison_cluster_runner: Callable[..., dict[str, Any]]):
    """Create a comparison UI with a session-local interactive cluster chart."""
    gr = _gradio()
    load_settings()
    configured_model = os.getenv("EMBED_MODEL", "amazon--titan-embed-image")

    def cluster_view(state: object) -> object:
        entries = state.get("entries", []) if isinstance(state, dict) else []
        if not entries:
            return None
        try:
            import plotly.graph_objects as go
        except ImportError as error:
            raise RuntimeError(
                "2D cluster 표시에 plotly가 필요합니다. requirements.txt를 다시 설치하세요."
            ) from error

        palette = ["#5B8FF9", "#61DDAA", "#F6BD16", "#7262FD", "#E8684A"]
        figure = go.Figure()
        for cluster_id in sorted({int(entry["cluster"]) for entry in entries}):
            members = [entry for entry in entries if int(entry["cluster"]) == cluster_id]
            figure.add_trace(
                go.Scatter(
                    x=[float(entry["x"]) for entry in members],
                    y=[float(entry["y"]) for entry in members],
                    mode="markers+text",
                    name=f"Cluster {cluster_id}",
                    text=[str(entry["text"]).replace("\n", " ")[:24] for entry in members],
                    textposition="top center",
                    textfont={"size": 11, "color": "#344054"},
                    customdata=[[int(entry["index"]), str(entry["text"])] for entry in members],
                    hovertemplate=(
                        "<b>%{customdata[1]}</b><br>Entry %{customdata[0]} · Cluster "
                        + str(cluster_id)
                        + "<br>UMAP 1 %{x:.3f}<br>UMAP 2 %{y:.3f}<extra></extra>"
                    ),
                    marker={
                        "size": 15, "color": palette[cluster_id % len(palette)],
                        "line": {"color": "#FFFFFF", "width": 2}, "opacity": 0.95,
                    },
                )
            )
        figure.update_layout(
            template="plotly_white", height=460,
            margin={"l": 50, "r": 30, "t": 64, "b": 48},
            paper_bgcolor="#FFFFFF", plot_bgcolor="#F8FAFC",
            title={
                "text": (
                    "Embedding space · fixed-reference UMAP"
                    if state.get("projection") == "reference_umap"
                    else "Embedding space · UMAP"
                ),
                "x": 0.02,
                "xanchor": "left",
            },
            font={"family": "Inter, Arial, sans-serif", "color": "#344054"},
            legend={"orientation": "h", "y": 1.05, "x": 1, "xanchor": "right"},
            hoverlabel={"bgcolor": "#101828", "font": {"color": "white"}},
        )

        def padded_range(values: list[float], padding_ratio: float = 0.45) -> list[float]:
            low, high = min(values), max(values)
            padding = max((high - low) * padding_ratio, 0.1)
            return [low - padding, high + padding]

        def autoscaled_range(axis: str, values: list[float]) -> list[float]:
            """Keep the reference map visible and zoom out for new outliers."""
            reference_range = (
                state.get("coordinate_range", {}).get(axis)
                if isinstance(state, dict)
                else None
            )
            if isinstance(reference_range, list) and len(reference_range) == 2:
                return padded_range(
                    [float(reference_range[0]), float(reference_range[1]), *values],
                    padding_ratio=0.22,
                )
            return padded_range(values)

        figure.update_xaxes(
            title="UMAP 1",
            range=autoscaled_range("x", [float(entry["x"]) for entry in entries]),
            zeroline=True,
            zerolinecolor="#D0D5DD",
            gridcolor="#EAECF0",
        )
        figure.update_yaxes(
            title="UMAP 2",
            range=autoscaled_range("y", [float(entry["y"]) for entry in entries]),
            zeroline=True,
            zerolinecolor="#D0D5DD",
            gridcolor="#EAECF0",
        )
        return figure

    def compare_and_add(text_a: str, text_b: str, state: object) -> tuple[dict[str, Any], object, object]:
        try:
            outcome = comparison_cluster_runner(
                text_a=text_a, text_b=text_b, state=state, settings=load_settings(), model=None,
                use_reference_umap=True,
            )
            cluster = outcome["cluster"]
            return outcome["comparison"], cluster, cluster_view(cluster)
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}, state, cluster_view(state)

    layout_css = """
    #embedding-comparison-row { flex-wrap: nowrap !important; gap: 16px !important; }
    #embedding-comparison-row > * { min-width: 0 !important; }
    """
    with gr.Blocks(css=layout_css, fill_width=True) as app:
        gr.Markdown(f"Embedding model: `{configured_model}` (`.env`의 `EMBED_MODEL`)")
        with gr.Row(equal_height=True, elem_id="embedding-comparison-row"):
            with gr.Column(scale=1, min_width=0):
                first = gr.Textbox(label="Text A", value="apple")
                second = gr.Textbox(label="Text B", value="orange")
                run = gr.Button("Compare", variant="primary")
            with gr.Column(scale=1, min_width=0):
                output = gr.JSON(label="Result", min_height=260)
        cluster_state = gr.State(value=None)
        cluster_plot = gr.Plot(label=None, show_label=False)
        run.click(
            compare_and_add,
            inputs=[first, second, cluster_state],
            outputs=[output, cluster_state, cluster_plot],
        )
    return app


def build_business_embedding_ui(
    lab_runner: Callable[..., dict[str, Any]],
    cases: list[dict[str, str]],
    n_clusters: int = 4,
):
    """Create a progressive, read-only business-routing view."""
    gr = _gradio()
    load_settings()  # Loads the repository .env before reading EMBED_MODEL for the view.
    configured_model = os.getenv("EMBED_MODEL", "amazon--titan-embed-image")
    queue_names = {
        "logistics": "물류·배송 팀",
        "payment": "결제 팀",
        "compliance": "컴플라이언스 팀",
        "technical": "기술 지원 팀",
    }

    def queue_name(label: object) -> str:
        value = str(label)
        return queue_names.get(value, value.replace("_", " ").title() + " 팀")

    def render_result(outcome: dict[str, Any]) -> tuple[str, str, str, dict[str, Any], object]:
        """Translate numeric evidence into a clear routing decision."""
        if "error" in outcome:
            message = escape(str(outcome["error"]))
            return (
                '<div class="routing-decision routing-decision--review"><span class="decision-kicker">분석할 수 없습니다</span>'
                f"<h2>입력 또는 연결을 확인해주세요</h2><p>{message}</p></div>",
                "",
                "",
                outcome,
                gr.update(visible=True),
            )

        recommendation = outcome["recommendation"]
        similarities = list(recommendation["label_similarity"].items())
        top_score = float(similarities[0][1]) if similarities else 0.0
        margin = top_score - float(similarities[1][1]) if len(similarities) > 1 else top_score
        needs_review = top_score < 0.55 or margin < 0.18
        status = "사람 검토 권장" if needs_review else "전달 추천"
        status_class = "routing-decision--review" if needs_review else "routing-decision--ready"
        queue = queue_name(recommendation["recommended_queue"])
        second_queue = queue_name(similarities[1][0]) if len(similarities) > 1 else None
        if needs_review:
            reason = (
                f"{queue}이 가장 가깝지만, {second_queue}과도 의미가 겹칠 수 있습니다."
                if second_queue
                else "추천 근거가 충분하지 않아 사람이 내용을 확인해야 합니다."
            )
            next_step = "담당자가 문의 내용을 확인한 뒤 최종 팀을 선택하세요."
        else:
            reason = f"입력한 문의가 {queue} 사례와 가장 뚜렷하게 유사합니다."
            next_step = "운영 정책에 따라 해당 팀 전달 전 최종 내용을 확인하세요."
        summary = f"""
        <div class="routing-decision {status_class}">
          <span class="decision-kicker">{status}</span>
          <h2>{escape(queue)}으로 전달하세요</h2>
          <p class="decision-reason">{escape(reason)}</p>
          <div class="decision-next"><b>다음 단계</b><span>{escape(next_step)}</span></div>
        </div>
        """
        confidence = "높음" if top_score >= 0.75 else "보통" if top_score >= 0.55 else "낮음"
        separation = "뚜렷함" if margin >= 0.18 else "애매함"
        interpretation = f"""
        <div class="interpretation">
          <div><span>결과 점수</span><strong>{top_score:.3f}</strong></div>
          <div><span>2순위와 차이</span><strong>{margin:.3f}</strong></div>
          <div><span>추천 확신도</span><strong>{confidence}</strong></div>
          <div><span>후보 간 구분</span><strong>{separation}</strong></div>
        </div>
        """
        bars = []
        for label, score in similarities:
            value = float(score)
            width = max(0, min(100, value * 100))
            bars.append(
                f"<div class=\"similarity-row\"><span>{escape(queue_name(label))}</span>"
                f"<div class=\"similarity-track\"><i style=\"width:{width:.1f}%\"></i></div>"
                f"<b>{value:.3f}</b></div>"
            )
        similarity_view = "<div class=\"similarity-panel\"><h3>다른 가능성</h3>" + "".join(bars) + "</div>"
        return summary, interpretation, similarity_view, outcome, gr.update(visible=True)

    def recommend(ticket: str) -> tuple[str, str, str, dict[str, Any], object]:
        if not ticket.strip():
            return render_result({"error": "새 업무 문의를 입력하세요."})
        try:
            outcome = lab_runner(
                ticket=ticket,
                cases=cases,
                settings=load_settings(),
                n_clusters=n_clusters,
            )
            return render_result(outcome)
        except Exception as error:
            return render_result({"error": f"{type(error).__name__}: {error}"})

    layout_css = """
    .business-routing { max-width: 1180px; margin: 0 auto; color: #1f2937; }
    .routing-header { margin: 4px 0 24px; }
    .routing-header h1 { margin: 0 0 5px; font-size: 1.5rem; letter-spacing: -.035em; }
    .routing-header p { margin: 0; color: #6b7280; font-size: .94rem; }
    .routing-input { padding: 24px; border: 1px solid #e5e7eb; border-radius: 16px; background: #fff; box-shadow: 0 6px 24px rgba(31,41,55,.04); }
    .example-label { margin: 18px 0 8px; color: #6b7280; font-size: .82rem; font-weight: 650; }
    #example-row { gap: 8px !important; }
    #routing-actions { margin-top: 18px; align-items: center; }
    #routing-actions > *:first-child { flex-grow: 1 !important; }
    #routing-main-row { flex-wrap: nowrap !important; gap: 24px !important; align-items: flex-start !important; }
    #routing-main-row > * { min-width: 0 !important; }
    #routing-result { margin-top: 0; }
    .routing-decision { padding: 26px 28px; border: 1px solid; border-radius: 16px; }
    .routing-decision--ready { border-color: #b9d7ff; background: #f3f8ff; }
    .routing-decision--review { border-color: #f1ce91; background: #fff9ef; }
    .decision-kicker { display: block; margin-bottom: 8px; color: #8a5b0a; font-size: .78rem; font-weight: 750; letter-spacing: .06em; }
    .routing-decision--ready .decision-kicker { color: #2563b8; }
    .routing-decision h2 { margin: 0; font-size: 1.55rem; letter-spacing: -.03em; }
    .decision-reason { margin: 10px 0 22px; color: #4b5563; font-size: 1rem; line-height: 1.55; }
    .decision-next { display: flex; gap: 12px; padding-top: 16px; border-top: 1px solid rgba(99,102,110,.18); font-size: .9rem; }
    .decision-next b { white-space: nowrap; }
    .decision-next span { color: #596579; }
    .interpretation { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 14px 0 2px; }
    .interpretation div { padding: 13px 14px; border: 1px solid #e6eaf0; border-radius: 12px; background: #fff; }
    .interpretation span { display: block; margin-bottom: 3px; color: #697586; font-size: .78rem; }
    .interpretation strong { font-size: 1rem; }
    .similarity-panel { padding: 4px 2px 10px; }
    .similarity-panel h3 { margin: 0 0 12px; font-size: .95rem; }
    .similarity-row { display: grid; grid-template-columns: 116px 1fr 48px; align-items: center; gap: 10px; margin: 9px 0; font-size: .85rem; }
    .similarity-track { height: 8px; overflow: hidden; border-radius: 999px; background: #e7ecf3; }
    .similarity-track i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #4185e6, #6aa9ff); }
    .similarity-row b { color: #43516a; font-size: .8rem; text-align: right; }
    @media (max-width: 900px) {
      #routing-main-row { flex-wrap: wrap !important; }
      #routing-result { margin-top: 4px; }
      .routing-input { padding: 18px; }
      .routing-decision { padding: 20px; }
      .interpretation { grid-template-columns: repeat(2, 1fr); }
      .similarity-row { grid-template-columns: 95px 1fr 45px; gap: 7px; }
    }
    """
    with gr.Blocks(css=layout_css, fill_width=True) as app:
        with gr.Column(elem_classes="business-routing"):
            gr.HTML(
                '<div class="routing-header"><h1>업무 문의 라우팅</h1>'
                '<p>문의 내용을 바탕으로 담당 팀을 추천합니다.</p></div>'
            )
            with gr.Row(elem_id="routing-main-row"):
                with gr.Column(scale=1, min_width=400, elem_classes="routing-input"):
                    ticket = gr.Textbox(
                        label="어떤 문의인가요?",
                        value="운송장에는 배송 완료로 나오지만 고객이 물건을 받지 못했습니다.",
                        lines=4,
                        placeholder="고객의 문제와 요청을 구체적으로 입력하세요.",
                    )
                    gr.HTML('<div class="example-label">예시로 시작하기</div>')
                    with gr.Row(elem_id="example-row"):
                        delivery_example = gr.Button("📦 배송 문제", size="sm")
                        payment_example = gr.Button("💳 결제 문제", size="sm")
                        security_example = gr.Button("🔒 계정·개인정보", size="sm")
                        technical_example = gr.Button("🛠 기술 지원", size="sm")
                    with gr.Row(elem_id="routing-actions"):
                        run = gr.Button("라우팅 분석하기 →", variant="primary")
                        reset = gr.Button("새 문의")
                with gr.Column(scale=1, min_width=400, visible=False, elem_id="routing-result") as result_area:
                    summary = gr.HTML()
                    interpretation = gr.HTML()
                    with gr.Accordion("추천 근거와 상세 분석 보기", open=False):
                        similarity = gr.HTML()
                        gr.Markdown(
                            f"모델: `{escape(configured_model)}` · 학습 사례: {len(cases)}건 · 탐색 cluster: {n_clusters}개"
                        )
                        detail = gr.JSON(label="원본 분석 결과", min_height=260)

        example_values = {
            delivery_example: "운송장에는 배송 완료로 나오지만 고객이 물건을 받지 못했습니다.",
            payment_example: "결제는 완료되었는데 주문이 생성되지 않았고 카드 청구만 확인됩니다.",
            security_example: "내 계정 정보가 동의 없이 변경된 것 같습니다. 접근 기록을 확인해주세요.",
            technical_example: "앱에서 로그인 후 화면이 계속 멈추고 오류 메시지가 표시됩니다.",
        }
        for button, example in example_values.items():
            button.click(lambda value=example: value, outputs=ticket)
        run.click(
            recommend,
            inputs=ticket,
            outputs=[summary, interpretation, similarity, detail, result_area],
        )
        reset.click(
            lambda: ("", "", "", "", {}, gr.update(visible=False)),
            outputs=[ticket, summary, interpretation, similarity, detail, result_area],
        )
    return app


def build_decision_reranker_ui(
    decision_runner: Callable[..., dict[str, Any]],
    candidates: list[dict[str, str]],
    default_min_margin: float = 0.0,
    default_min_score: float = 0.0,
    embedding_comparison_runner: Callable[..., dict[str, Any]] | None = None,
):
    """Create a read-only decision view backed by one public core API."""
    gr = _gradio()
    default_behavior = ORDER_RISK_DEMO_CASES[0]["case"]
    example_scenarios = [(case["name"], case["case"]) for case in ORDER_RISK_DEMO_CASES]
    candidate_summary = "\n".join(
        f"- **{candidate['label']}** — {candidate['description']}"
        for candidate in candidates
    )
    modal_css = """
    #decision-settings-modal {
      position: fixed !important; inset: 18vh 24vw auto !important; z-index: 1000 !important;
      max-width: 620px !important; padding: 20px !important; border: 1px solid #d0d7de !important;
      border-radius: 14px !important; background: white !important; box-shadow: 0 18px 60px rgba(0,0,0,.22) !important;
    }
    #decision-main-row { flex-wrap: nowrap !important; gap: 20px !important; align-items: stretch !important; }
    #decision-main-row > * { min-width: 0 !important; }
    .decision-panel { padding: 18px !important; border: 1px solid #d9e2f0 !important; border-radius: 14px !important; background: #fff !important; }
    #decision-example-card { margin-top: 14px !important; border: 1px solid #d9e2f0 !important; border-radius: 12px !important; background: #f8fbff !important; }
    #decision-example-card > .label-wrap { font-weight: 700 !important; }
    .decision-example-button { min-height: 42px !important; text-align: left !important; }
    .decision-result-empty, .decision-result { border: 1px solid #d9e2f0; border-radius: 14px; padding: 18px; background: #fff; }
    .decision-result-empty { color: #5f6368; background: #f8fbff; }
    .decision-result.review { border-left: 5px solid #f9ab00; }
    .decision-result.approve { border-left: 5px solid #1e8e3e; }
    .decision-result.decline { border-left: 5px solid #d93025; }
    .decision-result.error { border-left: 5px solid #d93025; background: #fff8f7; }
    .decision-result-header { display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; }
    .decision-result-kicker { margin: 0; font-size: .78rem; font-weight: 700; color: #5f6368; letter-spacing: .04em; }
    .decision-result-title { margin: 4px 0 0; font-size: 1.45rem; color: #202124; }
    .decision-badge { display: inline-block; padding: 6px 10px; border-radius: 999px; font-size: .82rem; font-weight: 700; white-space: nowrap; }
    .decision-badge.review { background: #fef7e0; color: #8a5300; }
    .decision-badge.approve { background: #e6f4ea; color: #137333; }
    .decision-badge.decline { background: #fce8e6; color: #b3261e; }
    .decision-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 18px 0; }
    .decision-metric { padding: 12px; border-radius: 10px; background: #f8f9fa; }
    .decision-metric span { display: block; font-size: .78rem; color: #5f6368; }
    .decision-metric strong { display: block; margin-top: 4px; font-size: 1.25rem; color: #202124; }
    .decision-evidence { margin-top: 14px; padding-top: 14px; border-top: 1px solid #edf0f2; }
    .decision-evidence h4 { margin: 0 0 5px; font-size: .88rem; color: #3c4043; }
    .decision-evidence p { margin: 0; color: #5f6368; line-height: 1.55; }
    .decision-rankings { margin-top: 14px; }
    .decision-rankings h3 { margin: 0 0 10px; font-size: 1rem; color: #202124; }
    .decision-rank-row { display: grid; grid-template-columns: 28px minmax(90px, 1fr) minmax(100px, 2fr) 50px; align-items: center; gap: 8px; margin: 9px 0; }
    .decision-rank-label { color: #3c4043; font-size: .9rem; }
    .decision-progress { overflow: hidden; height: 9px; border-radius: 999px; background: #e8eaed; }
    .decision-progress > span { display: block; height: 100%; border-radius: inherit; background: #1a73e8; }
    .decision-rank-score { text-align: right; font-variant-numeric: tabular-nums; color: #3c4043; }
    .analysis-result { margin: 0; padding: 0; border: 0; background: transparent; }
    .analysis-result h3 { margin: 0 0 6px; font-size: 1rem; }
    .analysis-result p { margin: 0 0 10px; color: #5f6368; font-size: .88rem; line-height: 1.5; }
    .method-result-panel--embedding .analysis-result h3 { color: #1967d2; }
    .method-result-panel--reranker .analysis-result h3 { color: #7b1fa2; }
    .reranker-result .decision-badge { margin-left: 6px; vertical-align: middle; }
    .embedding-rank-row { display: grid; grid-template-columns: 28px minmax(90px, 1fr) minmax(100px, 2fr) 50px; align-items: center; gap: 8px; margin: 8px 0; }
    .embedding-progress { overflow: hidden; height: 9px; border-radius: 999px; background: #dce8fb; }
    .embedding-progress > span { display: block; height: 100%; border-radius: inherit; background: #4285f4; }
    #method-results-row { flex-wrap: nowrap !important; gap: 14px !important; align-items: stretch !important; }
    #method-results-row > * { min-width: 0 !important; }
    .method-result-panel { padding: 14px !important; border-radius: 14px !important; }
    .method-result-panel--embedding { border: 1px solid #8ab4f8 !important; background: #eef6ff !important; }
    .method-result-panel--reranker { border: 1px solid #c58af9 !important; background: #fbf3ff !important; }
    .method-result-card { width: 100%; }
    .method-result-heading { margin: 0 0 4px !important; font-size: 1.02rem !important; font-weight: 700 !important; }
    .method-result-heading--embedding { color: #1967d2 !important; }
    .method-result-heading--reranker { color: #7b1fa2 !important; }
    .method-result-caption { margin: 0 0 12px !important; color: #5f6368 !important; font-size: .84rem !important; }
    .reranker-summary { padding: 0; background: transparent; }
    @media (max-width: 760px) {
      #decision-main-row { flex-wrap: wrap !important; }
      #method-results-row { flex-wrap: wrap !important; }
      .decision-metrics { grid-template-columns: 1fr; }
      .decision-rank-row { grid-template-columns: 24px minmax(75px, 1fr) minmax(72px, 1fr) 44px; gap: 5px; }
    }
    """

    def decide(customer_behavior: str, min_margin: float, min_score: float) -> dict[str, Any]:
        if not customer_behavior.strip():
            return {"error": "고객 행동을 입력하세요."}
        try:
            if embedding_comparison_runner is not None:
                compared = embedding_comparison_runner(
                    customer_behavior, load_settings(), top_k=len(candidates),
                    min_margin=float(min_margin), min_score=float(min_score),
                )
                return {
                    **compared["reranker"],
                    "embedding": compared["embedding"],
                    "comparison_rows": compared["comparison_rows"],
                }
            return decision_runner(
                case_text=customer_behavior,
                settings=load_settings(),
                min_margin=float(min_margin),
                min_score=float(min_score),
            )
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}

    def render_outcome(outcome: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        if "error" in outcome:
            message = escape(str(outcome["error"]))
            return (
                (
                    '<section class="method-result-card"><p class="method-result-heading method-result-heading--reranker">Reranker 재정렬</p>'
                    '<p class="method-result-caption">후보 문서와 원문을 함께 읽은 관련도 순위</p>'
                    f'<section class="decision-result error"><p class="decision-result-kicker">호출 실패</p><h2 class="decision-result-title">추천을 생성하지 못했습니다</h2><p>{message}</p></section></section>'
                ),
                "",
                outcome,
            )

        ranked = list(outcome.get("ranked_candidates", []))
        top = ranked[0] if ranked else {}
        recommendation = str(outcome.get("recommendation", ""))
        requires_review = bool(outcome.get("requires_human_review"))
        theme = "review" if requires_review else recommendation
        if theme not in {"approve", "decline", "review"}:
            theme = "review"
        recommendation_label = escape(str(outcome.get("recommendation_label", recommendation)))
        review_label = "사람 검토 필요" if requires_review else "자동 추천 가능"
        try:
            top_score = float(top.get("score", 0))
            margin = float(outcome.get("margin", 0))
        except (TypeError, ValueError):
            top_score, margin = 0.0, 0.0
        reason = escape(str(outcome.get("reason", "판단 근거가 없습니다."))).replace("\n", "<br>")
        result_html = f"""
        <section class="analysis-result reranker-result">
          <h3>재정렬 결과</h3>
          <p><b>추천 정책: {recommendation_label}</b><span class="decision-badge {theme}">{review_label}</span><br>{reason}</p>
          <div class="decision-metrics">
            <div class="decision-metric"><span>최고 관련도 점수</span><strong>{top_score:.3f}</strong></div>
            <div class="decision-metric"><span>1·2위 점수 차이 (margin)</span><strong>{margin:.3f}</strong></div>
          </div>
        </section>
        """
        ranking_rows = []
        for item in ranked:
            try:
                score = float(item.get("score", 0))
            except (TypeError, ValueError):
                score = 0.0
            width = min(100, max(0, score * 100))
            rank = escape(str(item.get("rank", "-")))
            label = escape(str(item.get("label", item.get("id", "후보"))))
            ranking_rows.append(
                f'<div class="decision-rank-row"><span>{rank}</span><span class="decision-rank-label">{label}</span><span class="decision-progress"><span style="width: {width:.1f}%"></span></span><strong class="decision-rank-score">{score:.3f}</strong></div>'
            )
        ranking_html = "".join(ranking_rows)
        embedding = outcome.get("embedding")
        embedding_html = (
            '<section class="method-result-card"><p class="method-result-heading method-result-heading--embedding">Embedding 검색</p>'
            '<p class="method-result-caption">각 정책 원형과의 벡터 유사도 순위</p>'
            '<section class="decision-result-empty">실행하면 검색 순위와 유사도 점수를 표시합니다.</section></section>'
        )
        if isinstance(embedding, dict):
            embedding_ranked = list(embedding.get("ranked_candidates", []))
            try:
                embedding_top_score = float(embedding_ranked[0].get("score", 0)) if embedding_ranked else 0.0
            except (AttributeError, TypeError, ValueError):
                embedding_top_score = 0.0
            rows = []
            for item in embedding_ranked:
                try:
                    score = float(item.get("score", 0))
                except (TypeError, ValueError):
                    score = 0.0
                rows.append(
                    f'<div class="embedding-rank-row"><span>{escape(str(item.get("rank", "-")))}</span>'
                    f'<span class="decision-rank-label">{escape(str(item.get("label", item.get("id", "후보"))))}</span>'
                    f'<span class="embedding-progress"><span style="width: {min(100, max(0, score * 100)):.1f}%"></span></span>'
                    f'<strong class="decision-rank-score">{score:.3f}</strong></div>'
                )
            embedding_html = (
                '<section class="method-result-card"><p class="method-result-heading method-result-heading--embedding">Embedding 검색</p>'
                '<p class="method-result-caption">각 정책 원형과의 벡터 유사도 순위</p>'
                '<section class="analysis-result"><h3>검색 결과</h3>'
                '<p>정책 원형을 각각 벡터화해 유사도로 순위를 정합니다. 이 순위는 Reranker 관련도 점수와 절대값을 비교하지 않습니다.</p>'
                '<div class="decision-metrics">'
                f'<div class="decision-metric"><span>최고 유사도 점수</span><strong>{embedding_top_score:.3f}</strong></div>'
                f'<div class="decision-metric"><span>비교한 정책 원형</span><strong>{len(embedding_ranked)}개</strong></div>'
                '</div>'
                + "".join(rows) + "</section></section>"
            )
        reranker_html = (
            '<section class="method-result-card"><p class="method-result-heading method-result-heading--reranker">Reranker 재정렬</p>'
            '<p class="method-result-caption">후보 문서와 원문을 함께 읽은 관련도 순위</p>'
            + result_html + ranking_html + "</section>"
        )
        return reranker_html, embedding_html, outcome

    def decide_and_render(
        customer_behavior: str, min_margin: float, min_score: float,
    ) -> tuple[str, str, dict[str, Any]]:
        return render_outcome(decide(customer_behavior, min_margin, min_score))

    with gr.Blocks(css=modal_css, fill_width=True) as app:
        with gr.Row(equal_height=True):
            with gr.Column(scale=9):
                gr.Markdown(
                    "# Reranker Decision Playground\n"
                    "사례와 정책 후보를 비교해 추천을 만듭니다. 실제 업무 상태는 변경하지 않습니다."
                )
            with gr.Column(scale=1, min_width=90):
                open_settings = gr.Button("⚙️ 설정", size="sm")
        with gr.Row(equal_height=False, elem_id="decision-main-row"):
            with gr.Column(scale=5, min_width=320, elem_classes=["decision-panel"]):
                gr.Markdown("### ① 고객 행동\n주문 흐름과 인증·결제·한도 관련 사실을 입력하세요.")
                customer_behavior = gr.Textbox(
                    label="고객 행동",
                    value=default_behavior,
                    lines=7,
                    placeholder="예: 1분 동안 3회 주문을 시도했고, 인증 실패는 없었습니다.",
                )
                run = gr.Button("추천 생성", variant="primary")
                with gr.Accordion(f"예시 시나리오 ({len(example_scenarios)}개)", open=False, elem_id="decision-example-card"):
                    gr.Markdown("예시를 선택하면 고객 행동 입력란에 적용됩니다.")
                    for row_start in range(0, len(example_scenarios), 2):
                        with gr.Row():
                            for label, scenario in example_scenarios[row_start:row_start + 2]:
                                example = gr.Button(
                                    label,
                                    variant="secondary",
                                    size="sm",
                                    elem_classes=["decision-example-button"],
                                )
                                example.click(
                                    lambda value=scenario: value,
                                    outputs=customer_behavior,
                                )
                with gr.Accordion("정책 후보 보기", open=False):
                    gr.Markdown(candidate_summary)
            with gr.Column(scale=7, min_width=380, elem_classes=["decision-panel"]):
                gr.Markdown("### ② 분석 결과")
                with gr.Row(equal_height=True, elem_id="method-results-row"):
                    with gr.Column(scale=1, elem_classes=["method-result-panel", "method-result-panel--embedding"]):
                        embedding_overview = gr.HTML(
                            value=(
                                '<section class="method-result-card"><p class="method-result-heading method-result-heading--embedding">Embedding 검색</p>'
                                '<p class="method-result-caption">각 정책 원형과의 벡터 유사도 순위</p>'
                                '<section class="decision-result-empty">실행하면 검색 순위와 유사도 점수를 표시합니다.</section></section>'
                            ),
                        )
                    with gr.Column(scale=1, elem_classes=["method-result-panel", "method-result-panel--reranker"]):
                        result_overview = gr.HTML(
                            value=(
                                '<section class="method-result-card"><p class="method-result-heading method-result-heading--reranker">Reranker 재정렬</p>'
                                '<p class="method-result-caption">후보 문서와 원문을 함께 읽은 관련도 순위</p>'
                                '<section class="decision-result-empty">실행하면 추천·관련도 점수·순위를 표시합니다.</section></section>'
                            ),
                        )
                with gr.Accordion("상세 응답 (JSON)", open=False):
                    output = gr.JSON(label="원본 응답", min_height=220)
        with gr.Column(visible=False, elem_id="decision-settings-modal") as settings_modal:
            gr.Markdown("### Reranker 설정")
            gr.Markdown("### 사람 검토 게이트")
            with gr.Row():
                min_margin = gr.Slider(
                    minimum=0,
                    maximum=1,
                    value=default_min_margin,
                    step=0.005,
                    label="최소 margin",
                    info="1·2위 score 차이가 이 값보다 작으면 manual-review입니다.",
                )
                min_score = gr.Slider(
                    minimum=0,
                    maximum=1,
                    value=default_min_score,
                    step=0.01,
                    label="최소 score",
                    info="최고 score가 이 값보다 작으면 manual-review입니다.",
                )
            close_settings = gr.Button("닫기")
        open_settings.click(lambda: gr.update(visible=True), outputs=settings_modal)
        close_settings.click(lambda: gr.update(visible=False), outputs=settings_modal)
        run.click(
            decide_and_render,
            inputs=[customer_behavior, min_margin, min_score],
            outputs=[result_overview, embedding_overview, output],
        )
    return app
