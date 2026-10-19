"""Read ERP change-request and data-mapping readiness records."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_erp_readiness_evidence(context_id: Any) -> dict[str, Any]:
    """Read ERP mapping and documented-change evidence."""
    return lookup_context_records(
        context_id,
        lookup="erp_readiness_evidence",
        snapshots=("erp_change", "erp_mapping"),
    )
