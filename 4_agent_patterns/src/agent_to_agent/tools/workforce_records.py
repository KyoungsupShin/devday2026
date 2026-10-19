"""Read workforce, qualification, attendance, and labor-control records."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_hr_workforce_evidence(context_id: Any) -> dict[str, Any]:
    """Read workforce, qualification, and attendance-control evidence."""
    return lookup_context_records(
        context_id, lookup="hr_workforce_evidence", snapshots=("hr",)
    )
