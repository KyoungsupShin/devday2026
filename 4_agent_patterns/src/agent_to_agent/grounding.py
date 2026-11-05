"""SAP BTP vector-Grounding evidence for the F&B A2A workflow.

The Grounding service enriches the LLM decision record; it never selects an
Agent or performs an A2A handoff.  Team and Sub-agent selection remains an
LLM decision in the orchestration layer.
"""

from __future__ import annotations

import os
from typing import Any

from .lesson_support.ai_core import (
    apply_ai_core_environment,
    llm_model_params,
    orchestration_url,
)
from .lesson_support.config import Settings
from .lesson_support.grounding_repository import list_documents

try:
    from gen_ai_hub.orchestration_v2.models.config import (
        ModuleConfig as _ModuleConfig,
    )
    from gen_ai_hub.orchestration_v2.models.config import (
        OrchestrationConfig as _OrchestrationConfig,
    )
    from gen_ai_hub.orchestration_v2.models.document_grounding import (
        DocumentGroundingConfig as _DocumentGroundingConfig,
    )
    from gen_ai_hub.orchestration_v2.models.document_grounding import (
        DocumentGroundingFilter as _DocumentGroundingFilter,
    )
    from gen_ai_hub.orchestration_v2.models.document_grounding import (
        DocumentGroundingPlaceholders as _DocumentGroundingPlaceholders,
    )
    from gen_ai_hub.orchestration_v2.models.document_grounding import (
        GroundingModuleConfig as _GroundingModuleConfig,
    )
    from gen_ai_hub.orchestration_v2.models.llm_model_details import (
        LLMModelDetails as _LLMModelDetails,
    )
    from gen_ai_hub.orchestration_v2.models.message import (
        SystemMessage as _SystemMessage,
    )
    from gen_ai_hub.orchestration_v2.models.message import (
        UserMessage as _UserMessage,
    )
    from gen_ai_hub.orchestration_v2.models.template import (
        PromptTemplatingModuleConfig as _PromptTemplatingModuleConfig,
    )
    from gen_ai_hub.orchestration_v2.models.template import (
        Template as _Template,
    )
    from gen_ai_hub.orchestration_v2.service import (
        OrchestrationService as _OrchestrationService,
    )
except ImportError as error:
    _SDK_IMPORT_ERROR: ImportError | None = error
else:
    _SDK_IMPORT_ERROR = None

GROUNDING_REPOSITORY_ENV = "GROUNDING_REPOSITORY_ID"
MANUAL_SEARCH_TOOL_NAME = "search_manuals"


