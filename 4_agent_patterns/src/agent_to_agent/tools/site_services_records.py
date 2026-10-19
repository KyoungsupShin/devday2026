"""Read site service, non-production asset, and access-support records."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_general_affairs_evidence(context_id: Any) -> dict[str, Any]:
    """Read site-service, asset, and access-support evidence."""
    return lookup_context_records(
        context_id,
        lookup="general_affairs_evidence",
        snapshots=("general_affairs",),
    )
