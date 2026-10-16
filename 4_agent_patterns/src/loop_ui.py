"""Thin Tool-Calling presentation adapter for notebook 02.

The app deliberately reuses notebook 01's workflow chat, status timeline, and
streaming Agent cards. It only expands selected Tool Calling evidence.
"""
from __future__ import annotations

import gradio as gr

from lab_common.config import Settings
from .workflow_ui import build_workflow_ui


def build_loop_ui(settings: Settings | None = None) -> gr.Blocks:
    """Build the same fixed graph UI, with Tool Calling audit details enabled."""
    return build_workflow_ui(
        settings,
        title="Fixed Agent Workflow · Tool Calling",
        show_tool_calling=True,
    )


def launch_loop_ui() -> gr.Blocks:
    """Build and launch the notebook-local Tool Calling UI."""
    app = build_loop_ui()
    app.launch(inline=True, share=False, show_error=True, server_name="127.0.0.1", height=900)
    return app
