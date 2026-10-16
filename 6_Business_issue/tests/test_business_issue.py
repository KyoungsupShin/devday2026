import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "6_Business_issue" / "src"))

from business_issue import solve_business_issue
from kyc_issue import solve_kyc_issue
from receivables_ra_issue import solve_receivables_ra_issue
from seizure_aml_multiagent import run_seizure_aml_multiagent


class BusinessIssueTests(unittest.TestCase):
    def test_replenishment_is_routed_and_requires_approval(self):
        result = solve_business_issue()

        self.assertEqual(result["route"]["selected"], "business-agent")
        self.assertTrue(result["business_agent_prompt_loaded"])
        self.assertEqual(result["action"], "approval_required")
        self.assertFalse(result["write_performed"])

    def test_policy_calculation_stays_under_budget(self):
        result = solve_business_issue()
        recommendation = result["recommendation"]

        self.assertEqual(recommendation["total_order_cost_krw"], 9_580_000)
        self.assertEqual(recommendation["remaining_budget_krw"], 420_000)
        self.assertTrue(recommendation["within_budget"])
        self.assertEqual(len(recommendation["lines"]), 3)
        self.assertEqual(recommendation["lines"][1]["discount_rate"], 0.1)

    def test_kyc_is_sent_to_enhanced_due_diligence_without_activation(self):
        result = solve_kyc_issue()

        self.assertEqual(result["route"]["selected"], "business-agent")
        self.assertEqual(result["assessment"]["decision"], "enhanced_due_diligence")
        self.assertIn("unverified_ubo", result["assessment"]["risk_flags"])
        self.assertFalse(result["assessment"]["account_activation_allowed"])
        self.assertEqual(result["action"], "compliance_approval_required")

    def test_receivables_ra_requires_conditional_credit_release(self):
        result = solve_receivables_ra_issue()

        self.assertEqual(result["route"]["selected"], "business-agent")
        self.assertEqual(result["assessment"]["decision"], "conditional_release")
        self.assertEqual(result["assessment"]["post_order_exposure_krw"], 93_000_000)
        self.assertEqual(result["assessment"]["over_limit_amount_krw"], 13_000_000)
        self.assertIn("overdue_ratio_exceeded", result["assessment"]["risk_flags"])
        self.assertFalse(result["assessment"]["shipment_release_allowed"])
        self.assertEqual(result["action"], "credit_manager_approval_required")

    def test_financial_multiagent_delegates_aml_and_stops_for_human_review(self):
        result = run_seizure_aml_multiagent()

        self.assertEqual(result["route"]["selected"], "business-agent")
        self.assertTrue(result["deep_orchestrator_prompt_loaded"])
        self.assertIn("aml", result["artifacts"])
        self.assertEqual(result["artifacts"]["aml"]["assessment"], "review_required")
        self.assertEqual(len(result["artifacts"]["graph"]["rapid_pass_through_events"]), 2)
        self.assertTrue(any(event["event"] == "replanned" for event in result["trace"]))
        self.assertTrue(any(event["event"] == "delegated" for event in result["trace"]))
        self.assertEqual(result["action"], "legal_and_compliance_approval_required")
        self.assertFalse(result["asset_restriction_performed"])
        self.assertFalse(result["aml_report_filed"])


if __name__ == "__main__":
    unittest.main()
