"""Thin AI Core adapter. SDK imports are delayed so local exercises still run."""

from __future__ import annotations

import os
from typing import Any

import requests

from .config import Settings

DEFAULT_CHAT_TIMEOUT_SECONDS = 90.0


def _chat_timeout_seconds() -> float:
    """Read the chat timeout lazily, after the repository .env has been loaded."""
    try:
        return max(
            1.0,
            float(os.getenv("CHAT_TIMEOUT_SECONDS", str(DEFAULT_CHAT_TIMEOUT_SECONDS))),
        )
    except ValueError:
        return DEFAULT_CHAT_TIMEOUT_SECONDS


def _aicore_sdk_client(settings: Settings, base_url: str) -> Any:
    """Create the SAP AI Core Python SDK client without using Orchestration."""
    try:
        from ai_core_sdk.ai_core_v2_client import AICoreV2Client
    except ImportError as error:
        raise RuntimeError(
            "sap-ai-sdk-core가 없습니다. pip install -r requirements.txt를 실행하세요."
        ) from error
    settings.require_ai_core()
    return AICoreV2Client(
        base_url=base_url.rstrip("/"),
        auth_url=f"{settings.auth_url}/oauth/token",
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        resource_group=settings.resource_group,
        read_timeout=int(_chat_timeout_seconds()),
        connect_timeout=int(_chat_timeout_seconds()),
        num_request_retries=0,
    )


def _deployment_model_name(deployment: Any) -> str:
    details = getattr(deployment, "details", {}) or {}
    return str(
        details.get("resources", {})
        .get("backend_details", {})
        .get("model", {})
        .get("name", "")
    )


def model_deployment_url(settings: Settings, model: str) -> str:
    """Find the configured RUNNING model deployment through the AI Core SDK."""
    control_client = _aicore_sdk_client(settings, f"{settings.base_url}/v2")
    configured_id = settings.llm_deployment_id if model == settings.llm_model else ""
    for deployment in control_client.deployment.query(top=200).resources:
        status = getattr(getattr(deployment, "status", None), "value", "")
        if (
            status == "RUNNING"
            and _deployment_model_name(deployment) == model
            and deployment.deployment_url
            and (not configured_id or str(getattr(deployment, "id", "")) == configured_id)
        ):
            return str(deployment.deployment_url).rstrip("/")
    if configured_id:
        raise RuntimeError(
            "설정한 AICORE_LLM_DEPLOYMENT_ID에 RUNNING 상태의 "
            f"{model!r} 배포가 없습니다: {configured_id!r}"
        )
    raise RuntimeError(f"RUNNING LLM deployment를 찾지 못했습니다: {model!r}")


def apply_ai_core_environment(settings: Settings) -> None:
    """Expose standard SDK environment names after validating local settings."""
    settings.require_ai_core()
    mapping = {
        "AICORE_BASE_URL": settings.base_url,
        "AICORE_AUTH_URL": settings.auth_url,
        "AICORE_CLIENT_ID": settings.client_id,
        "AICORE_CLIENT_SECRET": settings.client_secret,
        "AICORE_RESOURCE_GROUP": settings.resource_group,
    }
    for key, value in mapping.items():
        os.environ.setdefault(key, value)


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


def orchestration_url(settings: Settings) -> str:
    """Find the RUNNING orchestration deployment unless an explicit URL is set."""
    configured = os.getenv("AICORE_ORCHESTRATION_DEPLOYMENT_URL", "").rstrip("/")
    if configured:
        return configured
    for deployment in list_running_deployments(settings):
        if deployment.get("scenarioId") == "orchestration" and deployment.get(
            "deploymentUrl"
        ):
            return str(deployment["deploymentUrl"])
    raise RuntimeError("RUNNING orchestration 배포를 찾지 못했습니다.")


def llm_model_params(settings: Settings, *, max_tokens: int) -> dict[str, int]:
    """Return SDK-safe Luna generation controls for prompt-templating services."""
    # gpt-5.6-luna accepts a stable seed, while non-default temperature values
    # are rejected by the deployment. Keep the model's required default temperature.
    return {"max_tokens": max_tokens, "seed": settings.llm_seed}
