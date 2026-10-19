"""Reusable Gradio views for the Jupyter hands-on notebooks.

The functions create UI blocks but never launch a public share link.  A notebook
explicitly calls ``launch(inline=True)`` when the learner is ready.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable

from .ai_core import list_running_deployments
from .config import REPOSITORY_ROOT, Settings, load_settings


ENV_PATH = REPOSITORY_ROOT / ".env"


def _gradio():
    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError("Gradio가 없습니다. python3 -m pip install --user -r requirements.txt 를 실행하세요.") from error
    return gr


def _masked(value: str) -> str:
    return "configured" if value else "missing"


def settings_summary(settings: Settings | None = None) -> str:
    settings = settings or load_settings()
    return (
        f"AI Core URL: {'configured' if settings.base_url else 'missing'}\n"
        f"Auth URL: {'configured' if settings.auth_url else 'missing'}\n"
        f"Client ID: {_masked(settings.client_id)}\n"
        f"Client secret: {_masked(settings.client_secret)}\n"
        f"Resource group: {settings.resource_group}\n"
        f"LLM model: {settings.llm_model}\n"
        f"Embedding model: {os.getenv('EMBED_MODEL', 'not set')}"
    )


def _write_env(updates: dict[str, str]) -> None:
    """Update only supplied values, preserving comments and unrelated configuration."""
    original = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    lines = original.splitlines()
    remaining = dict(updates)
    rewritten: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in remaining:
            rewritten.append(f"{key}={remaining.pop(key)}")
        else:
            rewritten.append(line)
    if remaining:
        if rewritten and rewritten[-1]:
            rewritten.append("")
        rewritten.extend(f"{key}={value}" for key, value in remaining.items())
    ENV_PATH.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def save_settings(
    base_url: str, auth_url: str, client_id: str, client_secret: str,
    resource_group: str, llm_model: str, embed_model: str,
) -> str:
    """Persist nonblank form fields and make them active in this kernel."""
    fields = {
        "AICORE_BASE_URL": base_url.strip(),
        "AICORE_AUTH_URL": auth_url.strip(),
        "AICORE_CLIENT_ID": client_id.strip(),
        "AICORE_CLIENT_SECRET": client_secret.strip(),
        "AICORE_RESOURCE_GROUP": resource_group.strip(),
        "LLM_MODEL": llm_model.strip(),
        "EMBED_MODEL": embed_model.strip(),
    }
    updates = {key: value for key, value in fields.items() if value}
    if not updates:
        return "저장할 값이 없습니다. 빈 입력은 기존 .env 값을 유지합니다."
    _write_env(updates)
    os.environ.update(updates)
    return "저장했습니다. 비밀값은 표시하지 않습니다.\n\n" + settings_summary(load_settings())


def deployment_summary() -> str:
    try:
        deployments = list_running_deployments(load_settings())
    except Exception as error:
        return f"연결 확인 실패: {type(error).__name__}: {error}"
    if not deployments:
        return "RUNNING deployment가 없습니다."
    return "\n".join(
        f"- {item.get('scenarioId', 'unknown')} | {item.get('status')} | {item.get('deploymentUrl', '')}"
        for item in deployments
    )


def build_configuration_ui():
    """Create a local-only AI Core configuration and deployment-check UI."""
    gr = _gradio()
    current = load_settings()
    with gr.Blocks(fill_width=True) as app:
        gr.Markdown(
            "### AI Core 설정 UI\n"
            "빈 입력은 기존 `.env` 값을 유지합니다. client secret은 화면에 다시 표시하지 않습니다."
        )
        with gr.Row():
            with gr.Column():
                base_url = gr.Textbox(label="AI Core base URL", value=current.base_url)
                auth_url = gr.Textbox(label="Auth URL", value=current.auth_url)
                client_id = gr.Textbox(label="Client ID", value=current.client_id)
                client_secret = gr.Textbox(label="Client secret (blank keeps existing)", type="password")
            with gr.Column():
                resource_group = gr.Textbox(label="Resource group", value=current.resource_group)
                llm_model = gr.Textbox(label="LLM model", value=current.llm_model)
                embed_model = gr.Textbox(label="Embedding model", value=os.getenv("EMBED_MODEL", ""))
                save = gr.Button("Save local settings", variant="primary")
                check = gr.Button("Check RUNNING deployments")
        status = gr.Textbox(label="Configuration status", value=settings_summary(current), lines=8)
        deployments = gr.Textbox(label="Deployment status", lines=8)
        save.click(
            save_settings,
            inputs=[base_url, auth_url, client_id, client_secret, resource_group, llm_model, embed_model],
            outputs=status,
        )
        check.click(deployment_summary, outputs=deployments)
    return app


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
    configured_model = os.getenv("EMBED_MODEL", "text-embedding-3-small")

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


def build_business_embedding_ui(
    lab_runner: Callable[..., dict[str, Any]],
    cases: list[dict[str, str]],
    n_clusters: int = 4,
):
    """Create a read-only business-routing view backed by one public core API."""
    gr = _gradio()
    load_settings()  # Loads the repository .env before reading EMBED_MODEL for the view.
    configured_model = os.getenv("EMBED_MODEL", "text-embedding-3-small")

    def recommend(ticket: str) -> dict[str, Any]:
        if not ticket.strip():
            return {"error": "새 업무 문의를 입력하세요."}
        try:
            return lab_runner(
                ticket=ticket,
                cases=cases,
                settings=load_settings(),
                n_clusters=n_clusters,
            )
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}

    layout_css = """
    #business-embedding-row { flex-wrap: nowrap !important; gap: 16px !important; }
    #business-embedding-row > * { min-width: 0 !important; }
    """
    with gr.Blocks(css=layout_css, fill_width=True) as app:
        gr.Markdown(
            "# Business Embedding Routing UI\n"
            "합성 사례로 cluster·holdout 평가·추천 큐 근거를 확인합니다. 추천만 생성하며 외부 업무 큐나 상태를 변경하지 않습니다."
        )
        gr.Markdown(
            f"Embedding model: {configured_model} (.env의 EMBED_MODEL) · "
            f"학습용 사례: {len(cases)}건 · cluster 가설: {n_clusters}개"
        )
        with gr.Row(equal_height=True, elem_id="business-embedding-row"):
            with gr.Column(scale=1, min_width=0):
                ticket = gr.Textbox(
                    label="새 업무 문의",
                    value="운송장에는 배송 완료로 나오지만 고객이 물건을 받지 못했습니다.",
                    lines=5,
                )
                run = gr.Button("분석 및 추천", variant="primary")
                gr.Markdown("낮은 유사도·작은 margin·신규 업무 유형은 운영에서 사람 검토로 보내세요.")
            with gr.Column(scale=1, min_width=0):
                output = gr.JSON(label="분석 결과", min_height=440)
        run.click(recommend, inputs=ticket, outputs=output)
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
