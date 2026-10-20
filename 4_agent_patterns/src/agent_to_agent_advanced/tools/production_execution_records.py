"""Read production execution, line-operation, and traceability records."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_production_execution_evidence(context_id: Any) -> dict[str, Any]:
    """Read production execution, line operation, and traceability evidence."""
    return lookup_context_records(
        context_id,
        lookup="production_execution_evidence",
        snapshots=("production",),
    )
