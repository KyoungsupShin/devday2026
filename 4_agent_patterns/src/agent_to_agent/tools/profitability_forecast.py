"""Calculate read-only monthly and quarterly profitability scenarios."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from .context_records import context_record, related_rows


def _decimal_value(
    row: dict[str, str], field: str, errors: list[str], source: str
) -> Decimal | None:
    value = row.get(field, "").strip()
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        errors.append(f"invalid_numeric:{source}.{field}")
        return None
    if parsed <= 0:
        errors.append(f"non_positive_value:{source}.{field}")
        return None
    return parsed


def _rounded_krw(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _rounded_ratio_percent(numerator: Decimal, denominator: Decimal) -> float:
    return float(
        (numerator * Decimal(100) / denominator).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )


def _ceiling_units(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _profitability_error(
    context_id: str, errors: list[str], paths: dict[str, str]
) -> dict[str, Any]:
    return {
        "source": "hana_csv_snapshot_calculation",
        "lookup": "profitability_scenarios",
        "state": "insufficient_input",
        "message": (
            "수익성 계산에 필요한 CSV 입력이 누락되었거나 일관되지 않습니다. "
            "임의 보정 없이 계산을 중단했습니다."
        ),
        "context_id": context_id,
        "errors": list(dict.fromkeys(errors)),
        "related_snapshot_paths": paths,
        "snapshot_boundary": (
            "실시간 SAP HANA 조회가 아닌 로컬 CSV 스냅샷을 사용한 읽기 전용 계산입니다."
        ),
        "write_performed": False,
    }


def calculate_profitability_scenarios(context_id: Any) -> dict[str, Any]:
    """Calculate scenario COGS, BEP, and monthly/quarterly profitability.

    The calculation only combines records linked to the registered Context. It
    does not choose an Agent, workflow, or substitute missing inputs.
    """
    context, error = context_record(context_id)
    if error:
        error.update(
            {
                "source": "hana_csv_snapshot_calculation",
                "lookup": "profitability_scenarios",
                "write_performed": False,
            }
        )
        return error

    assert context is not None
    context_id_value = context["CONTEXT_ID"]
    product_id = context.get("PRODUCT_ID", "").strip()
    if not product_id:
        return _profitability_error(
            context_id_value, ["missing_context_product_id"], {}
        )

    snapshots = (
        "product_bom",
        "exchange_rate",
        "material_price",
        "product_cost_assumption",
        "sales_forecast",
    )
    records_by_snapshot: dict[str, list[dict[str, str]]] = {}
    paths: dict[str, str] = {}
    errors: list[str] = []
    for snapshot_name in snapshots:
        state, records, path = related_rows(snapshot_name, context)
        paths[snapshot_name] = path
        records_by_snapshot[snapshot_name] = records if state == "found" else []
        if state != "found":
            errors.append(f"missing_input:{snapshot_name}")

    bom_rows = [
        row
        for row in records_by_snapshot["product_bom"]
        if row.get("PRODUCT_ID", "").strip() == product_id
    ]
    sales_rows = [
        row
        for row in records_by_snapshot["sales_forecast"]
        if row.get("PRODUCT_ID", "").strip() == product_id
    ]
    assumption_rows = [
        row
        for row in records_by_snapshot["product_cost_assumption"]
        if row.get("PRODUCT_ID", "").strip() == product_id
    ]
    if not bom_rows:
        errors.append("missing_input:product_bom_for_context_product")
    if not sales_rows:
        errors.append("missing_input:sales_forecast_for_context_product")
    if not assumption_rows:
        errors.append("missing_input:product_cost_assumption_for_context_product")
    for snapshot_name, rows in records_by_snapshot.items():
        if any(row.get("DATA_SCOPE", "").strip() != "LOCAL_SNAPSHOT" for row in rows):
            errors.append(f"invalid_scope:{snapshot_name}")

    bom_by_material: dict[str, tuple[Decimal, str]] = {}
    for row in bom_rows:
        material = row.get("COMPONENT_MATERIAL", "").strip()
        unit = row.get("UNIT", "").strip()
        quantity = _decimal_value(row, "QUANTITY_PER_BASE_UNIT", errors, "product_bom")
        if not material or not unit:
            errors.append(
                "missing_required_field:product_bom.component_material_or_unit"
            )
        elif material in bom_by_material:
            errors.append(f"duplicate_input:product_bom.{material}")
        elif quantity is not None:
            bom_by_material[material] = (quantity, unit)

    sales_by_period: dict[str, tuple[Decimal, Decimal]] = {}
    for row in sales_rows:
        period = row.get("FORECAST_PERIOD", "").strip()
        quantity = _decimal_value(row, "FORECAST_QUANTITY", errors, "sales_forecast")
        revenue = _decimal_value(
            row, "FORECAST_NET_SALES_KRW", errors, "sales_forecast"
        )
        if row.get("UNIT", "").strip() != "EA":
            errors.append(f"unit_mismatch:sales_forecast.{period}")
        if row.get("CURRENCY", "").strip() != "KRW":
            errors.append(f"currency_mismatch:sales_forecast.{period}")
        if not period:
            errors.append("missing_required_field:sales_forecast.forecast_period")
        elif period in sales_by_period:
            errors.append(f"duplicate_input:sales_forecast.{period}")
        elif quantity is not None and revenue is not None:
            sales_by_period[period] = (quantity, revenue)

    assumptions_by_period: dict[str, tuple[Decimal, Decimal]] = {}
    for row in assumption_rows:
        period = row.get("FORECAST_PERIOD", "").strip()
        variable_cost = _decimal_value(
            row, "NON_FX_VARIABLE_COGS_KRW_PER_EA", errors, "product_cost_assumption"
        )
        fixed_cost = _decimal_value(
            row, "FIXED_MANUFACTURING_COST_KRW", errors, "product_cost_assumption"
        )
        if row.get("CURRENCY", "").strip() != "KRW":
            errors.append(f"currency_mismatch:product_cost_assumption.{period}")
        if not period:
            errors.append(
                "missing_required_field:product_cost_assumption.forecast_period"
            )
        elif period in assumptions_by_period:
            errors.append(f"duplicate_input:product_cost_assumption.{period}")
        elif variable_cost is not None and fixed_cost is not None:
            assumptions_by_period[period] = (variable_cost, fixed_cost)

    periods = sorted(sales_by_period)
    if set(periods) != set(assumptions_by_period):
        errors.append("period_mismatch:sales_forecast_and_product_cost_assumption")

    rates_by_key: dict[tuple[str, str, str], Decimal] = {}
    scenario_order: dict[str, int] = {}
    for row in records_by_snapshot["exchange_rate"]:
        scenario = row.get("SCENARIO", "").strip()
        period = row.get("FORECAST_PERIOD", "").strip()
        from_currency = row.get("FROM_CURRENCY", "").strip()
        to_currency = row.get("TO_CURRENCY", "").strip()
        rate = _decimal_value(row, "EXCHANGE_RATE", errors, "exchange_rate")
        key = (scenario, period, from_currency)
        if not scenario or not period or not from_currency or to_currency != "KRW":
            errors.append("missing_or_invalid_currency:exchange_rate")
            continue
        if key in rates_by_key:
            errors.append(
                f"duplicate_input:exchange_rate.{scenario}.{period}.{from_currency}"
            )
            continue
        try:
            order = int(row.get("SCENARIO_ORDER", "").strip())
        except ValueError:
            errors.append(f"invalid_scenario_order:exchange_rate.{scenario}")
            continue
        if scenario in scenario_order and scenario_order[scenario] != order:
            errors.append(f"inconsistent_scenario_order:{scenario}")
        scenario_order[scenario] = order
        if rate is not None:
            rates_by_key[key] = rate

    prices_by_key: dict[tuple[str, str, str], tuple[Decimal, str, str]] = {}
    for row in records_by_snapshot["material_price"]:
        scenario = row.get("SCENARIO", "").strip()
        period = row.get("FORECAST_PERIOD", "").strip()
        material = row.get("MATERIAL", "").strip()
        currency = row.get("CURRENCY", "").strip()
        unit = row.get("UNIT", "").strip()
        price = _decimal_value(row, "UNIT_PRICE", errors, "material_price")
        key = (scenario, period, material)
        if not scenario or not period or not material or not currency or not unit:
            errors.append("missing_required_field:material_price")
        elif key in prices_by_key:
            errors.append(
                f"duplicate_input:material_price.{scenario}.{period}.{material}"
            )
        elif price is not None:
            prices_by_key[key] = (price, currency, unit)

    scenarios = sorted(scenario_order, key=lambda name: (scenario_order[name], name))
    if not scenarios:
        errors.append("missing_input:exchange_rate_scenarios")
    if set(scenario_order) != {key[0] for key in prices_by_key}:
        errors.append("scenario_mismatch:exchange_rate_and_material_price")
    for scenario in scenarios:
        for period in periods:
            for material, (_, bom_unit) in bom_by_material.items():
                price_record = prices_by_key.get((scenario, period, material))
                if price_record is None:
                    errors.append(
                        f"missing_input:material_price.{scenario}.{period}.{material}"
                    )
                    continue
                _, currency, price_unit = price_record
                if price_unit != bom_unit:
                    errors.append(
                        f"unit_mismatch:product_bom_and_material_price.{material}"
                    )
                if (scenario, period, currency) not in rates_by_key:
                    errors.append(
                        f"currency_mismatch:material_price_and_exchange_rate.{scenario}.{period}.{material}"
                    )
    if errors:
        return _profitability_error(context_id_value, errors, paths)

    monthly_forecasts: list[dict[str, Any]] = []
    scenario_summaries: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_rows: list[dict[str, Any]] = []
        for period in periods:
            quantity, revenue = sales_by_period[period]
            non_fx_variable_cost, fixed_cost = assumptions_by_period[period]
            foreign_material_cost = Decimal(0)
            prices: list[Decimal] = []
            rates: list[Decimal] = []
            for material, (bom_quantity, _) in bom_by_material.items():
                price, currency, _ = prices_by_key[(scenario, period, material)]
                rate = rates_by_key[(scenario, period, currency)]
                foreign_material_cost += bom_quantity * price * rate
                prices.append(price)
                rates.append(rate)
            unit_cogs = Decimal(
                _rounded_krw(foreign_material_cost + non_fx_variable_cost)
            )
            unit_price = revenue / quantity
            contribution = unit_price - unit_cogs
            if contribution <= 0:
                return _profitability_error(
                    context_id_value,
                    [f"non_positive_contribution_margin:{scenario}.{period}"],
                    paths,
                )
            total_cost = unit_cogs * quantity + fixed_cost
            profit = revenue - total_cost
            row = {
                "scenario": scenario,
                "scenario_order": scenario_order[scenario],
                "forecast_period": period,
                "exchange_rate_krw_per_usd": _rounded_krw(sum(rates) / len(rates)),
                "material_price_usd_per_kg": float(
                    (sum(prices) / len(prices)).quantize(Decimal("0.01"))
                ),
                "forecast_quantity_ea": int(quantity),
                "unit_net_price_krw": _rounded_krw(unit_price),
                "unit_cogs_krw": int(unit_cogs),
                "total_cost_krw": _rounded_krw(total_cost),
                "revenue_krw": _rounded_krw(revenue),
                "operating_profit_krw": _rounded_krw(profit),
                "operating_margin_pct": _rounded_ratio_percent(profit, revenue),
                "bep_quantity_ea": _ceiling_units(fixed_cost / contribution),
                "bep_revenue_krw": _rounded_krw(
                    Decimal(_ceiling_units(fixed_cost / contribution)) * unit_price
                ),
            }
            scenario_rows.append(row)
            monthly_forecasts.append(row)

        total_quantity = sum(
            Decimal(row["forecast_quantity_ea"]) for row in scenario_rows
        )
        total_revenue = sum(Decimal(row["revenue_krw"]) for row in scenario_rows)
        total_cost = sum(Decimal(row["total_cost_krw"]) for row in scenario_rows)
        total_fixed_cost = sum(assumptions_by_period[period][1] for period in periods)
        total_variable_cost = total_cost - total_fixed_cost
        total_profit = total_revenue - total_cost
        contribution_per_ea = (total_revenue - total_variable_cost) / total_quantity
        if contribution_per_ea <= 0:
            return _profitability_error(
                context_id_value,
                [f"non_positive_quarter_contribution_margin:{scenario}"],
                paths,
            )
        quarter_bep_quantity = _ceiling_units(total_fixed_cost / contribution_per_ea)
        average_price = sum(
            Decimal(str(row["material_price_usd_per_kg"])) for row in scenario_rows
        ) / len(scenario_rows)
        scenario_summaries.append(
            {
                "scenario": scenario,
                "scenario_order": scenario_order[scenario],
                "forecast_horizon": f"{periods[0]}~{periods[-1]}",
                "average_exchange_rate_krw_per_usd": _rounded_krw(
                    sum(
                        Decimal(row["exchange_rate_krw_per_usd"])
                        for row in scenario_rows
                    )
                    / len(scenario_rows)
                ),
                "average_material_price_usd_per_kg": float(
                    average_price.quantize(Decimal("0.01"))
                ),
                "forecast_quantity_ea": int(total_quantity),
                "revenue_krw": _rounded_krw(total_revenue),
                "total_cost_krw": _rounded_krw(total_cost),
                "operating_profit_krw": _rounded_krw(total_profit),
                "operating_margin_pct": _rounded_ratio_percent(
                    total_profit, total_revenue
                ),
                "average_unit_cogs_krw": _rounded_krw(
                    total_variable_cost / total_quantity
                ),
                "bep_quantity_ea": quarter_bep_quantity,
                "bep_revenue_krw": _rounded_krw(
                    Decimal(quarter_bep_quantity) * total_revenue / total_quantity
                ),
            }
        )

    return {
        "source": "hana_csv_snapshot_calculation",
        "lookup": "profitability_scenarios",
        "state": "found",
        "message": "CSV 입력으로 환율·원자재 가격 시나리오별 월별 원가, BEP, 분기 손익을 계산했습니다.",
        "context_id": context_id_value,
        "calculation_basis": {
            "product_id": product_id,
            "forecast_horizon": f"{periods[0]}~{periods[-1]}",
            "sales_volume_and_price": "모든 시나리오에서 월별 판매량과 순매출 계획을 동일하게 사용했습니다.",
            "variable_inputs": "환율과 원자재 단가만 시나리오별로 변동합니다.",
            "currency": "KRW",
        },
        "scenario_summaries": scenario_summaries,
        "monthly_forecasts": monthly_forecasts,
        "inputs_used": {
            "bom_component_count": len(bom_by_material),
            "month_count": len(periods),
            "scenario_count": len(scenarios),
            "data_scope": "LOCAL_SNAPSHOT",
        },
        "related_snapshot_paths": paths,
        "snapshot_boundary": "실시간 SAP HANA 조회가 아닌 로컬 CSV 스냅샷을 사용한 읽기 전용 계산입니다.",
        "write_performed": False,
    }
