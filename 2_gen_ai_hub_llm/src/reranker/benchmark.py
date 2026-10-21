"""Repeatable, read-only evaluation helpers for decision reranker strategies."""
from __future__ import annotations

from statistics import median
from time import perf_counter
from typing import Any, Callable

from lab_common.config import Settings
from .lab_core import Strategy, run_decision_recommendation


# Educational labels cover the five order-risk signal groups.  They are not
# financial AML/STR determinations and do not change customer state.
SYNTHETIC_EVALUATION_CASES = [
    {"id": "normal_clear", "case": "인증된 고객이 60초 이상 간격으로 분당 1회 주문했다. 중복, 실패, 한도 초과는 없고 결제수단·배송지·수취인은 기존 이력과 일치한다.", "expected": "approve", "label_basis": "educational-policy"},
    {"id": "normal_boundary", "case": "기존 고객이 20초 이상 간격으로 1분에 3회 이하 주문했다. 인증과 결제는 성공했고 동일 주문의 중복은 없다.", "expected": "approve", "label_basis": "educational-policy"},
    {"id": "normal_repeat", "case": "한 계정이 평소 사용하던 기기와 배송지에서 같은 결제수단으로 주문을 두 번 완료했다. 실패와 변경 정황은 없다.", "expected": "approve", "label_basis": "educational-policy"},
    {"id": "normal_gift", "case": "인증된 고객이 선물 주문을 1회 생성했고 수취인만 다르다. 주문 빈도, 결제수단, 배송지는 정상 범위이며 실패는 없다.", "expected": "approve", "label_basis": "educational-policy"},
    {"id": "normal_low_volume", "case": "신규 고객이 인증 후 상품 한도를 넘지 않는 수량을 한 번 주문했다. 결제 실패, 중복 주문, 자동화 정황은 없다.", "expected": "approve", "label_basis": "educational-policy"},
    {"id": "caution_velocity", "case": "인증된 고객이 1분에 5회 주문을 시도했다. 실패와 자동화 정황은 확인되지 않았다.", "expected": "manual-review", "label_basis": "educational-policy"},
    {"id": "caution_account_link", "case": "두 계정이 같은 기기와 네트워크를 사용해 같은 배송지로 주문했다. 결제 실패나 한도 회피는 없다.", "expected": "manual-review", "label_basis": "educational-policy"},
    {"id": "caution_payment", "case": "한 계정이 결제수단을 두 번 변경했고 결제 실패가 한 번 발생했다. 배송지와 수취인은 같다.", "expected": "manual-review", "label_basis": "educational-policy"},
    {"id": "caution_recipient", "case": "한 계정이 짧은 시간에 수취인과 연락처를 여러 번 바꾸어 주문했다. 자동화와 실패는 확인되지 않았다.", "expected": "manual-review", "label_basis": "educational-policy"},
    {"id": "caution_inconsistency", "case": "주문 간격은 60초 이상으로 기록됐지만 같은 1분에 수백 회 주문했다고 보고됐다. 입력 오류 또는 자동화 여부를 확인해야 한다.", "expected": "manual-review", "label_basis": "educational-policy"},
    {"id": "risk_automation_velocity", "case": "자동화 스크립트로 의심되는 주문이 1분에 수십 회 반복됐고 동일 상품을 짧은 간격으로 요청했다.", "expected": "decline", "label_basis": "educational-policy"},
    {"id": "risk_multi_account", "case": "세 계정이 동일 기기, 네트워크, 배송지와 연락처를 공유하고 서로 다른 결제수단으로 반복 주문했다. 인증 실패도 5회 발생했다.", "expected": "decline", "label_basis": "educational-policy"},
    {"id": "risk_payment_churn", "case": "한 계정이 결제수단을 5번 바꾸며 주문했고 결제와 인증 실패가 4회 누적됐다.", "expected": "decline", "label_basis": "educational-policy"},
    {"id": "risk_limit_evasion", "case": "한 계정이 구매 한도를 피하려고 같은 상품을 여러 건으로 나누어 1분 동안 7회 주문했다.", "expected": "decline", "label_basis": "educational-policy"},
    {"id": "risk_recipient_network", "case": "여러 계정이 같은 수취인 연락처와 배송지를 공유하고 고가 상품을 서로 다른 결제수단으로 분할 주문해 한도 회피 정황이 있다.", "expected": "decline", "label_basis": "educational-policy"},
]


def _percentile(values: list[float], percentile: float) -> float:
    return sorted(values)[round((len(values) - 1) * percentile)] if values else 0.0


def evaluate_strategy(cases: list[dict[str, str]], runner: Callable[..., dict[str, Any]], strategy: Strategy) -> dict[str, Any]:
    """Evaluate a runner without external writes; exceptions are reported as rows."""
    labels = ("approve", "manual-review", "decline")
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = perf_counter()
        try:
            result = runner(case_text=case["case"], strategy=strategy)
            predicted = str(result["recommendation"])
            rows.append({**case, "predicted": predicted, "correct": predicted == case["expected"], "latency_ms": (perf_counter() - started) * 1000, "margin": result.get("margin"), "error": None})
        except Exception as error:
            rows.append({**case, "predicted": None, "correct": False, "latency_ms": (perf_counter() - started) * 1000, "margin": None, "error": f"{type(error).__name__}: {error}"})
    matrix = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for row in rows:
        if row["predicted"] in labels:
            matrix[row["expected"]][row["predicted"]] += 1
    per_class: dict[str, Any] = {}
    f1s = []
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[actual][label] for actual in labels if actual != label)
        fn = sum(matrix[label][predicted] for predicted in labels if predicted != label) + sum(row["expected"] == label and row["predicted"] is None for row in rows)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1}
        f1s.append(f1)
    latency = [row["latency_ms"] for row in rows]
    return {
        "strategy": strategy, "total": len(rows),
        "accuracy": sum(row["correct"] for row in rows) / len(rows) if rows else 0.0,
        "macro_f1": sum(f1s) / len(f1s), "per_class": per_class,
        "confusion_matrix": matrix,
        "high_risk_false_negative_rate": 1 - per_class["decline"]["recall"],
        "normal_false_positive_rate": 1 - per_class["approve"]["precision"] if any(row["predicted"] == "approve" for row in rows) else 0.0,
        "latency_ms": {"average": sum(latency) / len(latency) if latency else 0.0, "p50": median(latency) if latency else 0.0, "p95": _percentile(latency, .95)},
        "model_calls_per_request": 1 if strategy in {"v2", "v3"} else 2,
        "rows": rows,
    }


def benchmark_strategies(
    settings: Settings,
    cases: list[dict[str, str]] | None = None,
    enable_policy_validation: bool = False,
    enable_uncertainty_detection: bool = False,
) -> list[dict[str, Any]]:
    """Run V1/V2/V3 against identical cases, with gates explicitly selected."""
    data = cases or SYNTHETIC_EVALUATION_CASES
    return [evaluate_strategy(data, lambda case_text, strategy: run_decision_recommendation(case_text, settings, strategy=strategy, enable_policy_validation=enable_policy_validation, enable_uncertainty_detection=enable_uncertainty_detection), strategy) for strategy in ("v1", "v2", "v3")]
