import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "5_harness"))

from src.delegation_a2a import run_delegation_a2a


class DelegationA2ATests(unittest.TestCase):
    def test_delegation_reaches_writer_then_user_with_one_correlation_id(self):
        result = run_delegation_a2a("재고를 조사해 발주 검토 보고서를 작성해줘.")

        self.assertTrue(result["verification"]["passed"])
        self.assertTrue(result["verification"]["same_correlation_id"])
        self.assertTrue(result["verification"]["no_external_write"])
        self.assertEqual(
            result["verification"]["actual_hops"],
            [("orchestrator", "researcher"), ("researcher", "analyst_writer"), ("analyst_writer", "user")],
        )
        self.assertIn("SKU-A", result["report"]["summary"])

    def test_empty_request_is_rejected(self):
        with self.assertRaises(ValueError):
            run_delegation_a2a("  ")


if __name__ == "__main__":
    unittest.main()
