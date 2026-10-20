"""Read purchasing and supply records for a registered business Context."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_procurement_evidence(context_id: Any) -> dict[str, Any]:
    """Read sourcing and purchasing-record evidence."""
    return lookup_context_records(
        context_id,
        lookup="procurement_evidence",
        snapshots=(
            "mdm",
            "source",
            "supplier",
            "quote",
            "purchase_requisition",
            "open_purchase_schedule",
            "approval",
        ),
    )


def lookup_supply_evidence(context_id: Any) -> dict[str, Any]:
    """Read availability, demand, and inbound-supply evidence."""
    return lookup_context_records(
        context_id,
        lookup="supply_evidence",
        snapshots=(
            "stock",
            "material_requirement",
            "open_purchase_schedule",
            "material_planning",
        ),
    )
