from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
import unittest
import json

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "1_gen_ai_hub" / "src"))
sys.path.insert(0, str(ROOT / "2_gen_ai_hub_llm"))

from lab_common.config import Settings
from lab_common.models import RankedCandidate
from src.reranker.lab_core import (
    APPLICATION_DECISIONS,
    DecisionResult,
    MULTI_PROTOTYPE_DECISIONS,
    STRUCTURED_DECISIONS,
    build_rerank_payload,
    build_reranker_query,
    build_structured_query,
    extract_observations,
    recommend,
    run_decision_recommendation,
    validate_policy,
)
from src.reranker.benchmark import SYNTHETIC_EVALUATION_CASES, evaluate_strategy
from src.reranker.demo_cases import ORDER_RISK_DEMO_CASES


def test_settings() -> Settings:
    return Settings(
        base_url="https://example.invalid",
        auth_url="https://example.invalid",
        client_id="test",
        client_secret="test",
        resource_group="default",
        llm_model="test-model",
        rerank_endpoint="",
        rerank_api_key="",
        rerank_model="cohere-rerank-pro",
        allow_write_tools=False,
    )


class DecisionModelTests(unittest.TestCase):
    def test_recommendation_uses_llm_summary_then_cohere_reranker(self):
        ranked = [
            RankedCandidate(APPLICATION_DECISIONS[0], 0.88),
            RankedCandidate(APPLICATION_DECISIONS[1], 0.42),
            RankedCandidate(APPLICATION_DECISIONS[2], 0.12),
        ]
        with (
            patch(
                "src.reranker.lab_core._summary", return_value="LLM 정책 근거 요약"
            ) as summary,
            patch(
                "src.reranker.lab_core._rank",
                return_value=(ranked, "llm_policy_btp_cohere_rerank"),
            ) as rerank,
        ):
            result = recommend("10월 1일 분유 2개 구매", settings=test_settings(), strategy="v1")

        self.assertEqual(result.recommendation, "approve")
        self.assertEqual(result.engine, "llm_policy_btp_cohere_rerank")
        self.assertEqual(result.scores["approve"], 0.88)
        self.assertEqual(result.policy_summary, "LLM 정책 근거 요약")
        self.assertTrue(result.policy_id.startswith("sha256:"))
        self.assertFalse(result.requires_human_review)
        summary.assert_called_once()
        rerank.assert_called_once_with(
            "LLM 정책 근거 요약", APPLICATION_DECISIONS, test_settings()
        )

    def test_v2_builds_fact_only_query_without_a_new_llm_call(self):
        query, facts = build_structured_query(
            "인증된 고객이 주문 간격 60초 이상을 지키며 1분에 1회 주문을 시도했다. 중복, 실패, 한도 초과는 없다."
        )
        self.assertTrue(facts.authenticated)
        self.assertEqual(facts.min_order_interval_seconds, 60)
        self.assertEqual(facts.orders_per_minute, 1)
        self.assertEqual(facts.duplicate_order_count, 0)
        self.assertEqual(facts.failed_order_count, 0)
        self.assertFalse(facts.limit_exceeded)
        self.assertIn("task: customer_order_behavior_classification", query)
        self.assertNotIn("NORMAL", query)
        self.assertNotIn("HIGH_RISK", query)

    def test_default_v3_sends_original_text_and_facts_to_reranker_without_policy_override(self):
        ranked = [
            RankedCandidate(MULTI_PROTOTYPE_DECISIONS[0], .9),
            RankedCandidate(MULTI_PROTOTYPE_DECISIONS[2], .4),
            RankedCandidate(MULTI_PROTOTYPE_DECISIONS[4], .1),
        ]
        case = "인증된 고객이 1분에 11212회 주문을 시도했다. 중복, 실패, 한도 초과는 없다."
        expected_query, _ = build_reranker_query(case)
        with patch("src.reranker.lab_core._rank", return_value=(ranked, "fixture")) as rerank:
            result = recommend(case, settings=test_settings())
        rerank.assert_called_once_with(expected_query, MULTI_PROTOTYPE_DECISIONS, test_settings())
        self.assertEqual(result.recommendation, "approve")
        self.assertFalse(result.requires_human_review)
        self.assertEqual(result.policy_summary, expected_query)
        self.assertEqual(result.observations["orders_per_minute"], 11212)

    def test_reranker_query_keeps_original_statement_and_explicit_facts(self):
        case = "인증된 고객이 1분에 11212회 주문을 시도했다. 중복, 실패, 한도 초과는 없다."
        query, facts = build_reranker_query(case)
        self.assertEqual(facts.orders_per_minute, 11212)
        self.assertIn("orders_per_minute: 11212 per_minute", query)
        self.assertIn(f"customer_statement: |\n  {case}", query)
        self.assertNotIn("recommendation:", query)

    def test_unknown_is_not_conflated_with_false_or_zero(self):
        facts = extract_observations("authenticated: true\norders_per_minute: 1")
        self.assertIsNone(facts.duplicate_order_count)
        self.assertIsNone(facts.limit_exceeded)
        self.assertIsNone(facts.automation_detected)

    def test_payload_keeps_model_and_structured_documents(self):
        query, _ = build_structured_query("authenticated: true\norders_per_minute: 1")
        body = build_rerank_payload(query, STRUCTURED_DECISIONS, "cohere-rerank-pro")
        self.assertEqual(body["model"], "cohere-rerank-pro")
        self.assertEqual(body["top_n"], 3)
        self.assertEqual(body["documents"][0], STRUCTURED_DECISIONS[0].description)

    def test_caution_candidate_explicitly_covers_frequent_orders(self):
        caution_document = next(candidate.description for candidate in STRUCTURED_DECISIONS if candidate.id == "manual-review")
        self.assertIn("빈번한 주문", caution_document)
        for condition in (
            "order_velocity_or_concentration",
            "payment_instrument_irregularity",
            "account_device_network_linkage",
            "delivery_recipient_contact_anomaly",
            "identity_or_behavior_inconsistency",
        ):
            self.assertIn(condition, caution_document)

    def test_high_risk_candidate_requires_compound_order_risk_patterns(self):
        high_risk_document = next(candidate.description for candidate in STRUCTURED_DECISIONS if candidate.id == "decline")
        for condition in (
            "automated_extreme_velocity",
            "multi_account_linkage",
            "repeated_payment_failure_or_churn",
            "limit_evasion_or_structuring",
            "recipient_or_delivery_network_abuse",
        ):
            self.assertIn(condition, high_risk_document)
        self.assertIn("복합·반복", high_risk_document)

    def test_demo_cases_cover_labels_and_synthetic_benchmark_is_label_balanced(self):
        demo_counts = {label: sum(case["expected"] == label for case in ORDER_RISK_DEMO_CASES) for label in ("approve", "manual-review", "decline")}
        benchmark_counts = {label: sum(case["expected"] == label for case in SYNTHETIC_EVALUATION_CASES) for label in ("approve", "manual-review", "decline")}
        self.assertEqual(demo_counts, {"approve": 2, "manual-review": 5, "decline": 5})
        self.assertEqual(benchmark_counts, {"approve": 5, "manual-review": 5, "decline": 5})
        self.assertTrue(all(case["case"].strip() and case["name"].strip() for case in ORDER_RISK_DEMO_CASES))

    def test_policy_validation_checks_only_explicit_facts(self):
        findings = validate_policy(extract_observations(
            "orders_per_minute: 7\nautomation_detected: true\nfailed_order_count: 3"
        ))
        self.assertTrue(findings["requires_review"])
        self.assertGreaterEqual(len(findings["findings"]), 2)
        self.assertFalse(validate_policy(extract_observations("orders_per_minute: 7"))["requires_review"])

    def test_korean_frequency_with_spacing_is_extracted_for_limit_avoidance(self):
        findings = validate_policy(extract_observations(
            "한 계정이 1분 동안 7회 주문을 시도했다. 여러 건으로 나누어 구매했다."
        ))
        self.assertEqual(findings["recommended_class"], "decline")

    def test_v3_has_equal_prototype_count_per_class(self):
        counts = {key: sum(item.id == key for item in MULTI_PROTOTYPE_DECISIONS) for key in ("approve", "manual-review", "decline")}
        self.assertEqual(counts, {"approve": 2, "manual-review": 2, "decline": 2})

    def test_benchmark_reports_accuracy_f1_confusion_and_latency(self):
        cases = [
            {"id": "a", "case": "normal", "expected": "approve"},
            {"id": "b", "case": "risk", "expected": "decline"},
        ]
        def fixture_runner(case_text, strategy):
            return {"recommendation": "approve" if case_text == "normal" else "decline", "margin": .4}
        report = evaluate_strategy(cases, fixture_runner, "v2")
        self.assertEqual(report["accuracy"], 1.0)
        self.assertEqual(report["macro_f1"], 2 / 3)
        self.assertEqual(report["confusion_matrix"]["decline"]["decline"], 1)
        self.assertEqual(report["model_calls_per_request"], 1)

    def test_close_scores_force_manual_review_without_external_state_change(self):
        ranked = [
            RankedCandidate(APPLICATION_DECISIONS[0], 0.55),
            RankedCandidate(APPLICATION_DECISIONS[1], 0.549),
            RankedCandidate(APPLICATION_DECISIONS[2], 0.10),
        ]
        with (
            patch("src.reranker.lab_core._summary", return_value="LLM 정책 근거 요약"),
            patch(
                "src.reranker.lab_core._rank",
                return_value=(ranked, "llm_policy_btp_cohere_rerank"),
            ),
        ):
            result = recommend(
                "모호한 주문 사례", settings=test_settings(), min_margin=0.005
            )

        self.assertEqual(result.recommendation, "manual-review")
        self.assertTrue(result.requires_human_review)
        self.assertIn("최소 margin", result.reason)

    def test_public_runner_returns_json_friendly_read_only_result(self):
        calls = []

        def fake_runner(case_text, **kwargs):
            calls.append((case_text, kwargs))
            return DecisionResult(
                recommendation="approve",
                scores={"approve": 0.91, "manual-review": 0.22, "decline": 0.02},
                margin=0.69,
                engine="fixture",
                reason="fixture reason",
                requires_human_review=False,
                policy_summary="fixture policy summary",
                policy_id="sha256:fixture",
            )

        outcome = run_decision_recommendation(
            "  정상 주문  ",
            settings=test_settings(),
            recommendation_runner=fake_runner,
        )

        self.assertEqual(calls[0][0], "정상 주문")
        self.assertEqual(outcome["recommendation_label"], "정상 고객")
        self.assertFalse(outcome["requires_human_review"])
        self.assertEqual(outcome["ranked_candidates"][0]["id"], "approve")
        self.assertEqual(outcome["policy_summary"], "fixture policy summary")
        self.assertEqual(outcome["policy_id"], "sha256:fixture")
        self.assertEqual(
            outcome["decision_thresholds"], {"min_score": 0.0, "min_margin": 0.0}
        )
        self.assertIn("상태는 변경하지 않았습니다", outcome["action"])
        json.dumps(outcome)

    def test_public_runner_rejects_blank_case_without_calling_runner(self):
        with self.assertRaisesRegex(ValueError, "고객 행동"):
            run_decision_recommendation(
                "  ",
                settings=test_settings(),
                recommendation_runner=lambda *_args, **_kwargs: self.fail(
                    "runner should not be called"
                ),
            )

    def test_ai_core_configuration_is_required(self):
        with self.assertRaisesRegex(
            RuntimeError, "AI Core LLM 및 Cohere reranker 설정"
        ):
            recommend("10월 1일 분유 2개 구매")


if __name__ == "__main__":
    unittest.main()
