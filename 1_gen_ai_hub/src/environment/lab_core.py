"""Testable AI Core environment workflow without notebook or UI dependencies."""
from __future__ import annotations

import os
from typing import Any, Callable

from .lesson_support.ai_core import list_running_deployments
from .lesson_support.config import Settings, load_settings


def environment_status(settings: Settings | None = None, *, embed_model: str | None = None) -> dict[str, Any]:
    """Return a display-safe configuration status without exposing credentials."""
    configured = settings or load_settings()
    return {
        "missing_ai_core_fields": configured.missing_ai_core_fields(),
        "ai_core_ready": not configured.missing_ai_core_fields(),
        "resource_group": configured.resource_group,
        "llm_model": configured.llm_model,
        "embedding_model": embed_model if embed_model is not None else os.getenv("EMBED_MODEL", ""),
        "client_id": "configured" if configured.client_id else "missing",
        "client_secret": "configured" if configured.client_secret else "missing",
    }


def deployment_status(
    settings: Settings | None = None,
    *,
    deployment_loader: Callable[[Settings], list[dict[str, Any]]] = list_running_deployments,
) -> dict[str, Any]:
    """List only the fields learners need to identify RUNNING deployments."""
    configured = settings or load_settings()
    configured.require_ai_core()
    deployments = deployment_loader(configured)
    return {
        "resource_group": configured.resource_group,
        "running_deployments": [
            {
                "scenario_id": item.get("scenarioId", "unknown"),
                "status": item.get("status", "unknown"),
                "deployment_url": item.get("deploymentUrl", ""),
            }
            for item in deployments
        ],
    }


