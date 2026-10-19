"""Read rows from the local CSV snapshots used by A2A Tools.

This module only resolves file locations and reads CSV rows.  It never
interprets a business record, selects an Agent, or changes external state.
"""

from __future__ import annotations

import csv
from pathlib import Path

DATA_DIRECTORY = Path(__file__).parent.parent / "data" / "hana_raw"
SNAPSHOT_PATHS = {
    "business_context": DATA_DIRECTORY / "business_context.csv",
    "equipment": DATA_DIRECTORY / "equipment_master.csv",
    "maintenance": DATA_DIRECTORY / "maintenance_work_order.csv",
    "bom": DATA_DIRECTORY / "equipment_bom.csv",
    "mdm": DATA_DIRECTORY / "material_mdm.csv",
    "stock": DATA_DIRECTORY / "material_stock.csv",
    "source": DATA_DIRECTORY / "purchase_source.csv",
    "quote": DATA_DIRECTORY / "purchase_quote.csv",
    "opex_budget": DATA_DIRECTORY / "opex_budget.csv",
    "cost_center": DATA_DIRECTORY / "cost_center_master.csv",
    "approval": DATA_DIRECTORY / "approval_matrix.csv",
    "budget_transfer": DATA_DIRECTORY / "budget_transfer_request.csv",
    "erp_change": DATA_DIRECTORY / "erp_change_request.csv",
    "product": DATA_DIRECTORY / "product_master.csv",
    "product_bom": DATA_DIRECTORY / "product_bom.csv",
    "production_plan": DATA_DIRECTORY / "production_plan.csv",
    "material_requirement": DATA_DIRECTORY / "material_requirement.csv",
    "purchase_requisition": DATA_DIRECTORY / "purchase_requisition.csv",
    "open_purchase_schedule": DATA_DIRECTORY / "open_purchase_schedule.csv",
    "exchange_rate": DATA_DIRECTORY / "exchange_rate_scenario.csv",
    "material_price": DATA_DIRECTORY / "material_price_snapshot.csv",
    "product_cost_assumption": DATA_DIRECTORY / "product_cost_assumption.csv",
    "material_intake": DATA_DIRECTORY / "material_intake_request.csv",
    "bom_change": DATA_DIRECTORY / "bom_change_request.csv",
    "quality_release": DATA_DIRECTORY / "quality_release_status.csv",
    "cost_center_change": DATA_DIRECTORY / "cost_center_change_request.csv",
    "budget_commitment": DATA_DIRECTORY / "budget_commitment.csv",
    "material_budget": DATA_DIRECTORY / "material_purchase_budget.csv",
    "supplier": DATA_DIRECTORY / "supplier_master.csv",
    "material_planning": DATA_DIRECTORY / "material_planning_parameter.csv",
    "sales_forecast": DATA_DIRECTORY / "sales_forecast.csv",
    "erp_mapping": DATA_DIRECTORY / "erp_data_mapping.csv",
    "ehs": DATA_DIRECTORY / "ehs_evidence.csv",
    "hr": DATA_DIRECTORY / "hr_workforce_evidence.csv",
    "general_affairs": DATA_DIRECTORY / "general_affairs_evidence.csv",
    "process": DATA_DIRECTORY / "process_evidence.csv",
    "rnd": DATA_DIRECTORY / "rnd_evidence.csv",
    "production": DATA_DIRECTORY / "production_evidence.csv",
    "quality": DATA_DIRECTORY / "quality_evidence.csv",
}


def snapshot_path(snapshot_name: str) -> Path:
    """Return the registered path for one named local snapshot."""
    try:
        return SNAPSHOT_PATHS[snapshot_name]
    except KeyError as error:
        raise ValueError(
            f"알 수 없는 CSV 스냅샷 유형입니다: {snapshot_name}"
        ) from error


def display_path(path: Path) -> str:
    """Return paths relative to the agent package whenever possible."""
    try:
        return str(path.relative_to(Path(__file__).parent.parent))
    except ValueError:
        return str(path)


def read_rows(snapshot_name: str) -> tuple[str, list[dict[str, str]], str]:
    """Read all rows from one local CSV snapshot."""
    path = snapshot_path(snapshot_name)
    path_display = display_path(path)
    if not path.is_file():
        return "snapshot_missing", [], path_display
    with path.open(newline="", encoding="utf-8") as handle:
        return "found", list(csv.DictReader(handle)), path_display


def filter_rows(
    snapshot_name: str, *, field: str, value: str
) -> tuple[str, list[dict[str, str]], str]:
    """Return rows whose field exactly matches the supplied registered value."""
    state, rows, path = read_rows(snapshot_name)
    if state != "found":
        return state, rows, path
    records = [row for row in rows if row.get(field, "").strip() == value]
    return ("found" if records else "no_match"), records, path
