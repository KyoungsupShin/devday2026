"""Gradio presentation adapter for the 02 agent loop/MCP lab.

The app deliberately reuses notebook 01's workflow chat, status timeline, and
streaming Agent cards. It only expands selected Tool Calling evidence.
"""
from __future__ import annotations

import gradio as gr

from lab_common.config import Settings
from ..agent_workflow.ui import build_workflow_ui


DEFAULT_LOOP_REQUEST = (
    "편의점용 고단백 닭가슴살 도시락의 마케팅 출시안을 만들어주세요. 제품명은 “프로틴 런치”, "
    "타깃은 운동을 즐기는 20~30대 직장인입니다. 핵심 메시지·프로모션 문구·판매 채널을 "
    "제안하고, 마지막에는 이 내용을 바탕으로 생성 이미지가 포함된 한 장짜리 프로모션 HTML 시안도 만들어주세요. "
    "영양·건강 관련 표현은 검토가 필요한 가정임을 표시해주세요."
)


def build_loop_ui(settings: Settings | None = None) -> gr.Blocks:
    """Build the same orchestrated graph UI, with Tool Calling audit details enabled."""
    return build_workflow_ui(
        settings,
        title="LLM-Orchestrated Agent Workflow · Tool Calling",
        show_tool_calling=True,
        default_request=DEFAULT_LOOP_REQUEST,
    )


def launch_loop_ui() -> gr.Blocks:
    """Build and launch the notebook-local Tool Calling UI."""
    app = build_loop_ui()
    app.launch(inline=True, share=False, show_error=True, server_name="127.0.0.1", height=900)
    return app
