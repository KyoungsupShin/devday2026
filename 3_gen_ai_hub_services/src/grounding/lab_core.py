"""Core workflow for ``02_grounding.ipynb``."""
from __future__ import annotations

from collections.abc import Iterator
from collections.abc import Mapping
from typing import Any

from .lesson_support.ai_core import (
    apply_ai_core_environment,
    llm_model_params,
    orchestration_url,
)
from .lesson_support.config import Settings


def _sdk() -> dict[str, Any]:
    try:
        from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
        from gen_ai_hub.orchestration_v2.models.document_grounding import (
            DocumentGroundingConfig, DocumentGroundingFilter, DocumentGroundingPlaceholders, GroundingModuleConfig,
        )
        from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
        from gen_ai_hub.orchestration_v2.models.message import SystemMessage, UserMessage
        from gen_ai_hub.orchestration_v2.models.streaming import GlobalStreamOptions
        from gen_ai_hub.orchestration_v2.models.template import PromptTemplatingModuleConfig, Template
        from gen_ai_hub.orchestration_v2.service import OrchestrationService
    except ImportError as error:
        raise RuntimeError("sap-ai-sdk-gen이 없습니다. requirements.txt를 설치하세요.") from error
    return locals()


def _required_query(query: str) -> str:
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("질문을 입력하세요.")
    return cleaned


def _value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _jsonable(value: Any) -> Any:
    """Convert SDK response metadata to values suitable for a notebook/UI."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def _grounding_trace(response: Any, *, source: str) -> dict[str, Any]:
    """Expose grounding-module metadata when the service returns it.

    The managed service may return retrieved chunks, document IDs, or citations in
    ``data`` depending on repository type and service version.  Do not invent
    citations when that metadata is absent.
    """
    intermediate = _value(response, "intermediate_results")
    grounding = _value(intermediate, "grounding")
    if grounding is None:
        return {
            "configured_source": source,
            "metadata_available": False,
            "message": "Grounding module metadata was not returned by the service.",
            "data": None,
        }
    return {
        "configured_source": source,
        "metadata_available": True,
        "message": str(_value(grounding, "message") or ""),
        "data": _jsonable(_value(grounding, "data")),
    }


def _grounded_result(response: Any, *, source: str) -> dict[str, Any]:
    return {
        "answer": str(response.final_result.choices[0].message.content),
        "grounding": _grounding_trace(response, source=source),
    }


def build_help_grounded_service(settings: Settings, *, streaming: bool = False) -> Any:
    """Build the public help.sap.com grounding pipeline."""
    sdk = _sdk()
    apply_ai_core_environment(settings)
    grounding = sdk["GroundingModuleConfig"](config=sdk["DocumentGroundingConfig"](
        filters=[sdk["DocumentGroundingFilter"](id="SAPHelp", data_repository_type="help.sap.com")],
        placeholders=sdk["DocumentGroundingPlaceholders"](input=["user_query"], output="grounding_response"),
    ))
    prompt = sdk["PromptTemplatingModuleConfig"](
        prompt=sdk["Template"](template=[
            sdk["SystemMessage"](content="Answer only from the provided context. Say when context is insufficient."),
            sdk["UserMessage"](content="Request: {{?user_query}}\nContext: {{?grounding_response}}"),
        ]),
        model=sdk["LLMModelDetails"](name=settings.llm_model, params=llm_model_params(settings, max_tokens=1000)),
    )
    config_args: dict[str, Any] = {
        "modules": sdk["ModuleConfig"](prompt_templating=prompt, grounding=grounding)
    }
    if streaming:
        config_args["stream"] = sdk["GlobalStreamOptions"](enabled=True)
    config = sdk["OrchestrationConfig"](**config_args)
    return sdk["OrchestrationService"](api_url=orchestration_url(settings), config=config)


def run_help_grounded_query(query: str, settings: Settings) -> str:
    return run_help_grounded_query_with_trace(query, settings)["answer"]


def run_help_grounded_query_with_trace(query: str, settings: Settings) -> dict[str, Any]:
    response = build_help_grounded_service(settings).run(
        placeholder_values={"user_query": _required_query(query)}
    )
    return _grounded_result(response, source="help.sap.com")


def build_vector_grounded_service(settings: Settings, *, repository_id: str) -> Any:
    """Build the custom vector-repository grounding pipeline used by this lab's UI."""
    repository = repository_id.strip()
    if not repository:
        raise ValueError("Grounding repository ID를 입력하세요.")
    sdk = _sdk()
    apply_ai_core_environment(settings)
    grounding = sdk["GroundingModuleConfig"](config=sdk["DocumentGroundingConfig"](
        filters=[sdk["DocumentGroundingFilter"](
            id="CustomRepository", data_repository_type="vector", data_repositories=[repository]
        )],
        placeholders=sdk["DocumentGroundingPlaceholders"](input=["user_query"], output="grounding_response"),
    ))
    prompt = sdk["PromptTemplatingModuleConfig"](
        prompt=sdk["Template"](template=[
            sdk["SystemMessage"](content="Answer only from the provided context. Say when context is insufficient."),
            sdk["UserMessage"](content="Request: {{?user_query}}\nContext: {{?grounding_response}}"),
        ]),
        model=sdk["LLMModelDetails"](name=settings.llm_model, params=llm_model_params(settings, max_tokens=1000)),
    )
    config = sdk["OrchestrationConfig"](modules=sdk["ModuleConfig"](prompt_templating=prompt, grounding=grounding))
    return sdk["OrchestrationService"](api_url=orchestration_url(settings), config=config)


def run_vector_grounded_query(query: str, settings: Settings, *, repository_id: str) -> str:
    return run_vector_grounded_query_with_trace(
        query, settings, repository_id=repository_id
    )["answer"]


def run_vector_grounded_query_with_trace(
    query: str, settings: Settings, *, repository_id: str
) -> dict[str, Any]:
    response = build_vector_grounded_service(settings, repository_id=repository_id).run(
        placeholder_values={"user_query": _required_query(query)}
    )
    return _grounded_result(response, source=f"vector:{repository_id.strip()}")


def stream_help_grounded_query(query: str, settings: Settings) -> Iterator[str]:
    """Yield only non-empty text deltas from a grounded streaming answer."""
    service = build_help_grounded_service(settings, streaming=True)
    for chunk in service.stream(placeholder_values={"user_query": _required_query(query)}):
        delta = chunk.final_result.choices[0].delta.content
        if delta:
            yield str(delta)
