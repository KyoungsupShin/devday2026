"""Read quality-system, testing, and release-readiness records."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_quality_evidence(context_id: Any) -> dict[str, Any]:
    """Read quality-system, testing, and release-readiness evidence."""
    return lookup_context_records(
        context_id, lookup="quality_evidence", snapshots=("quality",)
    )
