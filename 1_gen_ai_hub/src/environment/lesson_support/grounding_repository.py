"""Read-only client for AI Core vector Grounding repositories."""
from __future__ import annotations

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


