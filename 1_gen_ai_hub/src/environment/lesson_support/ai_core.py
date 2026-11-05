"""Thin AI Core adapter. SDK imports are delayed so local exercises still run."""

from __future__ import annotations

from typing import Any

import requests

from .config import Settings

def access_token(settings: Settings) -> str:
    settings.require_ai_core()
    response = requests.post(
        f"{settings.auth_url}/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=(settings.client_id, settings.client_secret),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def list_running_deployments(settings: Settings) -> list[dict[str, Any]]:
    token = access_token(settings)
    response = requests.get(
        f"{settings.base_url}/v2/lm/deployments?$top=200",
        headers={
            "Authorization": f"Bearer {token}",
            "AI-Resource-Group": settings.resource_group,
        },
        timeout=20,
    )
    response.raise_for_status()
    return [
        deployment
        for deployment in response.json().get("resources", [])
        if deployment.get("status") == "RUNNING"
    ]


def api_headers(settings: Settings) -> dict[str, str]:
    """Return the standard authenticated headers for AI Core REST examples."""
    return {
        "Authorization": f"Bearer {access_token(settings)}",
        "AI-Resource-Group": settings.resource_group,
        "Content-Type": "application/json",
    }


