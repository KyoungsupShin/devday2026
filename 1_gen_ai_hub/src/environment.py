"""Testable AI Core environment workflow without notebook or UI dependencies."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from lab_common.ai_core import list_running_deployments
from lab_common.config import Settings, load_settings
from .litellm_adapter import litellm_connection_status


ENVIRONMENT_KEYS = (
    "AICORE_BASE_URL",
    "AICORE_AUTH_URL",
    "AICORE_CLIENT_ID",
    "AICORE_CLIENT_SECRET",
    "AICORE_RESOURCE_GROUP",
    "LLM_MODEL",
    "EMBED_MODEL",
)


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
        "litellm": litellm_connection_status(),
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


def write_environment_updates(updates: dict[str, str], env_file: Path) -> list[str]:
    """Persist permitted nonblank settings while preserving unrelated .env lines.

    The caller decides which values to supply. Secrets are written but never
    returned; the result contains only the updated key names.
    """
    selected = {key: value.strip() for key, value in updates.items() if key in ENVIRONMENT_KEYS and value.strip()}
    if not selected:
        return []
    original = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    pending = dict(selected)
    rewritten: list[str] = []
    for line in original.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        rewritten.append(f"{key}={pending.pop(key)}" if key in pending else line)
    if pending:
        if rewritten and rewritten[-1]:
            rewritten.append("")
        rewritten.extend(f"{key}={value}" for key, value in pending.items())
    env_file.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    return list(selected)
