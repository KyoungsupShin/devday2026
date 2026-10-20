"""Replace one F&B SOP in Vector Grounding for the A2A notebook lesson."""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lab_common.config import Settings, load_settings
from lab_common.grounding_repository import (
    delete_document,
    list_documents,
    upload_text_document,
)

_PROCESS_HEADING = "## 프로세스"
_STAKEHOLDER_HEADING = "\n## Stakeholder와 책임"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOP_SOURCE_PATH = (
    PROJECT_ROOT / "data" / "context" / "interdepartmental_collaboration_sop.md"
)


@dataclass
class SopGroundingReplacement:
    """The in-memory source and remote identity needed for one reversible swap."""

    settings: Settings
    repository_id: str
    source_path: Path
    filename: str
    original_text: str
    revised_text: str
    original_resource_id: str
    active: bool = False


def _logical_document_id(document: dict[str, Any]) -> str:
    for metadata in document.get("metadata", []):
        if not isinstance(metadata, dict) or metadata.get("key") != "id":
            continue
        values = metadata.get("value", [])
        if isinstance(values, list) and values:
            return str(values[0])
    return ""


def _resource_id(document: dict[str, Any]) -> str:
    return str(document.get("id") or document.get("documentId") or "").strip()


def _unique_document(
    settings: Settings, repository_id: str, filename: str
) -> dict[str, Any]:
    matches = [
        document
        for document in list_documents(settings, repository_id)
        if _logical_document_id(document) == filename
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"{filename} metadata 문서를 정확히 하나 찾아야 교체할 수 있습니다. "
            f"현재 {len(matches)}개입니다."
        )
    document = matches[0]
    if not _resource_id(document):
        raise RuntimeError("교체할 SOP의 Grounding resource ID를 확인할 수 없습니다.")
    return document


def _revised_text(original_text: str, revised_process: str) -> str:
    cleaned_process = revised_process.strip()
    if not cleaned_process.startswith(_PROCESS_HEADING):
        raise ValueError(f"수정 SOP는 {_PROCESS_HEADING} 제목으로 시작해야 합니다.")
    try:
        process_start = original_text.index(_PROCESS_HEADING)
        stakeholder_start = original_text.index(_STAKEHOLDER_HEADING)
    except ValueError as error:
        raise ValueError("원본 SOP에서 프로세스 또는 Stakeholder 구간을 찾지 못했습니다.") from error
    return (
        original_text[:process_start]
        + cleaned_process
        + "\n"
        + original_text[stakeholder_start:]
    )


def prepare_sop_replacement(
    settings: Settings,
    source_path: str | Path,
    revised_process: str,
    *,
    repository_id: str | None = None,
    restore_process: str | None = None,
) -> SopGroundingReplacement:
    """Build a reversible SOP swap without changing local or remote state."""
    repository = (repository_id or os.getenv("GROUNDING_REPOSITORY_ID", "")).strip()
    if not repository:
        raise RuntimeError(
            "GROUNDING_REPOSITORY_ID가 없습니다. 교육용 Vector Grounding repository를 .env에 설정하세요."
        )
    path = Path(source_path)
    source_text = path.read_text(encoding="utf-8")
    filename = path.name
    document = _unique_document(settings, repository, filename)
    return SopGroundingReplacement(
        settings=settings,
        repository_id=repository,
        source_path=path,
        filename=filename,
        original_text=(
            _revised_text(source_text, restore_process)
            if restore_process is not None
            else source_text
        ),
        revised_text=_revised_text(source_text, revised_process),
        original_resource_id=_resource_id(document),
    )


def prepare_default_sop_replacement(
    revised_process: str, restore_process: str | None = None
) -> SopGroundingReplacement:
    """Prepare the standard F&B A2A SOP swap used by notebook 03."""
    return prepare_sop_replacement(
        load_settings(),
        DEFAULT_SOP_SOURCE_PATH,
        revised_process,
        restore_process=restore_process,
    )


def preview_sop_replacement(change: SopGroundingReplacement) -> str:
    """Return a unified diff suitable for a notebook display."""
    return "\n".join(
        difflib.unified_diff(
            change.original_text.splitlines(),
            change.revised_text.splitlines(),
            fromfile="복구할 SOP",
            tofile="업로드할 수정 SOP",
            lineterm="",
        )
    )


def replace_sop(change: SopGroundingReplacement) -> dict[str, Any]:
    """Swap the current SOP for the revised text and recover the original on failure."""
    if change.active:
        raise RuntimeError("이 노트북 세션에서는 이미 수정 SOP가 활성화되어 있습니다.")
    delete_document(change.settings, change.repository_id, change.original_resource_id)
    try:
        result = upload_text_document(
            change.settings,
            change.repository_id,
            filename=change.filename,
            text=change.revised_text,
        )
    except Exception:
        upload_text_document(
            change.settings,
            change.repository_id,
            filename=change.filename,
            text=change.original_text,
        )
        raise
    change.active = True
    return result


def restore_sop(change: SopGroundingReplacement) -> dict[str, Any]:
    """Restore the original text after the notebook's revised-SOP demonstration."""
    if not change.active:
        raise RuntimeError("현재 노트북 세션에서 수정 SOP를 교체한 뒤에만 원본을 복구할 수 있습니다.")
    current_document = _unique_document(
        change.settings, change.repository_id, change.filename
    )
    current_resource_id = _resource_id(current_document)
    delete_document(change.settings, change.repository_id, current_resource_id)
    try:
        result = upload_text_document(
            change.settings,
            change.repository_id,
            filename=change.filename,
            text=change.original_text,
        )
    except Exception:
        upload_text_document(
            change.settings,
            change.repository_id,
            filename=change.filename,
            text=change.revised_text,
        )
        raise
    change.active = False
    return result
