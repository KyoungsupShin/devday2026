"""Local Gradio adapter for the 01 Prompt Registry lab."""
from __future__ import annotations

from typing import Any

import gradio as gr

from lab_common.config import load_settings
from .lab_core import (
    delete_orchestration_config,
    get_orchestration_config,
    invoke_saved_orchestration_config,
    preview_saved_orchestration_spec,
    save_orchestration_config,
)


def build_orchestration_registry_ui() -> gr.Blocks:
    """Build the local UI; BTP operations delegate to public core APIs."""

    def preview(system_prompt: str, user_prompt: str, model: str, max_tokens: int) -> dict[str, Any]:
        return preview_saved_orchestration_spec(
            load_settings(), system_prompt=system_prompt, user_prompt=user_prompt,
            model=model or None, max_tokens=int(max_tokens),
        )

    def save(
        name: str, version: str, scenario: str, system_prompt: str, user_prompt: str, model: str, max_tokens: int
    ) -> tuple[dict[str, Any], str]:
        result = save_orchestration_config(
            load_settings(), name=name, version=version, scenario=scenario, system_prompt=system_prompt,
            user_prompt=user_prompt, model=model or None, max_tokens=int(max_tokens),
        )
        return result, result["id"]

    def load(config_id: str) -> dict[str, Any]:
        return get_orchestration_config(config_id)

    def invoke(config_id: str, query: str) -> tuple[str, dict[str, str]]:
        result = invoke_saved_orchestration_config(query, load_settings(), config_id=config_id)
        return result["answer"], result

    def delete(config_id: str, confirmation: str) -> dict[str, Any]:
        if confirmation.strip() != "DELETE":
            raise ValueError("삭제하려면 확인 입력란에 DELETE를 정확히 입력하세요.")
        return delete_orchestration_config(config_id)

    with gr.Blocks(title="BTP Orchestration Config Registry") as app:
        gr.Markdown(
            "### BTP Orchestration Config 관리\n"
            "저장과 삭제는 Prompt Registry의 실제 BTP 리소스를 변경합니다. Invoke는 저장된 Config ID를 참조합니다."
        )
        with gr.Row():
            with gr.Column(scale=1):
                scenario = gr.Textbox(label="Scenario", value="devday")
                name = gr.Textbox(label="Config name", value="assistant")
                version = gr.Textbox(label="Version", value="1.0.0")
                model = gr.Textbox(label="Model (비우면 .env LLM_MODEL)")
                max_tokens = gr.Slider(label="Max tokens", minimum=1, maximum=4000, value=700, step=1)
            with gr.Column(scale=2):
                system_prompt = gr.Textbox(label="System prompt", value="You are a concise, helpful assistant.", lines=5)
                user_prompt = gr.Textbox(label="User prompt template", value="{{?user_query}}", lines=3)
                with gr.Row():
                    preview_button = gr.Button("구성 미리보기")
                    save_button = gr.Button("BTP에 저장 / 같은 버전 수정", variant="primary")
                save_result = gr.JSON(label="저장 결과")

        with gr.Accordion("저장된 Config 조회·호출·삭제", open=False):
            config_id = gr.Textbox(label="Config ID", placeholder="저장 결과 또는 Prompt Registry의 ID")
            with gr.Row():
                load_button = gr.Button("Config 불러오기")
                invoke_button = gr.Button("저장된 Config 호출", variant="primary")
            query = gr.Textbox(label="질문", value="Orchestration Service를 한 문장으로 설명해 주세요.", lines=3)
            answer = gr.Textbox(label="응답", lines=8)
            invoke_result = gr.JSON(label="호출 결과")
            loaded_config = gr.JSON(label="Config 상세")
            gr.Markdown("삭제는 되돌릴 수 없습니다. 아래에 **DELETE**를 정확히 입력한 뒤 실행하세요.")
            with gr.Row():
                delete_confirmation = gr.Textbox(label="삭제 확인", placeholder="DELETE")
                delete_button = gr.Button("Config 영구 삭제", variant="stop")
            delete_result = gr.JSON(label="삭제 결과")

        preview_button.click(preview, inputs=[system_prompt, user_prompt, model, max_tokens], outputs=save_result)
        save_button.click(save, inputs=[name, version, scenario, system_prompt, user_prompt, model, max_tokens], outputs=[save_result, config_id])
        load_button.click(load, inputs=config_id, outputs=loaded_config)
        invoke_button.click(invoke, inputs=[config_id, query], outputs=[answer, invoke_result])
        delete_button.click(delete, inputs=[config_id, delete_confirmation], outputs=delete_result)
    return app