def manual_search_tool() -> dict[str, Any]:
    """Describe the read-only manual search available to Orchestration.

    The model decides whether it needs this tool and which question to search.
    This schema never selects an Agent or a workflow path.
    """
    return {
        "type": "function",
        "function": {
            "name": MANUAL_SEARCH_TOOL_NAME,
            "description": (
                "Search the configured SAP BTP Vector Grounding repository for "
                "manual evidence relevant to the current orchestration decision. "
                "Use only when you judge that document evidence can materially "
                "clarify the request or an unresolved artifact. Do not use it to "
                "choose an Agent or to invent operational facts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "A focused Korean search question derived from the "
                            "request or accumulated artifacts."
                        ),
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


def no_grounding_requested() -> dict[str, Any]:
    """Return the initial evidence record before the model requests a search."""
    return {
        "state": "not_requested",
        "repository_id": None,
        "document_ids": [],
        "evidence": "",
        "searches": [],
    }


def add_grounding_search(
    current: dict[str, Any], query: str, result: dict[str, Any]
) -> dict[str, Any]:
    """Accumulate tool observations without making a business decision in code."""
    searches = list(current.get("searches", []))
    searches.append({"query": query, "result": result})
    document_ids = list(current.get("document_ids", []))
    for document_id in result.get("document_ids", []):
        if isinstance(document_id, str) and document_id not in document_ids:
            document_ids.append(document_id)
    evidence_items = [
        f"Search query: {item['query']}\nEvidence: {item['result']['evidence']}"
        for item in searches
        if isinstance(item, dict)
        and isinstance(item.get("query"), str)
        and isinstance(item.get("result"), dict)
        and item["result"].get("state") == "grounded"
        and isinstance(item["result"].get("evidence"), str)
        and item["result"]["evidence"].strip()
    ]
    states = [
        item["result"].get("state")
        for item in searches
        if isinstance(item, dict) and isinstance(item.get("result"), dict)
    ]
    state = "grounded" if "grounded" in states else str(states[-1])
    return {
        "state": state,
        "repository_id": result.get("repository_id"),
        "document_ids": document_ids,
        "evidence": "\n\n".join(evidence_items),
        "searches": searches,
    }


def _sdk() -> dict[str, Any]:
    """Return the SDK types after the module-level optional import check."""
    if _SDK_IMPORT_ERROR is not None:
        raise RuntimeError(
            "sap-ai-sdk-gen이 없습니다. pip install -r requirements.txt를 실행하세요."
        ) from _SDK_IMPORT_ERROR
    return {
        "ModuleConfig": _ModuleConfig,
        "OrchestrationConfig": _OrchestrationConfig,
        "DocumentGroundingConfig": _DocumentGroundingConfig,
        "DocumentGroundingFilter": _DocumentGroundingFilter,
        "DocumentGroundingPlaceholders": _DocumentGroundingPlaceholders,
        "GroundingModuleConfig": _GroundingModuleConfig,
        "LLMModelDetails": _LLMModelDetails,
        "SystemMessage": _SystemMessage,
        "UserMessage": _UserMessage,
        "PromptTemplatingModuleConfig": _PromptTemplatingModuleConfig,
        "Template": _Template,
        "OrchestrationService": _OrchestrationService,
    }


def _document_id(document: dict[str, Any]) -> str:
    """Return the human-readable logical ID, preferring the source filename."""
    for item in document.get("metadata", []):
        if isinstance(item, dict) and item.get("key") == "id":
            values = item.get("value", [])
            if isinstance(values, list) and values:
                return str(values[0])
    value = document.get("id") or document.get("documentId")
    if value:
        return str(value)
    return ""


def _model_data(value: Any) -> Any:
    """Convert an SDK response fragment to ordinary nested Python values."""
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)):
        return list(value)
    return value


def _grounding_source_document_ids(
    response: Any, available_document_ids: list[str]
) -> list[str]:
    """Extract only filenames returned by the Grounding module as evidence.

    The repository list is deliberately not used as a proxy for retrieval: it can
    contain many documents that did not contribute to this answer.  Grounding
    response payloads vary slightly by SDK/service version, so inspect their
    nested metadata generically and retain only known logical document IDs.
    """
    found: list[str] = []

    def visit(value: Any) -> None:
        value = _model_data(value)
        if isinstance(value, str):
            for identifier in available_document_ids:
                if identifier and identifier in value and identifier not in found:
                    found.append(identifier)
            return
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
            return
        if isinstance(value, list):
            for child in value:
                visit(child)

    intermediate = getattr(response, "intermediate_results", None)
    grounding = getattr(intermediate, "grounding", None)
    visit(getattr(grounding, "data", None))
    visit(getattr(grounding, "message", None))
    final_result = getattr(response, "final_result", None)
    visit(getattr(final_result, "citations", None))
    return found


