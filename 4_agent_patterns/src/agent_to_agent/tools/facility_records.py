"""Read equipment, maintenance, and equipment-BOM records."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_facility_context(context_id: Any) -> dict[str, Any]:
    """Read equipment, maintenance, and equipment-BOM evidence."""
    return lookup_context_records(
        context_id,
        lookup="facility_context",
        snapshots=("equipment", "maintenance", "bom"),
    )
