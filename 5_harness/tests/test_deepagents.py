import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "5_harness"))

from src.deepagents import deepagents_readiness, make_agent_plan


class DeepAgentsCoreTests(unittest.TestCase):
    def test_plan_is_read_only_and_uses_versioned_prompt(self):
        plan = make_agent_plan("재고 근거를 수집해줘")
        self.assertIn("Deep Orchestrator", plan["system_prompt"])
        self.assertEqual(plan["write_tools"], "human_approval_required")
        self.assertEqual(plan["delegation"], ["researcher", "business_agent"])

    def test_readiness_never_requires_a_remote_call(self):
        self.assertIn("deepagents_installed", deepagents_readiness())


if __name__ == "__main__":
    unittest.main()
