"""Core workflow for ``01_orchestration.ipynb``."""
from __future__ import annotations

from typing import Any, Callable

from lab_common.ai_core import (
    apply_ai_core_environment,
    llm_model_params,
    orchestration_url,
)
from lab_common.config import Settings


def _sdk() -> dict[str, Any]:
    try:
        from gen_ai_hub.orchestration_v2.models.config import (
            CompletionRequestConfigurationReferenceByIdConfigRef, ModuleConfig, OrchestrationConfig,
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


def _registry_client() -> Any:
    try:
        from gen_ai_hub.prompt_registry.client import OrchestrationConfigClient
    except ImportError as error:
        raise RuntimeError(
            "Orchestration Config Registry에는 sap-ai-sdk-gen>=7.4,<8가 필요합니다. requirements.txt를 설치하세요."
        ) from error
    return OrchestrationConfigClient()


def _required(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name}을(를) 입력하세요.")
    return cleaned


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(by_alias=True, exclude_none=True))
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def build_saved_orchestration_spec(
    settings: Settings, *, system_prompt: str, user_prompt: str = "{{?user_query}}",
    model: str | None = None, max_tokens: int = 700,
) -> Any:
    """Build one Prompt Registry-ready spec without writing it."""
    system = _required(system_prompt, "System prompt")
    user = _required(user_prompt, "User prompt")
    if "{{?user_query}}" not in user:
        raise ValueError("User prompt에는 {{?user_query}} placeholder가 필요합니다.")
    if max_tokens < 1:
        raise ValueError("max_tokens는 1 이상이어야 합니다.")
    sdk = _sdk()
    template = sdk["Template"](template=[
        sdk["SystemMessage"](content=system), sdk["UserMessage"](content=user),
    ])
    prompt = sdk["PromptTemplatingModuleConfig"](
        prompt=template,
        model=sdk["LLMModelDetails"](name=(model or settings.llm_model).strip(), params=llm_model_params(settings, max_tokens=max_tokens)),
    )
    return sdk["OrchestrationConfig"](modules=sdk["ModuleConfig"](prompt_templating=prompt))


def preview_saved_orchestration_spec(
    settings: Settings, *, system_prompt: str, user_prompt: str = "{{?user_query}}",
    model: str | None = None, max_tokens: int = 700,
) -> dict[str, Any]:
    return _json_value(build_saved_orchestration_spec(
        settings, system_prompt=system_prompt, user_prompt=user_prompt, model=model, max_tokens=max_tokens
    ))


def save_orchestration_config(
    settings: Settings, *, name: str, version: str, scenario: str, system_prompt: str,
    user_prompt: str = "{{?user_query}}", model: str | None = None, max_tokens: int = 700,
    registry_client: Any | None = None,
) -> dict[str, Any]:
    """Create or update a Prompt Registry orchestration config."""
    spec = build_saved_orchestration_spec(
        settings, system_prompt=system_prompt, user_prompt=user_prompt, model=model, max_tokens=max_tokens
    )
    response = (registry_client or _registry_client()).create_orchestration_config(
        name=_required(name, "Config name"), version=_required(version, "Version"),
        scenario=_required(scenario, "Scenario"), spec=spec,
    )
    return {
        "operation": "saved", "id": str(response.id), "name": str(response.name),
        "version": str(response.version), "scenario": str(response.scenario), "message": str(response.message),
    }


def get_orchestration_config(config_id: str, *, registry_client: Any | None = None) -> dict[str, Any]:
    return _json_value((registry_client or _registry_client()).get_orchestration_config_by_id(
        _required(config_id, "Config ID"), resolve_template_ref=True
    ))


def list_orchestration_configs(
    *, scenario: str, name: str, version: str, include_spec: bool = False, registry_client: Any | None = None,
) -> dict[str, Any]:
    response = (registry_client or _registry_client()).get_orchestration_configs(
        scenario=_required(scenario, "Scenario"), name=_required(name, "Config name"),
        version=_required(version, "Version"), include_spec=include_spec, resolve_template_ref=include_spec,
    )
    return {"count": int(response.count), "resources": _json_value(response.resources)}


def delete_orchestration_config(config_id: str, *, registry_client: Any | None = None) -> dict[str, Any]:
    selected_id = _required(config_id, "Config ID")
    response = (registry_client or _registry_client()).delete_orchestration_config_by_id(selected_id)
    return {"operation": "deleted", "id": selected_id, "message": str(response.message)}


def invoke_saved_orchestration_config(
    query: str, settings: Settings, *, config_id: str, service_factory: Callable[[Any], Any] | None = None,
) -> dict[str, str]:
    cleaned_query, selected_id = _required(query, "질문"), _required(config_id, "Config ID")
    sdk = _sdk()
    config_ref = sdk["CompletionRequestConfigurationReferenceByIdConfigRef"](id=selected_id)
    if service_factory is None:
        apply_ai_core_environment(settings)
        service = sdk["OrchestrationService"](api_url=orchestration_url(settings), config_ref=config_ref)
    else:
        service = service_factory(config_ref)
    return {"config_id": selected_id, "answer": _answer(service.run(placeholder_values={"user_query": cleaned_query}))}


def build_orchestration_service(settings: Settings, *, system_prompt: str, max_tokens: int = 700) -> Any:
    """Build a prompt-templating service without executing it."""
    if max_tokens < 1:
        raise ValueError("max_tokens는 1 이상이어야 합니다.")
    sdk = _sdk()
    apply_ai_core_environment(settings)
    template = sdk["Template"](template=[
        sdk["SystemMessage"](content=_required(system_prompt, "System prompt")),
        sdk["UserMessage"](content="{{?user_query}}"),
    ])
    prompt = sdk["PromptTemplatingModuleConfig"](
        prompt=template, model=sdk["LLMModelDetails"](name=settings.llm_model, params=llm_model_params(settings, max_tokens=max_tokens))
    )
    config = sdk["OrchestrationConfig"](modules=sdk["ModuleConfig"](prompt_templating=prompt))
    return sdk["OrchestrationService"](api_url=orchestration_url(settings), config=config)


def run_orchestration(query: str, settings: Settings) -> str:
    return _answer(build_orchestration_service(
        settings, system_prompt="You are a concise, helpful assistant."
    ).run(placeholder_values={"user_query": _required(query, "질문")}))
