"""Gradio views specific to the Gen AI Hub LLM notebooks.

The functions create UI blocks but never launch a public share link.  A notebook
explicitly calls ``launch(inline=True)`` when the learner is ready.
"""
from __future__ import annotations

import os
from html import escape
from collections.abc import Iterator
from typing import Any, Callable

from lab_common.config import load_settings


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
):
    """Create a compact chat UI, streaming tokens when a streamer is provided."""
    gr = _gradio()

    def reply(message: str, history: list[Any], chat_config: dict[str, str]) -> Iterator[str]:
        if not message.strip():
            yield "질문을 입력하세요."
            return
        settings = load_settings()
        selected_model = chat_config.get("model_name", "").strip() or settings.llm_model
        system_prompt = chat_config.get("system_prompt", "")
        try:
            if chat_stream_runner is not None:
                accumulated = ""
                for delta in chat_stream_runner(
                    message=message,
                    settings=settings,
                    history=_history_messages(history),
                    system_prompt=system_prompt,
                    model=selected_model,
                ):
                    accumulated += delta
                    yield accumulated
                return
            outcome = chat_runner(
                message=message,
                settings=settings,
                history=_history_messages(history),
                system_prompt=system_prompt,
                model=selected_model,
            )
            yield outcome["reply"]
        except Exception as error:
            yield f"호출 실패: {type(error).__name__}: {error}"

    settings = load_settings()
    modal_css = """
    #chat-settings-modal {
      position: fixed !important; inset: 12vh 18vw auto !important; z-index: 1000 !important;
      max-width: 760px !important; padding: 20px !important; border: 1px solid #d0d7de !important;
      border-radius: 14px !important; background: white !important; box-shadow: 0 18px 60px rgba(0,0,0,.22) !important;
    }
    """
    with gr.Blocks(css=modal_css, fill_width=True) as app:
        gr.Markdown(
            "# LLM Chatbot UI\n"
            "대화 내용은 현재 Jupyter session의 브라우저 UI에만 유지됩니다. prompt와 모델은 ⚙️ 설정에서 바꿀 수 있습니다."
        )
        chat_config = gr.State({
            "system_prompt": "너는 친절한 교육 보조자다. 한국어로 간결하게 답한다.",
            "model_name": settings.llm_model,
        })
        with gr.Row():
            gr.Markdown("질문을 입력해 대화를 시작하세요.")
            open_settings = gr.Button("⚙️ 설정", size="sm")
        gr.ChatInterface(fn=reply, additional_inputs=[chat_config], type="messages")
        with gr.Column(visible=False, elem_id="chat-settings-modal") as settings_modal:
            gr.Markdown("### 채팅 설정")
            system_prompt = gr.Textbox(
                label="System prompt",
                value="너는 친절한 교육 보조자다. 한국어로 간결하게 답한다.",
                lines=4,
            )
            model_name = gr.Textbox(label="Model (blank uses LLM_MODEL)", value=settings.llm_model)
            with gr.Row():
                save_settings_button = gr.Button("적용", variant="primary")
                close_settings = gr.Button("닫기")

        open_settings.click(lambda: gr.update(visible=True), outputs=settings_modal)
        close_settings.click(lambda: gr.update(visible=False), outputs=settings_modal)
        save_settings_button.click(
            lambda prompt, model: ({"system_prompt": prompt, "model_name": model}, gr.update(visible=False)),
            inputs=[system_prompt, model_name],
            outputs=[chat_config, settings_modal],
        )
    return app


def build_embedding_ui(embedding_runner: Callable[..., dict[str, Any]]):
    """Create an embedding comparison view backed by one public core API."""
    gr = _gradio()
    load_settings()  # Loads the repository .env before reading EMBED_MODEL for the view.
    configured_model = os.getenv("EMBED_MODEL", "amazon--titan-embed-image")

    def compare(text_a: str, text_b: str) -> dict[str, Any]:
        if not text_a.strip() or not text_b.strip():
            return {"error": "비교할 두 텍스트를 모두 입력하세요."}
        try:
            return embedding_runner(
                texts=[text_a, text_b],
                settings=load_settings(),
                model=None,
            )
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}

    layout_css = """
    #embedding-comparison-row { flex-wrap: nowrap !important; gap: 16px !important; }
    #embedding-comparison-row > * { min-width: 0 !important; }
    """
    with gr.Blocks(css=layout_css, fill_width=True) as app:
        gr.Markdown(
            "# Embedding Similarity UI\n"
            "두 텍스트를 임베딩해 cosine similarity를 비교합니다. 결과 조회만 수행하며 외부 업무 상태를 변경하지 않습니다."
        )
        gr.Markdown(f"Embedding model: `{configured_model}` (`.env`의 `EMBED_MODEL`)")
        with gr.Row(equal_height=True, elem_id="embedding-comparison-row"):
            with gr.Column(scale=1, min_width=0):
                first = gr.Textbox(label="Text A", value="apple")
                second = gr.Textbox(label="Text B", value="orange")
                run = gr.Button("Compare", variant="primary")
            with gr.Column(scale=1, min_width=0):
                output = gr.JSON(label="Result", min_height=260)
        run.click(compare, inputs=[first, second], outputs=output)
    return app


