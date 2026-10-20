"""Shared Context validation and related-record lookup for read-only Tools."""

from __future__ import annotations

from typing import Any

from . import snapshot_reader


def string_argument(
    value: Any, *, name: str
) -> tuple[str | None, dict[str, Any] | None]:
    """Validate one non-blank Tool argument without supplying a fallback."""
    if not isinstance(value, str) or not value.strip():
        return None, {
            "state": "invalid_input",
            "message": f"{name}는 비어 있지 않은 문자열이어야 합니다.",
        }
    return value.strip(), None


def base_response(lookup: str, state: str, path: str) -> dict[str, Any]:
    """Build the common, read-only response envelope."""
    messages = {
        "found": "로컬 CSV 스냅샷에서 읽은 데이터입니다.",
        "no_match": "로컬 CSV 스냅샷에 매칭 행이 없습니다.",
        "not_applicable": "등록된 Context에는 이 조회 범위의 행이 없습니다.",
        "snapshot_missing": "로컬 CSV 스냅샷 파일이 없습니다.",
    }
    return {
        "source": "hana_csv_snapshot",
        "lookup": lookup,
        "state": state,
        "message": messages[state],
        "snapshot_boundary": "실시간 SAP HANA 조회가 아닌 로컬 CSV 스냅샷입니다.",
        "raw_csv_path": path,
        "write_performed": False,
    }


def context_record(
    context_id: Any,
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    """Resolve one registered Context ID, without guessing a replacement."""
    normalized, invalid = string_argument(context_id, name="context_id")
    if invalid:
        return None, {
            "source": "hana_csv_snapshot",
            "lookup": "business_context",
            **invalid,
        }
    state, records, path = snapshot_reader.filter_rows(
        "business_context", field="CONTEXT_ID", value=normalized
    )
    if state != "found":
        response = base_response("business_context", state, path)
        response.update({"context_id": normalized, "records": records})
        return None, response
    return records[0], None


def related_rows(
    snapshot_name: str, context: dict[str, str]
) -> tuple[str, list[dict[str, str]], str]:
    """Read rows explicitly connected to a registered business Context."""
    state, rows, path = snapshot_reader.read_rows(snapshot_name)
    if state != "found":
        return state, rows, path

    context_id = context.get("CONTEXT_ID", "").strip()
    linked = [row for row in rows if row.get("CONTEXT_ID", "").strip() == context_id]
    if linked:
        return "found", linked, path

    # Explicit Context IDs are data lineage. Never broaden those records through
    # a shared Cost Center or another generic relation.
    eligible_rows = [
        row
        for row in rows
        if not row.get("CONTEXT_ID", "").strip()
        or row.get("CONTEXT_ID", "").strip() == context_id
    ]

    material_codes = {context.get("MATERIAL", "").strip()} - {""}
    product_id = context.get("PRODUCT_ID", "").strip()
    if product_id:
        bom_state, bom_rows, _ = snapshot_reader.read_rows("product_bom")
        if bom_state == "found":
            material_codes.update(
                row.get("COMPONENT_MATERIAL", "").strip()
                for row in bom_rows
                if row.get("PRODUCT_ID", "").strip() == product_id
                or row.get("CONTEXT_ID", "").strip() == context_id
            )
            material_codes.discard("")
    if material_codes:
        linked.extend(
            row
            for row in eligible_rows
            if row.get("MATERIAL", "").strip() in material_codes
            or row.get("PRODUCT", "").strip() in material_codes
        )

    relationships = (
        ("MATERIAL", ("MATERIAL", "PRODUCT")),
        ("PRODUCT_ID", ("PRODUCT_ID", "PRODUCT")),
        ("LINE_ID", ("LINE_ID", "LINE")),
        ("EQUIPMENT_ID", ("EQUIPMENT_ID",)),
        ("COST_CENTER", ("COST_CENTER", "SOURCE_COST_CENTER", "TARGET_COST_CENTER")),
    )
    for context_field, record_fields in relationships:
        value = context.get(context_field, "").strip()
        if value:
            linked.extend(
                row
                for row in eligible_rows
                if any(row.get(field, "").strip() == value for field in record_fields)
            )
    unique_rows = [row for index, row in enumerate(linked) if row not in linked[:index]]
    return ("found" if unique_rows else "no_match"), unique_rows, path


def status_tokens(
    records_by_snapshot: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    """Expose stored state fields without interpreting their business meaning."""
    suffixes = ("STATUS", "STATE", "READINESS")
    tokens: list[dict[str, str]] = []
    for snapshot_name, records in records_by_snapshot.items():
        for record in records:
            for field, value in record.items():
                if value and field.endswith(suffixes):
                    token = {"snapshot": snapshot_name, "field": field, "value": value}
                    if token not in tokens:
                        tokens.append(token)
    return tokens


def lookup_context_records(
    context_id: Any, *, lookup: str, snapshots: tuple[str, ...]
) -> dict[str, Any]:
    """Return a read-only evidence bundle for one Context and snapshot set."""
    context, error = context_record(context_id)
    if error:
        error["lookup"] = lookup
        return error

    assert context is not None
    records_by_snapshot: dict[str, list[dict[str, str]]] = {}
    paths: dict[str, str] = {}
    for snapshot_name in snapshots:
        state, records, path = related_rows(snapshot_name, context)
        records_by_snapshot[snapshot_name] = records if state == "found" else []
        paths[snapshot_name] = path

    response = base_response(
        lookup,
        "found" if any(records_by_snapshot.values()) else "not_applicable",
        paths[snapshots[0]],
    )
    response.update(
        {
            "context_id": context["CONTEXT_ID"],
            "context": context,
            "records_by_snapshot": records_by_snapshot,
            "status_tokens": status_tokens(records_by_snapshot),
            "related_snapshot_paths": paths,
            "relationship_boundary": (
                "Context와 엔터티 관계는 business_context CSV 스냅샷에만 근거합니다."
            ),
        }
    )
    return response
