from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
import unittest
import json

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "2_gen_ai_hub_llm"))

from lab_common.config import Settings
from lab_common.models import RankedCandidate
from src.reranker.lab_core import (
    APPLICATION_DECISIONS,
    DecisionResult,
    recommend,
    run_decision_recommendation,
)


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
            result = recommend("10월 1일 분유 2개 구매", settings=test_settings())

        self.assertEqual(result.recommendation, "approve")
        self.assertEqual(result.engine, "llm_policy_btp_cohere_rerank")
        self.assertEqual(result.scores["approve"], 0.88)
        self.assertFalse(result.requires_human_review)
        summary.assert_called_once()
        rerank.assert_called_once_with(
            "LLM 정책 근거 요약", APPLICATION_DECISIONS, test_settings()
        )

    def test_close_scores_force_manual_review_without_external_state_change(self):
        ranked = [
            RankedCandidate(APPLICATION_DECISIONS[0], 0.55),
            RankedCandidate(APPLICATION_DECISIONS[1], 0.50),
            RankedCandidate(APPLICATION_DECISIONS[2], 0.10),
        ]
        with (
            patch("src.reranker.lab_core._summary", return_value="LLM 정책 근거 요약"),
            patch(
                "src.reranker.lab_core._rank",
                return_value=(ranked, "llm_policy_btp_cohere_rerank"),
            ),
        ):
            result = recommend("모호한 주문 사례", settings=test_settings())

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
