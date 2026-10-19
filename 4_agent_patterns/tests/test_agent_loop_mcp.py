import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "4_agent_patterns"))

from lab_common.config import Settings
from src.agent_loop_mcp.lab_core import list_food_mcp_tools, run_food_mcp_loop


class AgentLoopMcpTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings("base", "auth", "client", "secret", "default", "gpt-5.6-luna", "", "", "cohere-reranker", False)

    def test_food_loop_keeps_the_graph_and_exposes_selected_specialist_tools(self):
        graph_result = {
            "route": "work",
            "result": "출시 권고",
            "agent_results": {
                "food-rnd": {
                    "answer": "제품 라벨 검토",
                    "tool_calls": [{"name": "open_food_facts_search", "arguments": {"query": "chicken breast"}, "result": {"products": []}}],
                }
            },
            "trace": [],
        }
        with patch("src.agent_loop_mcp.lab_core.run_workflow", return_value=graph_result) as workflow:
            result = run_food_mcp_loop("고단백 도시락을 기획해줘", self.settings)
        workflow.assert_called_once_with("고단백 도시락을 기획해줘", self.settings, min_margin=0.0)
        self.assertEqual(result["tool_calls"][0]["agent_id"], "food-rnd")
        self.assertEqual(result["tool_calls"][0]["name"], "open_food_facts_search")
        self.assertIn("existing Agent graph", result["execution_boundary"])
        self.assertTrue(all(not tool["write"] for tool in list_food_mcp_tools()))

    def test_food_loop_returns_no_tool_observations_for_chat_route(self):
        with patch("src.agent_loop_mcp.lab_core.run_workflow", return_value={"route": "chat", "result": "대화 응답", "trace": []}):
            result = run_food_mcp_loop("안녕", self.settings)
        self.assertEqual(result["tool_calls"], [])

if __name__ == "__main__":
    unittest.main()
