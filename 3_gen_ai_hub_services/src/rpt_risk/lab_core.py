"""Public, read-only SAP RPT workflows for the educational risk dataset."""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
import math
import os
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from .lesson_support.ai_core import _aicore_sdk_client, apply_ai_core_environment, list_running_deployments
from .lesson_support.config import Settings
from src.grounding.object_storage import ObjectStorageConfig

DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "risk_prova_educational.csv"
RANDOM_SEED = 20261021
TARGET_COLUMN = "risk_label"
PREDICTION_PLACEHOLDER = "[PREDICT]"
RPT_MAX_QUERY_ROWS = 512
FEATURE_COLUMNS = (
    "age", "income", "num_kids", "num_cards", "how_paid", "employed_days",
    "store_car", "loans", "mortgage", "mortgage_amount", "credit_score",
)
NUMERIC_COLUMNS = {
    "age", "income", "num_kids", "num_cards", "employed_days", "store_car",
    "loans", "mortgage_amount", "credit_score",
}
AUDIT_COLUMNS = ("audit_gender", "audit_marital")
EDUCATIONAL_COLUMNS = ("record_id", *FEATURE_COLUMNS, *AUDIT_COLUMNS, TARGET_COLUMN)
PREDICTION_TABLE_COLUMNS = (*EDUCATIONAL_COLUMNS, "rpt_prediction", "rpt_confidence")
RESULTS_DIRECTORY = Path(__file__).resolve().parents[2] / "results" / "rpt_risk"
HOLDOUT_SNAPSHOT_SCHEMA_VERSION = 1
HOLDOUT_ARTIFACT_NAME_PREFIX = "rpt-risk-holdout-"
DEFAULT_RPT_RISK_OBJECT_PREFIX = "rpt-risk"
RAW_HEADER_SIZE = 20
Predictor = Callable[[dict[str, Any], str], Any]


def _normalise_number(value: Any, column: str) -> int | float:
    raw = str(value).strip().replace(",", ".")
    if not raw:
        raise ValueError(f"{column} 값이 비어 있습니다.")
    number = float(raw)
    if not math.isfinite(number):
        raise ValueError(f"{column} 값은 유한한 숫자여야 합니다.")
    return int(number) if number.is_integer() else number


def _normalise_label(value: Any) -> str:
    label = str(value).strip()
    if label not in {"0", "1"}:
        raise ValueError("risk_label은 0 또는 1이어야 합니다.")
    return label


def _normalise_educational_row(row: Mapping[str, Any]) -> dict[str, Any]:
    if not str(row.get("record_id", "")).strip():
        raise ValueError("record_id가 비어 있습니다.")
    result: dict[str, Any] = {"record_id": str(row["record_id"]).strip()}
    for column in FEATURE_COLUMNS:
        value = row.get(column, "")
        result[column] = _normalise_number(value, column) if column in NUMERIC_COLUMNS else str(value).strip()
        if result[column] == "":
            raise ValueError(f"{column} 값이 비어 있습니다.")
    for column in AUDIT_COLUMNS:
        result[column] = str(row.get(column, "")).strip() or "unknown"
    result[TARGET_COLUMN] = _normalise_label(row.get(TARGET_COLUMN, ""))
    return result


def create_educational_dataset(source_path: str | Path, destination_path: str | Path) -> dict[str, Any]:
    """Create an ID-free educational copy from the supplied 20-column CSV."""
    source = Path(source_path)
    destination = Path(destination_path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        header = next(reader, None)
        if header is None or len(header) != RAW_HEADER_SIZE:
            raise ValueError("원본 risk CSV는 20개 세미콜론 구분 열이어야 합니다.")
        required = {
            0: "ID", 1: "AGE", 2: "INCOME", 3: "GENDER", 4: "MARITAL",
            5: "NUMKIDS", 6: "NUMCARDS", 7: "HOWPAID", 8: "EMPLOYED_DAYS",
            9: "STORECAR", 10: "LOANS", 15: "MORTGAGE", 16: "MORTGAGE_AMOUNT",
            17: "CREDIT_SCORE", 18: "RISK", 19: "RISK",
        }
        for index, name in required.items():
            if header[index].strip() != name:
                raise ValueError(f"원본 헤더 {index + 1}번째 열은 {name}이어야 합니다.")
        converted: list[dict[str, Any]] = []
        for line_number, raw in enumerate(reader, start=2):
            if len(raw) != RAW_HEADER_SIZE:
                raise ValueError(f"원본 {line_number}행의 열 수가 20개가 아닙니다.")
            converted.append(_normalise_educational_row({
                "record_id": f"risk-{len(converted) + 1:05d}",
                "age": raw[1], "income": raw[2],
                "audit_gender": raw[3], "audit_marital": raw[4],
                "num_kids": raw[5], "num_cards": raw[6], "how_paid": raw[7],
                "employed_days": raw[8], "store_car": raw[9], "loans": raw[10],
                "mortgage": raw[15], "mortgage_amount": raw[16],
                "credit_score": raw[17], TARGET_COLUMN: raw[19],
            }))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EDUCATIONAL_COLUMNS, delimiter=";")
        writer.writeheader()
        writer.writerows(converted)
    return {"source_rows": len(converted), "destination": str(destination), "columns": list(EDUCATIONAL_COLUMNS)}


