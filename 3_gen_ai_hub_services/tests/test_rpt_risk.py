from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "1_gen_ai_hub" / "src"), str(ROOT / "3_gen_ai_hub_services")]

from lab_common.config import Settings
from src.rpt_risk.lab_core import (
    AUDIT_COLUMNS,
    EDUCATIONAL_COLUMNS,
    FEATURE_COLUMNS,
    PREDICTION_PLACEHOLDER,
    PREDICTION_TABLE_COLUMNS,
    RPT_MAX_QUERY_ROWS,
    _stratified_split,
    build_rpt_request,
    create_educational_dataset,
    export_rpt_risk_results,
    explain_rpt_risk_case,
    inspect_risk_dataset,
    predict_rpt_risk_case,
    preview_risk_dataset,
    rpt_deployment_url,
    run_rpt_risk_evaluation,
    run_rpt_permutation_importance,
)


def settings(**overrides: str) -> Settings:
    values = {
        "base_url": "https://aicore.example",
        "auth_url": "https://auth.example",
        "client_id": "id",
        "client_secret": "secret",
        "resource_group": "default",
        "llm_model": "model",
        "rerank_endpoint": "",
        "rerank_api_key": "",
        "rerank_model": "rerank",
        "allow_write_tools": False,
    }
    values.update(overrides)
    return Settings(**values)


def educational_rows() -> list[dict[str, str]]:
    rows = []
    for index in range(10):
        rows.append({
            "record_id": f"risk-{index:05d}",
            "age": str(25 + index), "income": str(30000 + index * 1000),
            "num_kids": str(index % 3), "num_cards": str(1 + index % 2),
            "how_paid": "monthly", "employed_days": str(1000 + index),
            "store_car": "1", "loans": "0", "mortgage": "y",
            "mortgage_amount": "50000", "credit_score": "0,70",
            "audit_gender": "f" if index % 2 else "m",
            "audit_marital": "single" if index % 2 else "married",
            "risk_label": "1" if index < 5 else "0",
        })
    return rows