def build_image_labeling_ui(image_labeler: Callable[..., dict[str, Any]]):
    """Create a one-image, candidate-label classification view."""
    gr = _gradio()
    load_settings()
    configured_model = os.getenv("EMBED_MODEL", "amazon--titan-embed-image")

    def label(image: str | None, candidate_labels: str) -> dict[str, Any]:
        labels = [
            value.strip()
            for value in candidate_labels.replace(",", "\n").splitlines()
            if value.strip()
        ]
        if not image:
            return {"error": "라벨링할 이미지 한 장을 선택하세요."}
        if not labels:
            return {"error": "후보 라벨을 하나 이상 입력하세요."}
        try:
            return image_labeler(
                image_path=image, labels=labels, settings=load_settings(), model=None
            )
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}

    with gr.Blocks(fill_width=True) as app:
        gr.Markdown(
            "# Image Labeling UI\n"
            "이미지 한 장을 후보 라벨의 텍스트 embedding과 비교해 가장 가까운 라벨을 반환합니다. 이미지 파일은 embedding 요청에만 사용하며 외부에 저장하지 않습니다."
        )
        gr.Markdown(f"Embedding model: `{configured_model}` (`.env`의 `EMBED_MODEL`)")
        image = gr.Image(label="Image", type="filepath")
        candidate_labels = gr.Textbox(
            label="Candidate labels (comma or newline separated)",
            value="food, document, person, landscape",
            lines=3,
        )
        run = gr.Button("Label image", variant="primary")
        output = gr.JSON(label="Result")
        run.click(label, inputs=[image, candidate_labels], outputs=output)
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
    .business-routing { max-width: 820px; margin: 0 auto; color: #1f2937; }
    .routing-header { margin: 4px 0 24px; }
    .routing-header h1 { margin: 0 0 5px; font-size: 1.5rem; letter-spacing: -.035em; }
    .routing-header p { margin: 0; color: #6b7280; font-size: .94rem; }
    .routing-input { padding: 24px; border: 1px solid #e5e7eb; border-radius: 16px; background: #fff; box-shadow: 0 6px 24px rgba(31,41,55,.04); }
    .example-label { margin: 18px 0 8px; color: #6b7280; font-size: .82rem; font-weight: 650; }
    #example-row { gap: 8px !important; }
    #routing-actions { margin-top: 18px; align-items: center; }
    #routing-actions > *:first-child { flex-grow: 1 !important; }
    #routing-result { margin-top: 28px; }
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
    @media (max-width: 760px) {
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
            with gr.Column(elem_classes="routing-input"):
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
            with gr.Column(visible=False, elem_id="routing-result") as result_area:
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
    default_policy_document: str,
    candidates: list[dict[str, str]],
    default_min_margin: float = 0.12,
    default_min_score: float = 0.45,
):
    """Create a read-only decision view backed by one public core API."""
    gr = _gradio()
    default_behavior = "인증된 고객이 주문 간격 60초 이상을 지키며 1분에 1회 주문을 시도했다. 중복, 실패, 한도 초과는 없다."
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
    #decision-main-row { flex-wrap: nowrap !important; gap: 16px !important; }
    #decision-main-row > * { min-width: 0 !important; }
    """

    def decide(
        customer_behavior: str, policy_document: str, min_margin: float, min_score: float,
    ) -> dict[str, Any]:
        if not customer_behavior.strip():
            return {"error": "고객 행동을 입력하세요."}
        if not policy_document.strip():
            return {"error": "정책 document를 입력하세요."}
        try:
            return decision_runner(
                case_text=customer_behavior,
                settings=load_settings(),
                policy_document=policy_document,
                min_margin=float(min_margin),
                min_score=float(min_score),
            )
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}

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
            with gr.Column(scale=1, min_width=0):
                customer_behavior = gr.Textbox(label="고객 행동", value=default_behavior, lines=5)
                run = gr.Button("추천 생성", variant="primary")
                gr.Markdown("### 정책 후보\n" + candidate_summary)
            with gr.Column(scale=1, min_width=0):
                output = gr.JSON(label="추천 결과", min_height=360)
        with gr.Column(visible=False, elem_id="decision-settings-modal") as settings_modal:
            gr.Markdown("### Reranker 설정")
            policy_document = gr.Textbox(
                label="정책 문서",
                value=default_policy_document,
                lines=11,
            )
            gr.Markdown("### 사람 검토 게이트")
            with gr.Row():
                min_margin = gr.Slider(
                    minimum=0,
                    maximum=1,
                    value=default_min_margin,
                    step=0.01,
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
            decide,
            inputs=[customer_behavior, policy_document, min_margin, min_score],
            outputs=output,
        )
    return app
