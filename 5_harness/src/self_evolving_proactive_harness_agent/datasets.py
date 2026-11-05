"""Safe metadata summaries for CSV snapshots used by the cognitive harness."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


DATA_ROOT = Path(__file__).with_name("data")


def _metadata(path: Path) -> dict[str, Any]:
    metadata_path = path.with_suffix(".metadata.json")
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {}
    return value if isinstance(value, dict) else {}
def discover_csv_datasets() -> list[dict[str, Any]]:
    """Expose CSV shape and status distribution without sending party IDs to the LLM."""
    datasets: list[dict[str, Any]] = []
    for path in sorted(DATA_ROOT.glob("*.csv")):
        metadata = _metadata(path)
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            distinct_values = {column: set() for column in columns}
            row_count = 0
            for row in reader:
                row_count += 1
                for column in columns:
                    value = (row.get(column) or "").strip()
                    if value:
                        distinct_values[column].add(value)
        label = str(metadata.get("label") or path.stem)
        context = str(metadata.get("business_context") or "")
        summary = f"{label}: {row_count}건, 분석 가능 항목: {', '.join(columns)}."
        summary += " 항목별 값 종류 수: " + ", ".join(
            f"{column}={len(values)}" for column, values in distinct_values.items()
        ) + "."
        datasets.append({
            "kind": "dataset",
            "id": path.stem.lower(),
            "label": label,
            "description": " ".join(part for part in (context, summary) if part),
            "capabilities": ["inspect_csv_snapshot", "profile_tabular_snapshot"],
            "execution": "read_only",
        })
    return datasets


def analyze_csv_datasets(dataset_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Profile registered snapshots and return evidence, not inferred business facts.

    This deliberately excludes party identifiers and leaves the semantics of
    source-system status codes as a hypothesis requiring corroboration.
    """
    analyses: list[dict[str, Any]] = []
    for path in sorted(DATA_ROOT.glob("*.csv")):
        dataset_id = path.stem.lower()
        if dataset_ids and dataset_id not in dataset_ids:
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            rows = list(reader)
        metadata = _metadata(path)
        null_counts = {
            column: sum(not (row.get(column) or "").strip() for row in rows)
            for column in columns
        }
        distinct_counts = {
            column: len({(row.get(column) or "").strip() for row in rows if (row.get(column) or "").strip()})
            for column in columns
        }
        observations = [f"출고 데이터 스냅샷에 {len(rows)}건, {len(columns)}개 분석 항목이 있습니다."]
        observations.append(
            "항목별 값 종류 수: " + ", ".join(
                f"{column}={count}" for column, count in distinct_counts.items()
            ) + "."
        )
        missing = [column for column, count in null_counts.items() if count]
        if missing:
            observations.append("값이 비어 있는 항목이 확인되었습니다: " + ", ".join(missing) + ".")
        metric_summary = _safe_metric_summary(rows, metadata.get("safe_summary_columns", []))
        if metric_summary:
            observations.extend(metric_summary)
        analyses.append({
            "dataset_id": dataset_id,
            "row_count": len(rows),
            "columns": columns,
            "null_counts": null_counts,
            "distinct_counts": distinct_counts,
            "observations": observations,
        })
    return analyses


def simulate_csv_scenario(
    dataset_id: str, baseline_column: str, scenario_column: str, group_by: str | None = None,
) -> str:
    """Calculate an LLM-selected counterfactual from owner-approved numeric fields only."""
    path = DATA_ROOT / f"{dataset_id}.csv"
    if not path.is_file():
        raise ValueError("등록되지 않은 데이터셋은 시뮬레이션할 수 없습니다.")
    metadata = _metadata(path)
    approved = metadata.get("safe_summary_columns", [])
    if not isinstance(approved, list) or baseline_column not in approved or scenario_column not in approved:
        raise ValueError("데이터 소유자가 승인한 분석 항목만 시뮬레이션에 사용할 수 있습니다.")
    if group_by and group_by not in approved:
        raise ValueError("데이터 소유자가 승인한 분류 항목만 비교 기준으로 사용할 수 있습니다.")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    values: list[tuple[dict[str, str], float, float]] = []
    for row in rows:
        try:
            values.append((row, float((row.get(baseline_column) or "").strip()), float((row.get(scenario_column) or "").strip())))
        except ValueError:
            continue
    if not values:
        raise ValueError("선택한 두 항목에서 비교 가능한 수치 데이터를 찾지 못했습니다.")
    baseline = sum(item[1] for item in values) / len(values)
    scenario = sum(item[2] for item in values) / len(values)
    difference = baseline - scenario
    result = (f"시뮬레이션 결과: {len(values)}건 기준으로 {baseline_column} 평균 {baseline:.1f}, "
              f"{scenario_column} 평균 {scenario:.1f}, 평균 차이 {difference:.1f}, 총 차이 {difference * len(values):.1f}입니다.")
    if group_by:
        groups: dict[str, list[float]] = {}
        for row, before, after in values:
            groups.setdefault((row.get(group_by) or "미분류").strip() or "미분류", []).append(before - after)
        result += " " + group_by + "별 평균 차이: " + ", ".join(
            f"{key}={sum(deltas) / len(deltas):.1f}" for key, deltas in sorted(groups.items())
        ) + "."
    return result


def _safe_metric_summary(rows: list[dict[str, str]], columns: Any) -> list[str]:
    """Summarize only data-owner-approved mock metrics without choosing a route."""
    if not isinstance(columns, list):
        return []
    summaries: list[str] = []
    for column in columns:
        if not isinstance(column, str):
            continue
        values = [(row.get(column) or "").strip() for row in rows]
        values = [value for value in values if value]
        if not values:
            continue
        numeric = _numbers(values)
        if len(numeric) == len(values):
            summaries.append(
                f"{column}: 평균 {sum(numeric) / len(numeric):.1f}, 최소 {min(numeric):.0f}, 최대 {max(numeric):.0f}."
            )
        else:
            counts = {value: values.count(value) for value in sorted(set(values))}
            summaries.append(
                f"{column} 분포: " + ", ".join(f"{value}={count}" for value, count in counts.items()) + "."
            )
    return summaries


def _numbers(values: list[str]) -> list[float]:
    numbers: list[float] = []
    for value in values:
        try:
            numbers.append(float(value))
        except ValueError:
            return []
    return numbers
