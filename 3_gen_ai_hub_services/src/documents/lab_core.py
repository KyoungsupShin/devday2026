"""Core workflow for ``03_my_documents.ipynb``."""
from __future__ import annotations

import os
from typing import Any

import requests

from lab_common.ai_core import (
    api_headers,
    apply_ai_core_environment,
    llm_model_params,
    orchestration_url,
)
from lab_common.config import Settings
from lab_common.grounding_repository import delete_document, list_documents, upload_text_document


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


def configured_document_repository() -> str:
    repository_id = os.getenv("GROUNDING_REPOSITORY_ID", "").strip()
    if not repository_id:
        raise RuntimeError("GROUNDING_REPOSITORY_ID가 없습니다. 루트 .env에 vector collection ID를 설정하세요.")
    return repository_id


def _required(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name}을(를) 입력하세요.")
    return cleaned


def build_document_grounded_service(settings: Settings, *, repository_id: str) -> Any:
    sdk = _sdk()
    apply_ai_core_environment(settings)
    repository = _required(repository_id, "Grounding repository ID")
    grounding = sdk["GroundingModuleConfig"](config=sdk["DocumentGroundingConfig"](
        filters=[sdk["DocumentGroundingFilter"](
            id="MyDocs", data_repository_type="vector", data_repositories=[repository]
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


def run_document_grounded_query(query: str, settings: Settings, *, repository_id: str | None = None) -> str:
    cleaned = _required(query, "질문")
    service = build_document_grounded_service(settings, repository_id=repository_id or configured_document_repository())
    response = service.run(placeholder_values={"user_query": cleaned})
    return str(response.final_result.choices[0].message.content)


def list_document_ids(settings: Settings, *, repository_id: str | None = None) -> list[str]:
    documents = list_documents(settings, repository_id or configured_document_repository())
    return [document_id(document) for document in documents if document_id(document)]


def document_id(document: dict[str, Any]) -> str:
    value = document.get("id") or document.get("documentId")
    if value:
        return str(value)
    for item in document.get("metadata", []):
        if item.get("key") == "id" and item.get("value"):
            return str(item["value"][0])
    return ""


def upload_document_text(settings: Settings, *, filename: str, text: str, repository_id: str | None = None) -> dict[str, Any]:
    return upload_text_document(settings, repository_id or configured_document_repository(), filename=filename, text=text)


def delete_document_by_id(settings: Settings, *, document_id: str, repository_id: str | None = None) -> None:
    delete_document(settings, repository_id or configured_document_repository(), document_id)


def find_document_repository(settings: Settings) -> str:
    """Return the configured ID, or the first vector collection that has documents."""
    configured = os.getenv("GROUNDING_REPOSITORY_ID", "").strip()
    if configured:
        return configured
    settings.require_ai_core()
    base_url = settings.base_url.rstrip("/") + "/v2/lm/document-grounding"
    response = requests.get(f"{base_url}/vector/collections", headers=api_headers(settings), timeout=30)
    response.raise_for_status()
    collections = response.json()
    collections = collections.get("resources", collections) if isinstance(collections, dict) else collections
    for collection in collections:
        collection_id = str(collection.get("id", "")).strip()
        if not collection_id:
            continue
        documents = requests.get(
            f"{base_url}/vector/collections/{collection_id}/documents", headers=api_headers(settings), timeout=30
        )
        documents.raise_for_status()
        if int(documents.json().get("count", 0)) > 0:
            return collection_id
    raise RuntimeError("문서가 있는 vector collection을 찾지 못했습니다.")


def search_document_chunks(query: str, settings: Settings, *, repository_id: str) -> list[dict[str, Any]]:
    cleaned = _required(query, "질문")
    settings.require_ai_core()
    url = settings.base_url.rstrip("/") + "/v2/lm/document-grounding/retrieval/search"
    response = requests.post(
        url, headers=api_headers(settings),
        json={"query": cleaned, "filters": [{"id": "f", "dataRepositoryType": "vector", "dataRepositories": [repository_id]}]},
        timeout=60,
    )
    response.raise_for_status()
    chunks: list[dict[str, Any]] = []
    for result in response.json().get("results", []):
        for nested in result.get("results", []):
            for document in nested.get("dataRepository", {}).get("documents", []):
                chunks.extend(document.get("chunks", []))
    return chunks