def _grounded_answer_with_sources(
    request: str,
    settings: Settings,
    repository_id: str,
    available_document_ids: list[str],
) -> tuple[str, list[str]]:
    """Ask the SAP BTP Grounding pipeline for evidence, not a workflow decision."""
    sdk = _sdk()
    apply_ai_core_environment(settings)
    grounding = sdk["GroundingModuleConfig"](
        config=sdk["DocumentGroundingConfig"](
            filters=[
                sdk["DocumentGroundingFilter"](
                    id="FnbA2ARepository",
                    data_repository_type="vector",
                    data_repositories=[repository_id],
                )
            ],
            placeholders=sdk["DocumentGroundingPlaceholders"](
                input=["user_query"], output="grounding_response"
            ),
            # Return the logical source ID with each retrieved chunk so the UI
            # can distinguish documents actually used from all repository files.
            metadata_params=["id"],
        )
    )
    prompt = sdk["PromptTemplatingModuleConfig"](
        prompt=sdk["Template"](
            template=[
                sdk["SystemMessage"](
                    content=(
                        "Extract concise Korean evidence for a downstream enterprise "
                        "orchestration decision. Use only the provided document context. "
                        "Do not choose agents, recommend a workflow, or add facts. "
                        "If the context has no relevant evidence, reply exactly: "
                        "제공된 문서에서 관련 근거를 찾지 못했습니다."
                    )
                ),
                sdk["UserMessage"](
                    content=(
                        "Field request: {{?user_query}}\n"
                        "Grounding context: {{?grounding_response}}"
                    )
                ),
            ]
        ),
        model=sdk["LLMModelDetails"](
            name=settings.llm_model, params=llm_model_params(settings, max_tokens=900)
        ),
    )
    config = sdk["OrchestrationConfig"](
        modules=sdk["ModuleConfig"](prompt_templating=prompt, grounding=grounding)
    )
    service = sdk["OrchestrationService"](
        api_url=orchestration_url(settings), config=config
    )
    response = service.run(placeholder_values={"user_query": request})
    answer = str(response.final_result.choices[0].message.content or "").strip()
    return answer, _grounding_source_document_ids(response, available_document_ids)


def _grounded_answer(request: str, settings: Settings, repository_id: str) -> str:
    """Compatibility wrapper for callers that only need the evidence text."""
    answer, _ = _grounded_answer_with_sources(request, settings, repository_id, [])
    return answer


def collect_grounding_context(
    request: str,
    settings: Settings,
    *,
    repository_id: str | None = None,
) -> dict[str, Any]:
    """Return auditable vector-Grounding evidence for a single A2A request.

    A missing repository or an empty repository is a normal setup state while
    manuals are being prepared.  A configured repository that cannot be read
    is deliberately allowed to fail so the workflow does not claim grounding
    that never occurred.
    """
    cleaned_request = request.strip()
    if not cleaned_request:
        raise ValueError("Grounding할 현장 요청을 입력하세요.")
    repository = (repository_id or os.getenv(GROUNDING_REPOSITORY_ENV, "")).strip()
    if not repository:
        return {
            "state": "not_configured",
            "repository_id": None,
            "document_ids": [],
            "evidence": "",
        }

    documents = list_documents(settings, repository)
    document_ids = [
        identifier for document in documents if (identifier := _document_id(document))
    ]
    if not documents:
        return {
            "state": "empty_repository",
            "repository_id": repository,
            "document_ids": [],
            "evidence": "",
        }

    evidence, source_document_ids = _grounded_answer_with_sources(
        cleaned_request, settings, repository, document_ids
    )
    result = {
        "state": "grounded" if evidence else "no_result",
        "repository_id": repository,
        "document_ids": source_document_ids,
        "available_document_count": len(document_ids),
        "evidence": evidence,
    }
    return result


def grounding_audit(context: dict[str, Any]) -> dict[str, Any]:
    """Return safe, compact grounding metadata for events and middleware logs."""
    document_ids = context.get("document_ids", [])
    available_document_count = context.get("available_document_count")
    return {
        "state": context.get("state"),
        "repository_id": context.get("repository_id"),
        "document_count": (
            available_document_count
            if isinstance(available_document_count, int)
            else len(document_ids)
            if isinstance(document_ids, list)
            else 0
        ),
        "document_ids": document_ids if isinstance(document_ids, list) else [],
    }
