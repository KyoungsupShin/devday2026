import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "4_agent_patterns"))

from lab_common.config import Settings
from src.a2a import list_a2a_agents, run_food_handoff
from src.agent_loop import list_food_mcp_tools, run_food_mcp_loop


class LoopAndA2ATests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings("base", "auth", "client", "secret", "default", "gpt-5.6-luna", "", "", "cohere-reranker", False)

    def test_food_loop_keeps_the_graph_and_exposes_selected_specialist_tools(self):
        graph_result = {
            "route": "work",
            "result": "출시 권고",
            "agent_results": {
                "finance": {
                    "answer": "손익 검토",
                    "tool_calls": [{"name": "unit_economics", "arguments": {"retail_price_krw": 4500}, "result": {"contribution_krw": 1800}}],
                }
            },
            "trace": [],
        }
        with patch("src.agent_loop.run_workflow", return_value=graph_result) as workflow:
            result = run_food_mcp_loop("고단백 도시락을 기획해줘", self.settings)
        workflow.assert_called_once_with("고단백 도시락을 기획해줘", self.settings, min_margin=0.0)
        self.assertEqual(result["tool_calls"][0]["agent_id"], "finance")
        self.assertEqual(result["tool_calls"][0]["name"], "unit_economics")
        self.assertIn("existing Agent graph", result["execution_boundary"])
        self.assertTrue(all(not tool["write"] for tool in list_food_mcp_tools()))

    def test_food_loop_returns_no_tool_observations_for_chat_route(self):
        with patch("src.agent_loop.run_workflow", return_value={"route": "chat", "result": "대화 응답", "trace": []}):
            result = run_food_mcp_loop("안녕", self.settings)
        self.assertEqual(result["tool_calls"], [])

    def test_a2a_handoff_is_llm_backed_and_contract_explicit(self):
        with patch("src.a2a.chat_text", side_effect=["근거 브리프", "출시 전 검증 권고"]) as chat:
            result = run_food_handoff("고단백 도시락 출시를 검토해줘", self.settings)
        self.assertEqual(result["handoff"]["sender"], "food-researcher")
        self.assertEqual(result["handoff"]["recipient"], "launch-advisor")
        self.assertEqual(result["report"]["payload"]["recommendation"], "출시 전 검증 권고")
        self.assertEqual(chat.call_count, 2)
        self.assertTrue(all(agent["tools"] == [] for agent in list_a2a_agents()))


if __name__ == "__main__":
    unittest.main()
