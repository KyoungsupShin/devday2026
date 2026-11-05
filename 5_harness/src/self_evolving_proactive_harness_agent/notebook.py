"""Notebook-facing entry points for the proactive harness lesson."""

from __future__ import annotations

from typing import Any

from lab_common.config import Settings, load_settings

from .meta_agent import MetaCognitiveAgent
from .repository import CognitiveRepository, JsonCognitiveRepository
from .runtime import CognitiveCore, RuntimePolicy
from .ui import build_proactive_harness_ui


def create_default_core(
    *,
    settings: Settings | None = None,
    repository: CognitiveRepository | None = None,
    policy: RuntimePolicy = RuntimePolicy(),
) -> CognitiveCore:
    """Create the production-shaped core used by the hands-on notebook."""
    selected_settings = settings or load_settings()
    return CognitiveCore(
        repository or JsonCognitiveRepository(),
        MetaCognitiveAgent(selected_settings),
        policy=policy,
    )


def create_notebook_ui(
    *,
    settings: Settings | None = None,
    repository: CognitiveRepository | None = None,
    policy: RuntimePolicy = RuntimePolicy(),
):
    """Return the complete UI without launching a local server."""
    return build_proactive_harness_ui(
        create_default_core(settings=settings, repository=repository, policy=policy)
    )


def launch_notebook_ui(**launch_options: Any):
    """Create and launch the Gradio lesson UI with notebook-safe defaults."""
    interface = create_notebook_ui()
    return interface.launch(
        share=False,
        inline=True,
        show_error=True,
        **launch_options,
    )
