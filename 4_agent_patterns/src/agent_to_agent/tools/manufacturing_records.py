"""Read production planning and material-onboarding records."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_production_context(context_id: Any) -> dict[str, Any]:
    """Read product, BOM, production-plan, and material-demand evidence."""
    return lookup_context_records(
        context_id,
        lookup="production_context",
        snapshots=(
            "product",
            "product_bom",
            "production_plan",
            "material_requirement",
        ),
    )


def lookup_material_intake_context(context_id: Any) -> dict[str, Any]:
    """Read new-material registration and intake-readiness evidence."""
    return lookup_context_records(
        context_id,
        lookup="material_intake_context",
        snapshots=(
            "mdm",
            "material_intake",
            "bom_change",
            "quality_release",
            "production_plan",
        ),
    )
