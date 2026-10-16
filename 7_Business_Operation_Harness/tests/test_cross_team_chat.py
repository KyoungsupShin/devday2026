import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "7_Business_Operation_Harness"))

from src.cross_team_chat import TEAM_INTERFACES, agent_prompt, interface_catalog


class CrossTeamChatTests(unittest.TestCase):
    def test_interface_catalog_describes_both_teams(self):
        catalog = interface_catalog()
        self.assertEqual(catalog["business_ops_lead"]["team"], "business_operations")
        self.assertEqual(catalog["customer_ops_lead"]["team"], "customer_operations")

    def test_llm_prompt_only_treats_user_and_prior_messages_as_facts(self):
        prompt = agent_prompt(
            role=TEAM_INTERFACES["inventory_specialist"]["role"],
            task="영향을 분석하세요.",
            user_request="주문 지연 영향이 궁금합니다.",
            prior_messages=[],
        )
        self.assertIn("지어내지 않는다", prompt[0]["content"])
        self.assertIn("주문 지연 영향", prompt[1]["content"])


if __name__ == "__main__":
    unittest.main()
