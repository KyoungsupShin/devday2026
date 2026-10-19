"""Read process engineering, performance, and validation records."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_process_evidence(context_id: Any) -> dict[str, Any]:
    """Read process engineering, performance, and validation evidence."""
    return lookup_context_records(
        context_id, lookup="process_evidence", snapshots=("process",)
    )
