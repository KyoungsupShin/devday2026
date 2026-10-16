"""OpenAI-compatible adapter for a LiteLLM Proxy endpoint."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class LiteLLMConfig:
    """Non-secret connection details for a LiteLLM Proxy."""

    base_url: str
    api_key: str
    model: str

    def missing_fields(self) -> list[str]:
        required = {
            "LITELLM_BASE_URL": self.base_url,
            "LITELLM_API_KEY (or AI_SECRET_KEY)": self.api_key,
            "LITELLM_MODEL (or LLM_MODEL)": self.model,
        }
        return [name for name, value in required.items() if not value]

    def require_configured(self) -> None:
        missing = self.missing_fields()
        if missing:
            raise RuntimeError(
                "LiteLLM OpenAI-compatible 설정이 없습니다: "
                + ", ".join(missing)
                + ". 루트 .env의 LiteLLM 설정을 확인하세요."
            )


def load_litellm_config(environ: Mapping[str, str] | None = None) -> LiteLLMConfig:
    """Load settings without printing or persisting a secret.

    AI_SECRET_KEY is a compatibility alias for an AI gateway key. New settings
    should use the explicit LITELLM_API_KEY name.
    """
    values = os.environ if environ is None else environ
    return LiteLLMConfig(
        base_url=values.get("LITELLM_BASE_URL", "").rstrip("/"),
        api_key=values.get("LITELLM_API_KEY", "") or values.get("AI_SECRET_KEY", ""),
        model=values.get("LITELLM_MODEL", "") or values.get("LLM_MODEL", ""),
    )


def litellm_connection_status(config: LiteLLMConfig | None = None) -> dict[str, Any]:
    """Return display-safe status; credentials are never included."""
    configured = config or load_litellm_config()
    return {
        "openai_compatible": True,
        "base_url": configured.base_url,
        "model": configured.model,
        "api_key": "configured" if configured.api_key else "missing",
        "missing_litellm_fields": configured.missing_fields(),
        "litellm_ready": not configured.missing_fields(),
    }


def openai_client(
    config: LiteLLMConfig | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> Any:
    """Create an OpenAI SDK client which sends requests to LiteLLM Proxy."""
    configured = config or load_litellm_config()
    configured.require_configured()
    if client_factory is None:
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError(
                "OpenAI SDK가 없습니다. python3 -m pip install --user -r requirements.txt 를 실행하세요."
            ) from error
        client_factory = OpenAI
    return client_factory(base_url=configured.base_url, api_key=configured.api_key)


def _message_content(response: Any) -> str:
    """Read content from an OpenAI SDK object or a test double."""
    try:
        content = response.choices[0].message.content
    except AttributeError:
        content = response["choices"][0]["message"]["content"]
    return content or ""


def chat_completion(
    messages: list[dict[str, str]],
    config: LiteLLMConfig | None = None,
    *,
    model: str | None = None,
    client: Any | None = None,
) -> str:
    """Call chat completions through LiteLLM's OpenAI-compatible API."""
    if not messages:
        raise ValueError("messages는 비어 있을 수 없습니다.")
    configured = config or load_litellm_config()
    configured.require_configured()
    selected_model = (model or configured.model).strip()
    if not selected_model:
        raise ValueError("호출할 LiteLLM 모델을 지정하세요.")
    active_client = client or openai_client(configured)
    response = active_client.chat.completions.create(model=selected_model, messages=messages)
    return _message_content(response)
