"""SAP BTP vector-Grounding evidence for the F&B A2A workflow.

The Grounding service enriches the LLM decision record; it never selects an
Agent or performs an A2A handoff.  Team and Sub-agent selection remains an
LLM decision in the orchestration layer.
"""

from __future__ import annotations

import os
from typing import Any

from lab_common.ai_core import (
    apply_ai_core_environment,
    llm_model_params,
    orchestration_url,
)
from lab_common.config import Settings
from lab_common.grounding_repository import list_documents

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
MAX_RUNTIME_GROUNDING_OVERLAY_CHARS = 1_600


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
    value = document.get("id") or document.get("documentId")
    if value:
        return str(value)
    for item in document.get("metadata", []):
        if isinstance(item, dict) and item.get("key") == "id":
            values = item.get("value", [])
            if isinstance(values, list) and values:
                return str(values[0])
    return ""


def _validated_runtime_overlay(value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError("Grounding runtime overlay는 문자열이어야 합니다.")
    overlay = value.strip()
    if len(overlay) > MAX_RUNTIME_GROUNDING_OVERLAY_CHARS:
        raise ValueError(
            f"Grounding runtime overlay는 {MAX_RUNTIME_GROUNDING_OVERLAY_CHARS}자 이하여야 합니다."
        )
    return overlay


def _grounded_answer(
    request: str,
    settings: Settings,
    repository_id: str,
    runtime_overlay: str = "",
) -> str:
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
        )
    )
    overlay_note = (
        "\n\nHuman-approved runtime retrieval focus:\n"
        f"{runtime_overlay}\n"
        "Treat this only as a focus for finding and summarising repository evidence. "
        "It is not document evidence and must not create facts."
        if runtime_overlay
        else ""
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
                        + overlay_note
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
    return str(response.final_result.choices[0].message.content or "").strip()


def collect_grounding_context(
    request: str,
    settings: Settings,
    *,
    repository_id: str | None = None,
    runtime_overlay: str | None = None,
) -> dict[str, Any]:
    """Return auditable vector-Grounding evidence for a single A2A request.

    A missing repository or an empty repository is a normal setup state while
    manuals are being prepared.  A configured repository that cannot be read
    is deliberately allowed to fail so the workflow does not claim grounding
    that never occurred.
    """
    cleaned_request = request.strip()
    overlay = _validated_runtime_overlay(runtime_overlay)
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

    evidence = _grounded_answer(cleaned_request, settings, repository, overlay)
    result = {
        "state": "grounded" if evidence else "no_result",
        "repository_id": repository,
        "document_ids": document_ids,
        "evidence": evidence,
        "runtime_overlay_applied": bool(overlay),
    }
    return result


def grounding_audit(context: dict[str, Any]) -> dict[str, Any]:
    """Return safe, compact grounding metadata for events and middleware logs."""
    document_ids = context.get("document_ids", [])
    return {
        "state": context.get("state"),
        "repository_id": context.get("repository_id"),
        "document_count": len(document_ids) if isinstance(document_ids, list) else 0,
        "document_ids": document_ids if isinstance(document_ids, list) else [],
        "runtime_overlay_applied": bool(context.get("runtime_overlay_applied")),
    }
