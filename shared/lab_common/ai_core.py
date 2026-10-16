"""Thin AI Core adapter. SDK imports are delayed so local exercises still run."""
from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import requests

from .config import Settings


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
        headers={"Authorization": f"Bearer {token}", "AI-Resource-Group": settings.resource_group},
        timeout=20,
    )
    response.raise_for_status()
    return [deployment for deployment in response.json().get("resources", []) if deployment.get("status") == "RUNNING"]


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
        if deployment.get("scenarioId") == "orchestration" and deployment.get("deploymentUrl"):
            return str(deployment["deploymentUrl"])
    raise RuntimeError("RUNNING orchestration 배포를 찾지 못했습니다.")


def chat_text(settings: Settings, messages: list[dict[str, str]], model: str | None = None) -> str:
    """Make one native AI Core chat request and return its text content."""
    apply_ai_core_environment(settings)
    try:
        from gen_ai_hub.proxy.native.openai import chat
    except ImportError as error:
        raise RuntimeError("sap-ai-sdk-gen이 없습니다. pip install -r requirements.txt를 실행하세요.") from error
    response = chat.completions.create(model_name=model or settings.llm_model, messages=messages)
    return response.choices[0].message.content


def chat_tool_completion(
    settings: Settings,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str | None = None,
) -> Any:
    """Request one native OpenAI-compatible chat completion with Tool Calling enabled."""
    apply_ai_core_environment(settings)
    try:
        from gen_ai_hub.proxy.native.openai import chat
    except ImportError as error:
        raise RuntimeError("sap-ai-sdk-gen이 없습니다. pip install -r requirements.txt를 실행하세요.") from error
    return chat.completions.create(
        model_name=model or settings.llm_model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )


def _stream_content(chunk: Any) -> str:
    """Extract one text delta from the native OpenAI-compatible stream."""
    choices = getattr(chunk, "choices", None)
    if choices is None and isinstance(chunk, dict):
        choices = chunk.get("choices", [])
    if not choices:
        return ""
    choice = choices[0]
    delta = getattr(choice, "delta", None)
    if delta is None and isinstance(choice, dict):
        delta = choice.get("delta", {})
    content = getattr(delta, "content", None)
    if content is None and isinstance(delta, dict):
        content = delta.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
            for item in content
        )
    return ""


def chat_text_stream(
    settings: Settings,
    messages: list[dict[str, str]],
    model: str | None = None,
) -> Iterator[str]:
    """Yield native AI Core chat text deltas as soon as the deployment emits them."""
    apply_ai_core_environment(settings)
    try:
        from gen_ai_hub.proxy.native.openai import chat
    except ImportError as error:
        raise RuntimeError("sap-ai-sdk-gen이 없습니다. pip install -r requirements.txt를 실행하세요.") from error
    stream = chat.completions.create(
        model_name=model or settings.llm_model,
        messages=messages,
        stream=True,
    )
    for chunk in stream:
        text = _stream_content(chunk)
        if text:
            yield text