class RPTRiskTests(unittest.TestCase):
    def write_dataset(self, directory: str) -> Path:
        path = Path(directory) / "educational.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=EDUCATIONAL_COLUMNS, delimiter=";")
            writer.writeheader()
            writer.writerows(educational_rows())
        return path

    def test_raw_csv_conversion_removes_identifier_and_validates_semicolon_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.csv"
            target = Path(directory) / "target.csv"
            source.write_text(
                "ID;AGE;INCOME;GENDER;MARITAL;NUMKIDS;NUMCARDS;HOWPAID;EMPLOYED_DAYS;STORECAR;LOANS;LOAN_AMOUNT;10560;;;MORTGAGE;MORTGAGE_AMOUNT;CREDIT_SCORE;RISK;RISK\n"
                "cust-123;44;59944;m;married;1;2;monthly;6994;2;0;;0;0;;y;134000;0,76;good risk;1\n",
                encoding="utf-8",
            )
            result = create_educational_dataset(source, target)
            report = inspect_risk_dataset(target)

        self.assertEqual(result["source_rows"], 1)
        self.assertEqual(report["row_count"], 1)
        self.assertNotIn("ID", report["feature_columns"])
        self.assertEqual(report["target_distribution"], {"1": 1})

    def test_bad_educational_header_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.csv"
            path.write_text("bad;header\n1;2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "예상 스키마"):
                inspect_risk_dataset(path)

    def test_preview_is_bounded_and_has_no_source_customer_identifier(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_dataset(directory)
            preview = preview_risk_dataset(path, limit=3)

        self.assertEqual(preview["displayed_rows"], 3)
        self.assertEqual(len(preview["rows"]), 3)
        self.assertNotIn("source_id", preview["columns"])
        self.assertEqual(preview["rows"][0]["record_id"], "risk-00000")
        with self.assertRaisesRegex(ValueError, "1에서 500"):
            preview_risk_dataset(path, limit=0)

    def test_split_is_deterministic_and_rpt_request_excludes_audit_attributes(self):
        rows = educational_rows()
        support_a, holdout_a = _stratified_split(rows)
        support_b, holdout_b = _stratified_split(rows)
        request = build_rpt_request(support_a, holdout_a)

        self.assertEqual([row["record_id"] for row in support_a], [row["record_id"] for row in support_b])
        self.assertEqual([row["record_id"] for row in holdout_a], [row["record_id"] for row in holdout_b])
        self.assertFalse({row["record_id"] for row in support_a} & {row["record_id"] for row in holdout_a})
        self.assertEqual(sum(row["risk_label"] == "1" for row in support_a), 4)
        self.assertEqual(sum(row["risk_label"] == "1" for row in holdout_a), 1)
        self.assertEqual(len(request["rows"]), len(rows))
        self.assertEqual(sum(row["risk_label"] == PREDICTION_PLACEHOLDER for row in request["rows"]), len(holdout_a))
        self.assertTrue(all(column not in request["rows"][0] for column in AUDIT_COLUMNS))
        self.assertEqual(set(request["rows"][0]) - {"record_id", "risk_label"}, set(FEATURE_COLUMNS))

    def test_evaluation_maps_predictions_metrics_and_audit_without_btp_call(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_dataset(directory)
            seen = {}

            def predictor(request, deployment_url):
                seen["url"] = deployment_url
                query_count = sum(row["risk_label"] == PREDICTION_PLACEHOLDER for row in request["rows"])
                return {
                    "predictions": [{"risk_label": [{"prediction": "1" if index == 0 else "0", "confidence": 0.8} for index in range(query_count)]}],
                    "metadata": {"num_query_rows": query_count},
                }

            result = run_rpt_risk_evaluation(settings(), path, predictor=predictor)

        self.assertEqual(seen["url"], "test://rpt")
        self.assertEqual(result["request_summary"]["support_rows"], 8)
        self.assertEqual(result["request_summary"]["holdout_rows"], 2)
        self.assertEqual(len(result["predictions"]), 2)
        self.assertEqual(len(result["prediction_table"]), 2)
        self.assertEqual(tuple(result["prediction_table"][0]), PREDICTION_TABLE_COLUMNS)
        self.assertIn("rpt_prediction", result["prediction_table"][0])
        self.assertIn("audit_gender", result["audit"])
        self.assertIn("자동 승인·거절", result["execution_boundary"])

    def test_evaluation_batches_large_holdout_without_dropping_rows(self):
        calls = []

        def predictor(request, _url):
            query_count = sum(row["risk_label"] == PREDICTION_PLACEHOLDER for row in request["rows"])
            calls.append(query_count)
            return {"predictions": [{"risk_label": [{"prediction": "0"} for _ in range(query_count)]}], "metadata": {"num_query_rows": query_count}}

        result = run_rpt_risk_evaluation(settings(), predictor=predictor)

        self.assertEqual(calls, [RPT_MAX_QUERY_ROWS, 824 - RPT_MAX_QUERY_ROWS])
        self.assertEqual(sum(calls), result["request_summary"]["holdout_rows"])
        self.assertEqual(result["request_summary"]["rpt_request_count"], 2)

    def test_completed_evaluation_exports_a_local_csv_with_prediction_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset = self.write_dataset(directory)
            evaluation = run_rpt_risk_evaluation(
                settings(), dataset,
                predictor=lambda request, _url: {
                    "predictions": [{"risk_label": [{"prediction": "0", "confidence": 0.8} for row in request["rows"] if row["risk_label"] == PREDICTION_PLACEHOLDER]}],
                    "metadata": {},
                },
            )
            exported = export_rpt_risk_results(evaluation, Path(directory) / "results")
            with Path(exported["path"]).open("r", encoding="utf-8-sig", newline="") as handle:
                saved_rows = list(csv.DictReader(handle))

        self.assertEqual(exported["row_count"], 2)
        self.assertEqual(len(saved_rows), 2)
        self.assertIn("rpt_prediction", saved_rows[0])
        self.assertIn("rpt_accuracy", saved_rows[0])
        self.assertIn("로컬 CSV", exported["execution_boundary"])

    def test_export_requires_a_completed_evaluation(self):
        with self.assertRaisesRegex(ValueError, "먼저 RPT 평가"):
            export_rpt_risk_results({})

    def test_permutation_importance_keeps_support_fixed_and_scores_every_feature(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_dataset(directory)
            calls = []

            def predictor(request, _url):
                support = [row for row in request["rows"] if row["risk_label"] != PREDICTION_PLACEHOLDER]
                query = [row for row in request["rows"] if row["risk_label"] == PREDICTION_PLACEHOLDER]
                calls.append((len(support), len(query)))
                return {"predictions": [{"risk_label": [{"prediction": "0"} for _ in query]}], "metadata": {}}

            result = run_rpt_permutation_importance(settings(), path, predictor=predictor)

        self.assertEqual(len(result["feature_importance"]), len(FEATURE_COLUMNS))
        self.assertEqual(result["request_summary"]["rpt_request_count"], len(FEATURE_COLUMNS) + 1)
        self.assertTrue(all(support_count == 8 and query_count == 2 for support_count, query_count in calls))

    def test_local_counterfactual_compares_one_feature_with_a_reference_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_dataset(directory)
            seen_values = []

            def predictor(request, _url):
                query = next(row for row in request["rows"] if row["risk_label"] == PREDICTION_PLACEHOLDER)
                seen_values.append(query["age"])
                return {"predictions": [{"risk_label": [{"prediction": "1" if query["age"] > 25 else "0", "confidence": 0.8}]}], "metadata": {}}

            case = {column: educational_rows()[0][column] for column in FEATURE_COLUMNS}
            result = explain_rpt_risk_case(case, "age", settings(), path, predictor=predictor)

        self.assertEqual(result["feature"], "age")
        self.assertEqual(result["request_summary"]["rpt_request_count"], 2)
        self.assertEqual(len(seen_values), 2)
        self.assertNotEqual(result["baseline"]["feature_value"], result["counterfactual"]["feature_value"])
        with self.assertRaisesRegex(ValueError, "분석할 feature"):
            explain_rpt_risk_case(case, "audit_gender", settings(), path, predictor=lambda *_: {})

    def test_single_case_uses_only_declared_features_and_checks_response_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_dataset(directory)
            case = {column: educational_rows()[0][column] for column in FEATURE_COLUMNS}
            result = predict_rpt_risk_case(
                case, settings(), path,
                predictor=lambda request, _url: {"predictions": [{"risk_label": [{"prediction": "1", "confidence": 0.91}]}], "metadata": {"num_query_rows": 1}},
            )
            self.assertEqual(result["classification"], "1")
            self.assertEqual(result["confidence"], 0.91)
            with self.assertRaisesRegex(RuntimeError, "예측 수"):
                run_rpt_risk_evaluation(settings(), path, predictor=lambda *_: {"predictions": []})

    def test_deployment_lookup_honors_model_and_optional_id(self):
        loader = lambda _settings: [{
            "id": "rpt-123", "deploymentUrl": "https://rpt.example/inference/", "details": {
                "resources": {"backend_details": {"model": {"name": "sap-rpt-1.5-large"}}}
            },
        }]
        self.assertEqual(rpt_deployment_url(settings(), loader), "https://rpt.example/inference")
        self.assertEqual(rpt_deployment_url(settings(rpt_deployment_id="rpt-123"), loader), "https://rpt.example/inference")
        with self.assertRaisesRegex(RuntimeError, "RPT 배포"):
            rpt_deployment_url(settings(rpt_deployment_id="missing"), loader)


if __name__ == "__main__":
    unittest.main()