def _load_rows(data_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(data_path or DATASET_PATH)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if tuple(reader.fieldnames or ()) != EDUCATIONAL_COLUMNS:
            raise ValueError("교육용 risk CSV 헤더가 예상 스키마와 다릅니다.")
        rows = [_normalise_educational_row(row) for row in reader]
    if not rows:
        raise ValueError("교육용 risk CSV에 데이터 행이 없습니다.")
    if len({row["record_id"] for row in rows}) != len(rows):
        raise ValueError("교육용 risk CSV의 record_id는 고유해야 합니다.")
    return rows


def inspect_risk_dataset(data_path: str | Path | None = None) -> dict[str, Any]:
    """Return JSON-friendly data-quality evidence without calling SAP BTP."""
    rows = _load_rows(data_path)
    return {
        "dataset_path": str(Path(data_path or DATASET_PATH)),
        "row_count": len(rows),
        "feature_columns": list(FEATURE_COLUMNS),
        "target_column": TARGET_COLUMN,
        "target_distribution": dict(sorted(Counter(row[TARGET_COLUMN] for row in rows).items())),
        "rpt_excluded_columns": ["source_id", "risk_text_label", "audit_gender", "audit_marital", "blank_or_unreliable_source_columns"],
        "audit_only_columns": list(AUDIT_COLUMNS),
        "data_boundary": "RPT에는 feature_columns와 risk_label만 전송합니다. 식별자와 감사 속성은 전송하지 않습니다.",
    }


def preview_risk_dataset(
    data_path: str | Path | None = None,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Return a bounded, ID-free table preview without calling SAP BTP."""
    if not 1 <= limit <= 500:
        raise ValueError("limit은 1에서 500 사이여야 합니다.")
    rows = _load_rows(data_path)
    columns = list(EDUCATIONAL_COLUMNS)
    return {
        "columns": columns,
        "rows": [{column: row[column] for column in columns} for row in rows[:limit]],
        "total_rows": len(rows),
        "displayed_rows": min(limit, len(rows)),
        "data_boundary": "원본 customer ID는 제거되어 있으며, 이 미리보기는 로컬에서만 표시되고 SAP BTP에 전송되지 않습니다.",
    }


def _stratified_split(rows: Sequence[dict[str, Any]], support_fraction: float = 0.8) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not 0 < support_fraction < 1:
        raise ValueError("support_fraction은 0과 1 사이여야 합니다.")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row[TARGET_COLUMN]].append(row)
    support: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []
    for label in sorted(grouped):
        group = sorted(grouped[label], key=lambda item: item["record_id"])
        ordered = sorted(
            group,
            key=lambda item: hashlib.sha256(f"{RANDOM_SEED}:{item['record_id']}".encode()).hexdigest(),
        )
        cut = max(1, min(len(ordered) - 1, round(len(ordered) * support_fraction)))
        support.extend(ordered[:cut])
        holdout.extend(ordered[cut:])
    return sorted(support, key=lambda item: item["record_id"]), sorted(holdout, key=lambda item: item["record_id"])


def build_rpt_request(support_rows: Sequence[Mapping[str, Any]], query_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the RPT table request; audit attributes never cross this boundary."""
    if not support_rows or not query_rows:
        raise ValueError("RPT 요청에는 라벨된 support 행과 하나 이상의 query 행이 필요합니다.")

    def to_rpt_row(row: Mapping[str, Any], label: str) -> dict[str, Any]:
        return {"record_id": str(row["record_id"]), **{key: row[key] for key in FEATURE_COLUMNS}, TARGET_COLUMN: label}

    return {
        "prediction_config": {"target_columns": [{"name": TARGET_COLUMN, "prediction_placeholder": PREDICTION_PLACEHOLDER, "task_type": "classification"}]},
        "index_column": "record_id",
        "rows": [*(to_rpt_row(row, _normalise_label(row[TARGET_COLUMN])) for row in support_rows), *(to_rpt_row(row, PREDICTION_PLACEHOLDER) for row in query_rows)],
        "data_schema": {
            "record_id": {"dtype": "string"},
            **{column: {"dtype": "numeric" if column in NUMERIC_COLUMNS else "string"} for column in FEATURE_COLUMNS},
            TARGET_COLUMN: {"dtype": "string"},
        },
        "parse_data_types": False,
    }


def rpt_deployment_url(
    settings: Settings,
    deployment_loader: Callable[[Settings], list[dict[str, Any]]] = list_running_deployments,
) -> str:
    """Resolve one RUNNING RPT deployment without changing BTP resources."""
    settings.require_ai_core()
    for deployment in deployment_loader(settings):
        backend = ((deployment.get("details") or {}).get("resources") or {}).get("backend_details") or {}
        model = (backend.get("model") or {}).get("name", "")
        matches_id = not settings.rpt_deployment_id or deployment.get("id") == settings.rpt_deployment_id
        if model == settings.rpt_model and deployment.get("deploymentUrl") and matches_id:
            return str(deployment["deploymentUrl"]).rstrip("/")
    if settings.rpt_deployment_id:
        raise RuntimeError(f"AICORE_RPT_DEPLOYMENT_ID={settings.rpt_deployment_id!r}에 해당하는 RUNNING RPT 배포를 찾지 못했습니다.")
    raise RuntimeError(f"RUNNING RPT deployment를 찾지 못했습니다: {settings.rpt_model!r}")


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def _call_rpt(request: dict[str, Any], settings: Settings, deployment_url: str, predictor: Predictor | None) -> dict[str, Any]:
    if predictor is not None:
        return _to_jsonable(predictor(request, deployment_url))
    try:
        from gen_ai_hub.proxy.native.sap import RPTClient
    except ImportError as error:
        raise RuntimeError("sap-ai-sdk-gen이 없습니다. pip install -r requirements.txt를 실행하세요.") from error
    apply_ai_core_environment(settings)
    try:
        return _to_jsonable(RPTClient(timeout=120).predict(body=request, deployment_url=deployment_url))
    except Exception as error:
        status = getattr(error, "status", None)
        detail = getattr(error, "detail", None)
        evidence = ", ".join(part for part in (f"status={status}" if status else "", f"detail={detail}" if detail else "") if part)
        suffix = f" ({evidence})" if evidence else ""
        raise RuntimeError(f"SAP RPT 예측 호출에 실패했습니다: {type(error).__name__}: {error}{suffix}") from error


def _prediction_items(response: Mapping[str, Any], expected: int) -> list[dict[str, Any]]:
    items: list[Any] = []
    for prediction in response.get("predictions", []):
        if isinstance(prediction, Mapping) and isinstance(prediction.get(TARGET_COLUMN), list):
            items.extend(prediction[TARGET_COLUMN])
    if len(items) != expected:
        raise RuntimeError(f"SAP RPT 응답의 {TARGET_COLUMN} 예측 수가 query 행 수와 다릅니다: {len(items)} != {expected}")
    normalised = []
    for item in items:
        if not isinstance(item, Mapping):
            raise RuntimeError("SAP RPT 응답의 prediction 항목 형식이 올바르지 않습니다.")
        prediction = _normalise_label(item.get("prediction", ""))
        confidence = item.get("confidence")
        normalised.append({"prediction": prediction, "confidence": float(confidence) if confidence is not None else None})
    return normalised


def _metrics(actual: Sequence[str], predicted: Sequence[str]) -> dict[str, Any]:
    pairs = list(zip(actual, predicted, strict=True))
    true_positive = sum(a == "1" and p == "1" for a, p in pairs)
    false_positive = sum(a == "0" and p == "1" for a, p in pairs)
    false_negative = sum(a == "1" and p == "0" for a, p in pairs)
    true_negative = sum(a == "0" and p == "0" for a, p in pairs)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    return {
        "accuracy": (true_positive + true_negative) / len(pairs) if pairs else 0.0,
        "precision_positive_1": precision,
        "recall_positive_1": recall,
        "f1_positive_1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "confusion_matrix": {
            "actual_0": {"predicted_0": true_negative, "predicted_1": false_positive},
            "actual_1": {"predicted_0": false_negative, "predicted_1": true_positive},
        },
    }


def _audit(rows: Sequence[Mapping[str, Any]], predicted: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for column in AUDIT_COLUMNS:
        grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row, prediction in zip(rows, predicted, strict=True):
            grouped[str(row[column])].append((str(row[TARGET_COLUMN]), prediction))
        result[column] = [
            {
                "group": group,
                "count": len(values),
                "accuracy": sum(actual == prediction for actual, prediction in values) / len(values),
                "predicted_positive_rate": sum(prediction == "1" for _, prediction in values) / len(values),
            }
            for group, values in sorted(grouped.items())
        ]
    return result


def _query_batches(rows: Sequence[dict[str, Any]]) -> list[Sequence[dict[str, Any]]]:
    """Keep every holdout row while respecting the RPT service query-row limit."""
    return [rows[start:start + RPT_MAX_QUERY_ROWS] for start in range(0, len(rows), RPT_MAX_QUERY_ROWS)]


def _predict_query_rows(
    support: Sequence[dict[str, Any]],
    query_rows: Sequence[dict[str, Any]],
    settings: Settings,
    deployment_url: str,
    predictor: Predictor | None,
) -> tuple[list[dict[str, Any]], list[Any]]:
    items: list[dict[str, Any]] = []
    metadata: list[Any] = []
    for batch in _query_batches(query_rows):
        response = _call_rpt(build_rpt_request(support, batch), settings, deployment_url, predictor)
        items.extend(_prediction_items(response, len(batch)))
        metadata.append(response.get("metadata"))
    return items, metadata


def _permuted_rows(rows: Sequence[dict[str, Any]], feature: str) -> list[dict[str, Any]]:
    values = [row[feature] for row in rows]
    shuffled = values.copy()
    random.Random(f"{RANDOM_SEED}:{feature}").shuffle(shuffled)
    return [{**row, feature: value} for row, value in zip(rows, shuffled, strict=True)]


def _reference_value(rows: Sequence[dict[str, Any]], feature: str, original: Any) -> Any:
    values = [row[feature] for row in rows]
    if feature in NUMERIC_COLUMNS:
        ordered = sorted(values)
        reference = ordered[len(ordered) // 2]
        if reference == original:
            alternatives = [value for value in ordered if value != original]
            return alternatives[len(alternatives) // 2] if alternatives else reference
        return reference
    counts = Counter(values)
    alternatives = [value for value, _ in counts.most_common() if value != original]
    return alternatives[0] if alternatives else original


def _case_row(case: Mapping[str, Any], record_id: str) -> dict[str, Any]:
    return _normalise_educational_row({
        "record_id": record_id,
        **{column: case.get(column, "") for column in FEATURE_COLUMNS},
        "audit_gender": "not-collected",
        "audit_marital": "not-collected",
        TARGET_COLUMN: "0",
    })


def run_rpt_risk_evaluation(
    settings: Settings,
    data_path: str | Path | None = None,
    *,
    predictor: Predictor | None = None,
    deployment_url: str | None = None,
) -> dict[str, Any]:
    """Evaluate the fixed 80/20 holdout with one read-only SAP RPT request."""
    rows = _load_rows(data_path)
    support, holdout = _stratified_split(rows)
    selected_url = deployment_url or ("test://rpt" if predictor is not None else rpt_deployment_url(settings))
    items, metadata = _predict_query_rows(support, holdout, settings, selected_url, predictor)
    predicted = [item["prediction"] for item in items]
    actual = [row[TARGET_COLUMN] for row in holdout]
    return {
        "model": settings.rpt_model,
        "execution_boundary": "읽기 전용 RPT 예측입니다. 자동 승인·거절 또는 BTP 학습·배포 변경은 수행하지 않습니다.",
        "request_summary": {"support_rows": len(support), "holdout_rows": len(holdout), "rpt_request_count": len(metadata), "max_query_rows_per_request": RPT_MAX_QUERY_ROWS, "feature_columns": list(FEATURE_COLUMNS), "target_column": TARGET_COLUMN},
        "metrics": _metrics(actual, predicted),
        "audit": _audit(holdout, predicted),
        "predictions": [{"record_id": row["record_id"], "actual": label, **item} for row, label, item in zip(holdout, actual, items, strict=True)],
        "prediction_table": [
            {
                **{column: row[column] for column in EDUCATIONAL_COLUMNS},
                "rpt_prediction": item["prediction"],
                "rpt_confidence": item["confidence"],
            }
            for row, item in zip(holdout, items, strict=True)
        ],
        "rpt_metadata": metadata,
        "review_notice": "이 결과는 교육용 모델 평가이며 신용 승인·거절 결정을 대신하지 않습니다.",
    }


def export_rpt_risk_results(
    evaluation: Mapping[str, Any],
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Persist one completed holdout evaluation as a local UTF-8 CSV file."""
    rows = evaluation.get("prediction_table")
    if not isinstance(rows, list) or not rows:
        raise ValueError("저장할 holdout 예측 결과가 없습니다. 먼저 RPT 평가를 실행하세요.")
    if any(not isinstance(row, Mapping) or any(column not in row for column in PREDICTION_TABLE_COLUMNS) for row in rows):
        raise ValueError("저장할 RPT 예측 결과의 CSV 스키마가 올바르지 않습니다.")
    metrics = evaluation.get("metrics") or {}
    exported_at = datetime.now(ZoneInfo("Asia/Seoul"))
    target_dir = Path(output_dir) if output_dir is not None else RESULTS_DIRECTORY
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"rpt_risk_holdout_{exported_at.strftime('%Y%m%dT%H%M%S%f%z')}.csv"
    metadata = {
        "rpt_model": str(evaluation.get("model", "")),
        "rpt_accuracy": metrics.get("accuracy", ""),
        "rpt_f1_positive_1": metrics.get("f1_positive_1", ""),
        "exported_at": exported_at.isoformat(),
    }
    fieldnames = [*PREDICTION_TABLE_COLUMNS, *metadata]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({**{column: row[column] for column in PREDICTION_TABLE_COLUMNS}, **metadata})
    return {
        "path": str(path),
        "row_count": len(rows),
        "columns": fieldnames,
        "execution_boundary": "로컬 CSV 파일만 저장했습니다. SAP BTP 학습·배포·외부 쓰기 작업은 수행하지 않았습니다.",
    }


def _holdout_storage_prefix() -> str:
    raw = os.getenv("RPT_RISK_OBJECT_PREFIX", DEFAULT_RPT_RISK_OBJECT_PREFIX).strip().strip("/")
    parts = [part for part in raw.replace("\\", "/").split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("RPT_RISK_OBJECT_PREFIX는 상대 Object Storage 경로여야 합니다.")
    return "/".join(parts)


def _snapshot_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the pseudonymous RPT contract fields in a persisted snapshot."""
    normalized = _normalise_educational_row(row)
    return {
        "record_id": normalized["record_id"],
        **{column: normalized[column] for column in FEATURE_COLUMNS},
        TARGET_COLUMN: normalized[TARGET_COLUMN],
    }


def _row_from_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise ValueError("저장된 holdout 행 형식이 올바르지 않습니다.")
    return _normalise_educational_row({
        "record_id": row.get("record_id", ""),
        **{column: row.get(column, "") for column in FEATURE_COLUMNS},
        "audit_gender": "not-stored",
        "audit_marital": "not-stored",
        TARGET_COLUMN: row.get(TARGET_COLUMN, ""),
    })


def build_rpt_holdout_snapshot(
    evaluation: Mapping[str, Any],
    *,
    data_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create one immutable, ID-minimized snapshot for a completed holdout run."""
    prediction_rows = evaluation.get("prediction_table")
    if not isinstance(prediction_rows, list) or not prediction_rows:
        raise ValueError("저장할 holdout 예측 결과가 없습니다. 먼저 RPT 평가를 실행하세요.")
    rows = _load_rows(data_path)
    support, holdout = _stratified_split(rows)
    by_id = {str(row.get("record_id", "")): row for row in prediction_rows if isinstance(row, Mapping)}
    if set(by_id) != {row["record_id"] for row in holdout}:
        raise ValueError("holdout 평가 결과와 현재 데이터 분할이 일치하지 않습니다. 평가를 다시 실행하세요.")
    created_at = now or datetime.now(ZoneInfo("Asia/Seoul"))
    run_id = f"{created_at.strftime('%Y%m%dT%H%M%S%f%z')}-{uuid4().hex[:8]}"
    holdout_rows = []
    for row in holdout:
        predicted = by_id[row["record_id"]]
        holdout_rows.append({
            **_snapshot_row(row),
            "rpt_prediction": _normalise_label(predicted.get("rpt_prediction", "")),
            "rpt_confidence": (
                float(predicted["rpt_confidence"])
                if predicted.get("rpt_confidence") not in {None, "", "—"} else None
            ),
        })
    metrics = evaluation.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ValueError("저장할 holdout 평가 지표가 없습니다.")
    return {
        "schema_version": HOLDOUT_SNAPSHOT_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": created_at.isoformat(),
        "model": str(evaluation.get("model", "")),
        "split": {"support_fraction": 0.8, "random_seed": RANDOM_SEED},
        "feature_columns": list(FEATURE_COLUMNS),
        "target_column": TARGET_COLUMN,
        "support_rows": [_snapshot_row(row) for row in support],
        "holdout_rows": holdout_rows,
        "metrics": dict(metrics),
        "request_summary": dict(evaluation.get("request_summary") or {}),
    }


def _validate_holdout_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise ValueError("저장된 holdout snapshot 형식이 올바르지 않습니다.")
    if snapshot.get("schema_version") != HOLDOUT_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("지원하지 않는 holdout snapshot 버전입니다.")
    if snapshot.get("feature_columns") != list(FEATURE_COLUMNS) or snapshot.get("target_column") != TARGET_COLUMN:
        raise ValueError("저장된 holdout snapshot의 RPT 스키마가 현재 코드와 다릅니다.")
    support = snapshot.get("support_rows")
    holdout = snapshot.get("holdout_rows")
    if not isinstance(support, list) or not support or not isinstance(holdout, list) or not holdout:
        raise ValueError("저장된 holdout snapshot에 support 또는 holdout 행이 없습니다.")
    normalized_support = [_row_from_snapshot(row) for row in support]
    normalized_holdout = [_row_from_snapshot(row) for row in holdout]
    if {row["record_id"] for row in normalized_support} & {row["record_id"] for row in normalized_holdout}:
        raise ValueError("저장된 support와 holdout에 중복 record_id가 있습니다.")
    return {**dict(snapshot), "support_rows": normalized_support, "holdout_rows": normalized_holdout}


def _artifact_client(settings: Settings) -> Any:
    return _aicore_sdk_client(settings, f"{settings.base_url}/v2").artifact


def _artifact_kind_resultset() -> Any:
    try:
        from ai_api_client_sdk.models.artifact import Artifact
    except ImportError as error:
        raise RuntimeError("AI Core Artifact 등록에는 sap-ai-sdk-core가 필요합니다.") from error
    return Artifact.Kind.RESULTSET


def _artifact_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, list):
        return [_artifact_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _artifact_value(item) for key, item in value.items()}
    return value


def persist_rpt_holdout_snapshot(
    evaluation: Mapping[str, Any],
    settings: Settings,
    *,
    data_path: str | Path | None = None,
    storage: ObjectStorageConfig | None = None,
    storage_client: Any | None = None,
    artifact_client: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Write a completed holdout snapshot to Object Storage and register its RESULTSET artifact."""
    if not settings.allow_write_tools:
        raise PermissionError("BTP holdout 저장에는 ALLOW_WRITE_TOOLS=true가 필요합니다.")
    scenario_id = settings.rpt_artifact_scenario_id.strip()
    if not scenario_id:
        raise ValueError("AICORE_RPT_ARTIFACT_SCENARIO_ID를 설정하세요.")
    snapshot = build_rpt_holdout_snapshot(evaluation, data_path=data_path, now=now)
    configuration = storage or ObjectStorageConfig.from_environment()
    configuration.require_configured()
    key = f"{_holdout_storage_prefix()}/{snapshot['run_id']}/holdout.json"
    body = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    response = (storage_client or configuration.client()).put_object(
        Bucket=configuration.bucket, Key=key, Body=body, ContentType="application/json; charset=utf-8"
    )
    uri = f"s3://{configuration.bucket}/{key}"
    try:
        artifact = (artifact_client or _artifact_client(settings)).create(
            name=f"{HOLDOUT_ARTIFACT_NAME_PREFIX}{snapshot['run_id']}",
            kind=_artifact_kind_resultset(),
            url=uri,
            scenario_id=scenario_id,
            description=(
                "Educational RPT 80/20 holdout snapshot; contains pseudonymous record IDs, "
                "RPT features, labels, predictions, and metrics only."
            ),
        )
    except Exception as error:
        raise RuntimeError(
            f"Object Storage 저장은 완료됐지만 AI Core Artifact 등록에 실패했습니다: {uri}"
        ) from error
    return {
        "run_id": snapshot["run_id"],
        "artifact_id": str(getattr(artifact, "id", getattr(artifact, "artifact_id", ""))),
        "artifact_name": f"{HOLDOUT_ARTIFACT_NAME_PREFIX}{snapshot['run_id']}",
        "scenario_id": scenario_id,
        "object_uri": uri,
        "etag": str(response.get("ETag", "")),
        "holdout_rows": len(snapshot["holdout_rows"]),
        "execution_boundary": "BTP Object Storage와 AI Core Artifact에 교육용 holdout snapshot만 저장했습니다. 자동 신용 승인·거절은 수행하지 않습니다.",
    }


def list_saved_rpt_holdout_runs(
    settings: Settings, *, artifact_client: Any | None = None,
) -> dict[str, Any]:
    """List RESULTSET artifacts for the configured tabular-orchestration scenario."""
    scenario_id = settings.rpt_artifact_scenario_id.strip()
    if not scenario_id:
        raise ValueError("AICORE_RPT_ARTIFACT_SCENARIO_ID를 설정하세요.")
    response = (artifact_client or _artifact_client(settings)).query(
        scenario_id=scenario_id, kind=_artifact_kind_resultset(), top=200
    )
    resources = getattr(response, "resources", response.get("resources", []) if isinstance(response, Mapping) else [])
    runs = []
    for artifact in resources:
        name = str(getattr(artifact, "name", artifact.get("name", "") if isinstance(artifact, Mapping) else ""))
        if not name.startswith(HOLDOUT_ARTIFACT_NAME_PREFIX):
            continue
        artifact_id = str(getattr(artifact, "id", artifact.get("id", "") if isinstance(artifact, Mapping) else ""))
        url = str(getattr(artifact, "url", artifact.get("url", "") if isinstance(artifact, Mapping) else ""))
        created_at = getattr(artifact, "created_at", artifact.get("created_at", "") if isinstance(artifact, Mapping) else "")
        runs.append({"artifact_id": artifact_id, "name": name, "object_uri": url, "created_at": _artifact_value(created_at)})
    return {"scenario_id": scenario_id, "runs": sorted(runs, key=lambda item: item["name"], reverse=True)}


def _s3_uri_parts(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError("저장된 Artifact URL은 s3:// URI여야 합니다.")
    bucket, separator, key = uri[5:].partition("/")
    if not bucket or not separator or not key:
        raise ValueError("저장된 Artifact의 Object Storage URI가 올바르지 않습니다.")
    return bucket, key


def load_saved_rpt_holdout_run(
    artifact_id: str,
    settings: Settings,
    *,
    storage: ObjectStorageConfig | None = None,
    storage_client: Any | None = None,
    artifact_client: Any | None = None,
) -> dict[str, Any]:
    """Load and validate one persisted RPT holdout snapshot from its Artifact URI."""
    selected_id = str(artifact_id).strip()
    if not selected_id:
        raise ValueError("저장된 Holdout Artifact를 선택하세요.")
    artifact = (artifact_client or _artifact_client(settings)).get(selected_id)
    artifact_scenario = str(getattr(artifact, "scenario_id", artifact.get("scenario_id", "") if isinstance(artifact, Mapping) else ""))
    if artifact_scenario and artifact_scenario != settings.rpt_artifact_scenario_id:
        raise ValueError("선택한 Artifact가 설정된 tabular-orchestration Scenario에 속하지 않습니다.")
    url = str(getattr(artifact, "url", artifact.get("url", "") if isinstance(artifact, Mapping) else ""))
    bucket, key = _s3_uri_parts(url)
    configuration = storage or ObjectStorageConfig.from_environment()
    configuration.require_configured()
    if bucket != configuration.bucket:
        raise ValueError("저장된 Holdout Artifact가 현재 설정된 Object Storage bucket에 없습니다.")
    response = (storage_client or configuration.client()).get_object(Bucket=bucket, Key=key)
    body = response.get("Body") if isinstance(response, Mapping) else None
    if body is None or not hasattr(body, "read"):
        raise RuntimeError("Object Storage가 holdout snapshot 본문을 반환하지 않았습니다.")
    try:
        snapshot = json.loads(body.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("저장된 holdout snapshot JSON을 읽을 수 없습니다.") from error
    validated = _validate_holdout_snapshot(snapshot)
    return {**validated, "artifact_id": selected_id, "object_uri": url}


def saved_rpt_holdout_scenarios(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return selectable holdout scenarios without disclosing their actual labels."""
    validated = _validate_holdout_snapshot(snapshot)
    return [
        {"record_id": row["record_id"], **{column: row[column] for column in FEATURE_COLUMNS}}
        for row in validated["holdout_rows"]
    ]


def predict_saved_rpt_holdout_row(
    snapshot: Mapping[str, Any],
    record_id: str,
    settings: Settings,
    *,
    predictor: Predictor | None = None,
    deployment_url: str | None = None,
) -> dict[str, Any]:
    """Predict one persisted holdout row against its persisted 80% support set."""
    validated = _validate_holdout_snapshot(snapshot)
    selected_id = str(record_id).strip()
    selected = next((row for row in validated["holdout_rows"] if row["record_id"] == selected_id), None)
    if selected is None:
        raise ValueError("선택한 record_id가 저장된 holdout 시나리오에 없습니다.")
    selected_url = deployment_url or ("test://rpt" if predictor is not None else rpt_deployment_url(settings))
    items, metadata = _predict_query_rows(validated["support_rows"], [selected], settings, selected_url, predictor)
    item = items[0]
    return {
        "artifact_id": str(validated.get("artifact_id", "")),
        "record_id": selected_id,
        "classification": item["prediction"],
        "confidence": item["confidence"],
        "actual_label": selected[TARGET_COLUMN],
        "correct": item["prediction"] == selected[TARGET_COLUMN],
        "stored_model": str(validated.get("model", "")),
        "active_model": settings.rpt_model,
        "request_summary": {"support_rows": len(validated["support_rows"]), "query_rows": 1, "feature_columns": list(FEATURE_COLUMNS)},
        "execution_boundary": "저장된 교육용 holdout 행을 RPT로 재예측한 사람 검토용 결과입니다. 자동 신용 승인·거절은 수행하지 않습니다.",
        "rpt_metadata": metadata,
    }


def predict_rpt_risk_case(
    case: Mapping[str, Any],
    settings: Settings,
    data_path: str | Path | None = None,
    *,
    predictor: Predictor | None = None,
    deployment_url: str | None = None,
) -> dict[str, Any]:
    """Classify one declared case against the same labelled support set."""
    rows = _load_rows(data_path)
    support, _ = _stratified_split(rows)
    query = _case_row(case, "manual-case")
    selected_url = deployment_url or ("test://rpt" if predictor is not None else rpt_deployment_url(settings))
    items, metadata = _predict_query_rows(support, [query], settings, selected_url, predictor)
    item = items[0]
    return {
        "model": settings.rpt_model,
        "classification": item["prediction"],
        "confidence": item["confidence"],
        "request_summary": {"support_rows": len(support), "query_rows": 1, "feature_columns": list(FEATURE_COLUMNS)},
        "execution_boundary": "읽기 전용 RPT 예측입니다. 이 결과는 사람 검토용 참고치이며 자동 신용 의사결정이 아닙니다.",
        "rpt_metadata": metadata,
    }


def run_rpt_permutation_importance(
    settings: Settings,
    data_path: str | Path | None = None,
    *,
    predictor: Predictor | None = None,
    deployment_url: str | None = None,
) -> dict[str, Any]:
    """Estimate global feature impact by permuting one holdout feature at a time."""
    rows = _load_rows(data_path)
    support, holdout = _stratified_split(rows)
    selected_url = deployment_url or ("test://rpt" if predictor is not None else rpt_deployment_url(settings))
    actual = [row[TARGET_COLUMN] for row in holdout]
    baseline_items, baseline_metadata = _predict_query_rows(support, holdout, settings, selected_url, predictor)
    baseline_metrics = _metrics(actual, [item["prediction"] for item in baseline_items])
    importance: list[dict[str, Any]] = []
    request_count = len(baseline_metadata)
    for feature in FEATURE_COLUMNS:
        items, metadata = _predict_query_rows(
            support, _permuted_rows(holdout, feature), settings, selected_url, predictor
        )
        metrics = _metrics(actual, [item["prediction"] for item in items])
        request_count += len(metadata)
        importance.append({
            "feature": feature,
            "permuted_accuracy": metrics["accuracy"],
            "permuted_f1_positive_1": metrics["f1_positive_1"],
            "accuracy_drop": baseline_metrics["accuracy"] - metrics["accuracy"],
            "f1_drop_positive_1": baseline_metrics["f1_positive_1"] - metrics["f1_positive_1"],
        })
    importance.sort(key=lambda item: item["f1_drop_positive_1"], reverse=True)
    return {
        "model": settings.rpt_model,
        "method": "각 feature를 holdout에서만 결정적으로 섞고 baseline 대비 성능 하락을 측정하는 model-agnostic permutation importance입니다.",
        "baseline_metrics": baseline_metrics,
        "feature_importance": importance,
        "request_summary": {"support_rows": len(support), "holdout_rows": len(holdout), "rpt_request_count": request_count, "feature_count": len(FEATURE_COLUMNS)},
        "limitation": "이는 RPT 내부의 인과적 설명이나 개별 기여도가 아닙니다. 상관된 feature는 중요도가 분산될 수 있으며, 자동 신용 의사결정 근거로 사용하면 안 됩니다.",
    }


def explain_rpt_risk_case(
    case: Mapping[str, Any],
    feature: str,
    settings: Settings,
    data_path: str | Path | None = None,
    *,
    predictor: Predictor | None = None,
    deployment_url: str | None = None,
) -> dict[str, Any]:
    """Compare one case with a one-feature counterfactual reference value."""
    if feature not in FEATURE_COLUMNS:
        raise ValueError(f"분석할 feature는 다음 중 하나여야 합니다: {', '.join(FEATURE_COLUMNS)}")
    rows = _load_rows(data_path)
    support, _ = _stratified_split(rows)
    selected_url = deployment_url or ("test://rpt" if predictor is not None else rpt_deployment_url(settings))
    baseline = _case_row(case, "manual-case")
    reference = _reference_value(support, feature, baseline[feature])
    counterfactual = {**baseline, "record_id": "counterfactual-case", feature: reference}
    baseline_item, baseline_metadata = _predict_query_rows(support, [baseline], settings, selected_url, predictor)
    changed_item, changed_metadata = _predict_query_rows(support, [counterfactual], settings, selected_url, predictor)
    baseline_result, changed_result = baseline_item[0], changed_item[0]
    confidence_delta = None
    if baseline_result["confidence"] is not None and changed_result["confidence"] is not None:
        confidence_delta = changed_result["confidence"] - baseline_result["confidence"]
    return {
        "model": settings.rpt_model,
        "method": "선택한 feature 하나만 support set의 대표값으로 바꾼 local counterfactual sensitivity입니다.",
        "feature": feature,
        "baseline": {"feature_value": baseline[feature], **baseline_result},
        "counterfactual": {"feature_value": reference, **changed_result},
        "prediction_changed": baseline_result["prediction"] != changed_result["prediction"],
        "confidence_delta": confidence_delta,
        "request_summary": {"support_rows": len(support), "rpt_request_count": len(baseline_metadata) + len(changed_metadata)},
        "limitation": "이 비교는 하나의 가상 변경에 대한 민감도일 뿐 예측의 원인이나 인과관계를 증명하지 않습니다.",
    }
