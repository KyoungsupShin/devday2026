"""Local Gradio adapter for browsing and invoking registered orchestrations."""
from __future__ import annotations

from typing import Any

import gradio as gr

from lab_common.config import load_settings
from .lab_core import (
    get_orchestration_config,
    invoke_saved_orchestration_config,
    list_orchestration_configs,
)


def build_orchestration_registry_ui() -> gr.Blocks:
    """Build a read-only registry browser; invocation uses the selected config ID."""
    settings = load_settings()

    def refresh() -> tuple[dict[str, Any], gr.Dropdown]:
        result = list_orchestration_configs(settings=settings)
        resources = result["resources"]
        choices = [
            (
                f"{item.get('scenario', '')} / {item.get('name', '')} / "
                f"{item.get('version', '')} — {item.get('id', '')}",
                item.get("id", ""),
            )
            for item in resources
            if item.get("id")
        ]
        return result, gr.Dropdown(choices=choices, value=choices[0][1] if choices else None)

    def load(config_id: str) -> dict[str, Any]:
        return get_orchestration_config(config_id, settings=settings)

    def invoke(config_id: str, query: str) -> tuple[str, dict[str, str]]:
        result = invoke_saved_orchestration_config(query, settings, config_id=config_id)
        return result["answer"], result

    with gr.Blocks(title="BTP Orchestration Registry") as app:
        with gr.Sidebar(open=True, width=340, position="left"):
            gr.Markdown("## Orchestration 선택")
            gr.Markdown("Prompt Registry에 등록된 Orchestration을 선택합니다.")
            refresh_button = gr.Button("등록된 Orchestration 새로고침", variant="primary")
            config_id = gr.Dropdown(label="Orchestration 선택", choices=[], interactive=True)
            load_button = gr.Button("Orchestration 불러오기")
            with gr.Accordion("조회 결과", open=False):
                listed_configs = gr.JSON(label="등록된 Orchestration 목록")

        gr.Markdown(
            "# BTP Orchestration Registry\n"
            "사이드바에서 등록된 Orchestration을 선택한 뒤 상세를 확인하거나 호출합니다. 이 화면은 Registry를 변경하지 않습니다."
        )
        with gr.Accordion("선택한 Orchestration 상세·호출", open=True):
            invoke_button = gr.Button("선택한 Orchestration 호출", variant="primary", size="sm")
            query = gr.Textbox(label="질문", value="Orchestration Service를 한 문장으로 설명해 주세요.", lines=3)
            answer = gr.Textbox(label="응답", lines=8)
            invoke_result = gr.JSON(label="호출 결과")
            loaded_config = gr.JSON(label="선택한 Orchestration 상세")

        refresh_button.click(refresh, outputs=[listed_configs, config_id])
        load_button.click(load, inputs=config_id, outputs=loaded_config)
        invoke_button.click(invoke, inputs=[config_id, query], outputs=[answer, invoke_result])
    return app
