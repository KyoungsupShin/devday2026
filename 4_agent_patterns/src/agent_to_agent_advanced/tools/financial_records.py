"""Read cost-driver, business outlook, and financial-control records."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_cost_driver_evidence(context_id: Any) -> dict[str, Any]:
    """Read cost-driver and unit-economics scenario evidence."""
    return lookup_context_records(
        context_id,
        lookup="cost_driver_evidence",
        snapshots=(
            "product_bom",
            "exchange_rate",
            "material_price",
            "product_cost_assumption",
        ),
    )


def lookup_business_outlook_evidence(context_id: Any) -> dict[str, Any]:
    """Read demand, revenue, and planning-horizon scenario evidence."""
    return lookup_context_records(
        context_id,
        lookup="business_outlook_evidence",
        snapshots=("product", "sales_forecast"),
    )


def lookup_financial_control_evidence(context_id: Any) -> dict[str, Any]:
    """Read budget, approval, Cost Center, and transfer-control evidence."""
    return lookup_context_records(
        context_id,
        lookup="financial_control_evidence",
        snapshots=(
            "opex_budget",
            "approval",
            "cost_center",
            "budget_commitment",
            "material_budget",
            "cost_center_change",
            "budget_transfer",
        ),
    )
