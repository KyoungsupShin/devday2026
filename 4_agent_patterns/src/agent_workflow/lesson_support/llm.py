"""Generic text-completion helpers shared by the hands-on stages."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .ai_core import _aicore_sdk_client, model_deployment_url
from .config import Settings


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
    deployment_url = model_deployment_url(settings, selected_model)
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


def chat_text_stream(
    settings: Settings,
    messages: list[dict[str, str]],
    model: str | None = None,
) -> Iterator[str]:
    """Yield the completed response through the SDK's synchronous REST client."""
    response = chat_text(settings, messages, model)
    if response:
        yield response
