import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "5_harness"))

from src.harness_prompts import default_prompt, hana_overrides


class HarnessPromptTests(unittest.TestCase):
    def test_prompt_snapshot_has_defaults_and_hana_overrides(self):
        self.assertIn("Deep Orchestrator", default_prompt("deep_orchestrator"))
        overrides = hana_overrides()
        self.assertEqual(len(overrides), 3)
        self.assertIn("rerank.specialist_dispatch.business-agent", overrides)


if __name__ == "__main__":
    unittest.main()
