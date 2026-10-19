"""Thin AI Core adapter. SDK imports are delayed so local exercises still run."""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator
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


def _direct_model_deployment_url(settings: Settings, model: str) -> str:
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


def chat_text(
    settings: Settings, messages: list[dict[str, str]], model: str | None = None
) -> str:
    """Call the selected model deployment through the SAP AI Core Python SDK."""
    selected_model = model or settings.llm_model
    request_body: dict[str, Any] = {
        "model": selected_model,
        "messages": messages,
        "seed": settings.llm_seed,
    }
    deployment_url = _direct_model_deployment_url(settings, selected_model)
    inference_client = _aicore_sdk_client(settings, deployment_url)
    response = inference_client.rest_client.post(
        "/chat/completions?api-version=2025-03-01-preview",
        body=request_body,
    )
    try:
        content = str(response["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError(
            "AI Core LLM 응답에 텍스트 completion이 없습니다."
        ) from error
    return content


def generate_image_data_url(settings: Settings, prompt: str, model: str) -> str:
    """Generate one image through an AI Core Gemini image deployment.

    The native Google Vertex client returns image bytes as inline data.  This
    adapter turns them into a portable data URL for a local HTML preview; it
    never publishes the image to an external host.
    """
    apply_ai_core_environment(settings)
    try:
        from gen_ai_hub.proxy.native.google_vertexai.clients import GenerativeModel
        from vertexai.generative_models import GenerationConfig
    except ImportError as error:
        raise RuntimeError(
            "Gemini 이미지 생성 의존성이 없습니다. requirements.txt를 다시 설치하세요."
        ) from error
    response = GenerativeModel(model_name=model).generate_content(
        prompt,
        generation_config=GenerationConfig(response_modalities=["IMAGE"]),
    )
    for candidate in getattr(response, "candidates", []) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", []) or []:
            inline_data = getattr(part, "inline_data", None)
            data = getattr(inline_data, "data", None)
            mime_type = getattr(inline_data, "mime_type", None) or "image/png"
            if data:
                image_bytes = data if isinstance(data, bytes) else bytes(data)
                encoded = base64.b64encode(image_bytes).decode("ascii")
                return f"data:{mime_type};base64,{encoded}"
    raise RuntimeError("Gemini 이미지 생성 응답에 inline image data가 없습니다.")


def chat_tool_completion(
    settings: Settings,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str | None = None,
    tool_choice: str | dict[str, Any] = "auto",
) -> Any:
    """Request one native chat completion through the SAP GenAI Hub SDK.

    ``tool_choice="none"`` is used for the response after local tools have
    completed.  Keeping both turns on this client preserves the required
    assistant-tool_calls -> tool-message protocol.
    """
    selected_model = model or settings.llm_model
    request: dict[str, Any] = {
        "model_name": selected_model,
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
        "seed": settings.llm_seed,
    }
    if settings.llm_deployment_id and selected_model == settings.llm_model:
        request["deployment_id"] = settings.llm_deployment_id

    apply_ai_core_environment(settings)
    try:
        from gen_ai_hub.proxy.native.openai import chat
    except ImportError as error:
        raise RuntimeError(
            "sap-ai-sdk-gen이 없습니다. pip install -r requirements.txt를 실행하세요."
        ) from error
    return chat.completions.create(**request)


def llm_model_params(settings: Settings, *, max_tokens: int) -> dict[str, int]:
    """Return SDK-safe Luna generation controls for prompt-templating services."""
    # gpt-5.6-luna accepts a stable seed, while non-default temperature values
    # are rejected by the deployment. Keep the model's required default temperature.
    return {"max_tokens": max_tokens, "seed": settings.llm_seed}


def chat_text_stream(
    settings: Settings,
    messages: list[dict[str, str]],
    model: str | None = None,
) -> Iterator[str]:
    """Yield the completed response through the SDK's synchronous REST client."""
    response = chat_text(settings, messages, model)
    if response:
        yield response
