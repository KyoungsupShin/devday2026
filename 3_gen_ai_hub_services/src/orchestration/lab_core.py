"""Core workflow for ``01_orchestration.ipynb``."""
from __future__ import annotations

from typing import Any, Callable

from lab_common.ai_core import (
    apply_ai_core_environment,
    llm_model_params,
    orchestration_url,
)
from lab_common.config import Settings


_REGISTRY_CONFIG_PATH = "/registry/v2/orchestrationConfigs"


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


def _registry_client(settings: Settings | None = None) -> Any:
    """Create a Prompt Registry client using the configured AI Core credentials."""
    try:
        from gen_ai_hub.prompt_registry.client import OrchestrationConfigClient
    except ImportError as error:
        raise RuntimeError(
            "Orchestration Config Registry에는 sap-ai-sdk-gen>=7.4,<8가 필요합니다. requirements.txt를 설치하세요."
        ) from error
    if settings is not None:
        apply_ai_core_environment(settings)
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


def _registry_get(client: Any, path: str, *, params: dict[str, Any]) -> Any:
    """Read Registry JSON without deserializing it through SDK config models.

    Registry can return new Orchestration module fields before the installed SDK
    models are updated.  Listing and displaying a saved configuration only need
    the service response; strict SDK deserialization would reject those fields.
    Injected test clients retain the typed SDK method fallback.
    """
    rest_client = getattr(client, "rest_client", None)
    if rest_client is not None:
        return rest_client.get(path=path, params=params, convert_params_to_camel_case=False)
    if path == _REGISTRY_CONFIG_PATH:
        return client.get_orchestration_configs(**params)
    config_id = path.rsplit("/", 1)[-1]
    return client.get_orchestration_config_by_id(
        config_id, resolve_template_ref=params["resolve_template_ref"]
    )


def get_orchestration_config(
    config_id: str, *, settings: Settings | None = None, registry_client: Any | None = None,
) -> dict[str, Any]:
    selected_id = _required(config_id, "Config ID")
    client = registry_client or _registry_client(settings)
    return _json_value(_registry_get(
        client, f"{_REGISTRY_CONFIG_PATH}/{selected_id}", params={"resolve_template_ref": True}
    ))


def list_orchestration_configs(
    *, scenario: str | None = None, name: str | None = None, version: str | None = None,
    include_spec: bool = False, settings: Settings | None = None, registry_client: Any | None = None,
) -> dict[str, Any]:
    """List registered orchestration configs, optionally narrowed by registry fields."""
    response = _registry_get(
        registry_client or _registry_client(settings), _REGISTRY_CONFIG_PATH, params={
            "scenario": scenario.strip() if scenario and scenario.strip() else None,
            "name": name.strip() if name and name.strip() else None,
            "version": version.strip() if version and version.strip() else None,
            "include_spec": include_spec,
            "resolve_template_ref": include_spec,
        }
    )
    if isinstance(response, dict):
        resources = response.get("resources", [])
        return {"count": int(response.get("count", len(resources))), "resources": _json_value(resources)}
    return {"count": int(response.count), "resources": _json_value(response.resources)}


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
