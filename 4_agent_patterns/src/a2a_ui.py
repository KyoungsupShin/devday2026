"""Thin local Gradio adapter for the public Food A2A handoff core API."""
from __future__ import annotations

import html

import gradio as gr

from lab_common.config import Settings, load_settings

from .a2a import run_food_handoff

DEFAULT_FOOD_REQUEST = (
    "편의점용 고단백 닭가슴살 도시락을 출시하려고 합니다. 판매가 4,500원, 단백질 30g 이상, "
    "전자레인지 조리 가능 조건으로 출시 준비에 필요한 검토 항목을 정리해주세요."
)


def build_a2a_ui(settings: Settings | None = None) -> gr.Blocks:
    """Build the UI; its callback delegates all work to ``run_food_handoff``."""
    settings = settings or load_settings()
    settings.require_ai_core()

    def a2a_chat(message: str, history: list[dict]):
        history = list(history or [])
        if not message or not message.strip():
            return "", history + [{"role": "assistant", "content": "<div style='color:#b3261e'>요청을 입력하세요.</div>"}], None
        try:
            outcome = run_food_handoff(message, settings)
        except Exception as error:
            return "", history + [{"role": "user", "content": message}, {"role": "assistant", "content": f'<div style="color:#b3261e">{html.escape(str(error))}</div>'}], None
        recommendation = outcome["report"]["payload"]["recommendation"]
        return "", history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": recommendation},
        ], {"handoff": outcome["handoff"], "report": outcome["report"], "trace": outcome["trace"], "execution_boundary": outcome["execution_boundary"]}

    with gr.Blocks() as app:
        gr.Markdown("## Food Agent-to-Agent Handoff")
        gr.Markdown("Food Researcher가 근거 브리프를 작성해 Launch Advisor에게 명시적으로 전달합니다. 두 Agent 모두 AI Core LLM만 사용하며 외부 쓰기를 수행하지 않습니다.")
        chatbot = gr.Chatbot(type="messages", label="A2A conversation", height=800)
        message = gr.Textbox(label="Message", value=DEFAULT_FOOD_REQUEST, info="Enter를 눌러 전송하세요.")
        artifact = gr.JSON(label="A2A handoff artifact and trace")
        message.submit(a2a_chat, inputs=[message, chatbot], outputs=[message, chatbot, artifact])
    return app


def launch_a2a_ui() -> gr.Blocks:
    app = build_a2a_ui()
    app.launch(inline=True, share=False, show_error=True, server_name="127.0.0.1", height=900)
    return app
