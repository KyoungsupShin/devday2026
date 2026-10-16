"""Core orchestration, grounding, and memory workflows.

SDK imports happen inside builders so importing and testing this module does not
require an AI Core installation or credentials.
"""
from __future__ import annotations

import os
from typing import Any

from lab_common.ai_core import apply_ai_core_environment, orchestration_url
from lab_common.config import Settings


def _sdk() -> dict[str, Any]:
    try:
        from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
        from gen_ai_hub.orchestration_v2.models.document_grounding import (
            DocumentGroundingConfig, DocumentGroundingFilter, DocumentGroundingPlaceholders, GroundingModuleConfig,
        )
        from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
        from gen_ai_hub.orchestration_v2.models.message import SystemMessage, UserMessage
        from gen_ai_hub.orchestration_v2.models.template import PromptTemplatingModuleConfig, Template
        from gen_ai_hub.orchestration_v2.service import OrchestrationService
    except ImportError as error:
        raise RuntimeError("sap-ai-sdk-gen이 없습니다. requirements.txt를 설치하세요.") from error
    return locals()


def _answer(result: Any) -> str:
    return str(result.final_result.choices[0].message.content)


def build_orchestration_service(settings: Settings, *, system_prompt: str, max_tokens: int = 700) -> Any:
    """Build a prompt-templating service without executing it."""
    sdk = _sdk()
    apply_ai_core_environment(settings)
    template = sdk["Template"](template=[
        sdk["SystemMessage"](content=system_prompt),
        sdk["UserMessage"](content="{{?user_query}}"),
    ])
    prompt = sdk["PromptTemplatingModuleConfig"](
        prompt=template, model=sdk["LLMModelDetails"](name=settings.llm_model, params={"max_tokens": max_tokens})
    )
    config = sdk["OrchestrationConfig"](modules=sdk["ModuleConfig"](prompt_templating=prompt))
    return sdk["OrchestrationService"](api_url=orchestration_url(settings), config=config)


def run_orchestration(query: str, settings: Settings) -> str:
    """Run the basic prompt-templating lesson."""
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("질문을 입력하세요.")
    service = build_orchestration_service(settings, system_prompt="You are a concise, helpful assistant.")
    return _answer(service.run(placeholder_values={"user_query": cleaned}))


def build_grounded_service(settings: Settings, *, repository_type: str, repository_id: str | None = None) -> Any:
    """Build a context-only grounding pipeline for SAP Help or a vector store."""
    sdk = _sdk()
    apply_ai_core_environment(settings)
    if repository_type not in {"help.sap.com", "vector"}:
        raise ValueError("repository_type은 help.sap.com 또는 vector여야 합니다.")
    if repository_type == "vector" and not repository_id:
        raise ValueError("vector grounding에는 repository_id가 필요합니다.")
    filter_args: dict[str, Any] = {"id": "Grounding", "data_repository_type": repository_type}
    if repository_id:
        filter_args["data_repositories"] = [repository_id]
    grounding = sdk["GroundingModuleConfig"](config=sdk["DocumentGroundingConfig"](
        filters=[sdk["DocumentGroundingFilter"](**filter_args)],
        placeholders=sdk["DocumentGroundingPlaceholders"](input=["user_query"], output="grounding_response"),
    ))
    template = sdk["Template"](template=[
        sdk["SystemMessage"](content="Answer only from the provided context. Say when context is insufficient."),
        sdk["UserMessage"](content="Request: {{?user_query}}\nContext: {{?grounding_response}}"),
    ])
    prompt = sdk["PromptTemplatingModuleConfig"](
        prompt=template, model=sdk["LLMModelDetails"](name=settings.llm_model, params={"max_tokens": 1000})
    )
    config = sdk["OrchestrationConfig"](modules=sdk["ModuleConfig"](prompt_templating=prompt, grounding=grounding))
    return sdk["OrchestrationService"](api_url=orchestration_url(settings), config=config)


def run_grounded_query(query: str, settings: Settings, *, repository_type: str = "help.sap.com", repository_id: str | None = None) -> str:
    """Execute one context-grounded query."""
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("질문을 입력하세요.")
    service = build_grounded_service(settings, repository_type=repository_type, repository_id=repository_id)
    return _answer(service.run(placeholder_values={"user_query": cleaned}))


def configured_document_repository() -> str:
    """Read the optional vector collection ID only at the boundary."""
    repository_id = os.getenv("GROUNDING_REPOSITORY_ID", "").strip()
    if not repository_id:
        raise RuntimeError("GROUNDING_REPOSITORY_ID가 없습니다. 루트 .env에 vector collection ID를 설정하세요.")
    return repository_id


class MemoryChatbot:
    """Stateful orchestration conversation with a resettable, explicit history."""

    def __init__(self, settings: Settings, service: Any | None = None):
        self.settings = settings
        self.service = service or build_orchestration_service(
            settings, system_prompt="You are a helpful chatbot assistant.", max_tokens=500
        )
        self.history: list[Any] = []

    def chat(self, message: str) -> str:
        cleaned = message.strip()
        if not cleaned:
            raise ValueError("메시지를 입력하세요.")
        response = self.service.run(placeholder_values={"user_query": cleaned}, history=self.history)
        answer = response.final_result.choices[0].message
        self.history = list(response.intermediate_results.templating)
        self.history.append(answer)
        return str(answer.content)

    def reset(self) -> None:
        self.history = []
