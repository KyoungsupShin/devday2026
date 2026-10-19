"""Read safety, environment, chemical, and work-permit records."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_ehs_evidence(context_id: Any) -> dict[str, Any]:
    """Read worker-safety, environmental, and work-permit evidence."""
    return lookup_context_records(context_id, lookup="ehs_evidence", snapshots=("ehs",))
