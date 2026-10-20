"""Agent-specific AI Core client helpers."""
from __future__ import annotations

import base64
from typing import Any

from lab_common.ai_core import apply_ai_core_environment
from lab_common.config import Settings


def generate_image_data_url(settings: Settings, prompt: str, model: str) -> str:
    """Generate one image and return it as a local HTML data URL."""
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
    """Request one native chat completion for an Agent tool-calling turn."""
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
