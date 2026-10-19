"""Core workflow for ``02_grounding.ipynb``."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from lab_common.ai_core import (
    apply_ai_core_environment,
    llm_model_params,
    orchestration_url,
)
from lab_common.config import Settings


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
    response = build_help_grounded_service(settings).run(placeholder_values={"user_query": _required_query(query)})
    return str(response.final_result.choices[0].message.content)


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
    response = build_vector_grounded_service(settings, repository_id=repository_id).run(
        placeholder_values={"user_query": _required_query(query)}
    )
    return str(response.final_result.choices[0].message.content)


def stream_help_grounded_query(query: str, settings: Settings) -> Iterator[str]:
    """Yield only non-empty text deltas from a grounded streaming answer."""
    service = build_help_grounded_service(settings, streaming=True)
    for chunk in service.stream(placeholder_values={"user_query": _required_query(query)}):
        delta = chunk.final_result.choices[0].delta.content
        if delta:
            yield str(delta)
