"""Small REST client for AI Core vector Grounding repositories.

The Grounding API stores documents as text chunks, not as binary file objects.
This module intentionally supports UTF-8 text and Markdown so the notebook can
make the conversion explicit and keep document management easy to audit.
"""
from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

import requests

from .ai_core import api_headers
from .config import Settings


def _documents_url(settings: Settings, repository_id: str) -> str:
    settings.require_ai_core()
    cleaned_id = repository_id.strip()
    if not cleaned_id:
        raise ValueError("Grounding repository ID를 입력하세요.")
    base_url = settings.base_url.rstrip("/")
    return f"{base_url}/v2/lm/document-grounding/vector/collections/{quote(cleaned_id, safe='')}/documents"


def _chunks(text: str, chunk_size: int = 3_000) -> list[str]:
    """Split text on paragraph boundaries, then on a safe character limit."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("비어 있는 문서는 업로드할 수 없습니다.")
    if chunk_size < 1:
        raise ValueError("chunk_size는 1 이상이어야 합니다.")

    chunks: list[str] = []
    current = ""
    for paragraph in cleaned.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        candidate = f"{current}\n\n{paragraph}".strip()
        if current and len(candidate) > chunk_size:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
        while len(current) > chunk_size:
            chunks.append(current[:chunk_size])
            current = current[chunk_size:]
    if current:
        chunks.append(current)
    return chunks


def list_documents(settings: Settings, repository_id: str) -> list[dict[str, Any]]:
    """Return document resources currently registered in a vector repository."""
    response = requests.get(_documents_url(settings, repository_id), headers=api_headers(settings), timeout=30)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        resources = payload.get("resources", payload.get("documents", []))
    else:
        resources = payload
    return [item for item in resources if isinstance(item, dict)]


def upload_text_document(
    settings: Settings,
    repository_id: str,
    *,
    filename: str,
    text: str,
    document_id: str | None = None,
    metadata: Mapping[str, str | Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Upload one text/Markdown document to a vector repository.

    ``metadata`` is retained on both the document and its chunks so callers can
    preserve an auditable source location (for example an Object Storage key).
    """
    name = Path(filename).name.strip()
    if not name:
        raise ValueError("파일 이름이 필요합니다.")
    identifier = (document_id or name).strip()
    if not identifier:
        raise ValueError("document ID가 필요합니다.")

    source_metadata: list[dict[str, list[str]]] = []
    for key, raw_value in (metadata or {}).items():
        cleaned_key = str(key).strip()
        if not cleaned_key or cleaned_key == "id":
            continue
        values = [str(value).strip() for value in (raw_value if isinstance(raw_value, Sequence) and not isinstance(raw_value, str) else [raw_value])]
        values = [value for value in values if value]
        if values:
            source_metadata.append({"key": cleaned_key, "value": values})
    document_chunks = [
        {
            "content": content,
            "metadata": [{"key": "chunk_index", "value": [str(index)]}, *source_metadata],
        }
        for index, content in enumerate(_chunks(text), start=1)
    ]
    body = {
        "documents": [{
            "metadata": [{"key": "id", "value": [identifier]}, *source_metadata],
            "chunks": document_chunks,
        }]
    }
    response = requests.post(
        _documents_url(settings, repository_id), headers=api_headers(settings), json=body, timeout=60
    )
    response.raise_for_status()
    return response.json() if response.content else {}


def delete_document(settings: Settings, repository_id: str, document_id: str) -> None:
    """Permanently delete one document, identified by the API's document ID."""
    cleaned_id = document_id.strip()
    if not cleaned_id:
        raise ValueError("삭제할 document ID를 선택하세요.")
    response = requests.delete(
        f"{_documents_url(settings, repository_id)}/{quote(cleaned_id, safe='')}",
        headers=api_headers(settings),
        timeout=30,
    )
    response.raise_for_status()
