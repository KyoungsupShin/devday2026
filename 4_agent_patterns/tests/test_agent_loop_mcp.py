import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "4_agent_patterns"))

from lab_common.config import Settings
from src.agent_loop_mcp.lab_core import (
    list_food_mcp_tools,
    run_food_mcp_loop,
    run_food_mcp_loop_steps,
    run_food_mcp_loop_stream,
)
from src.agent_loop_mcp.main import main
from src.agent_loop_mcp.prompts import agent_prompt, get_prompt
from src.agent_loop_mcp.ui import LOOP_SCENARIOS, build_loop_ui


class AgentLoopMcpTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings("base", "auth", "client", "secret", "default", "gpt-5.6-luna", "", "", "cohere-reranker", False)

    def test_loop_runtime_has_no_agent_workflow_import(self):
        loop_root = ROOT / "4_agent_patterns" / "src" / "agent_loop_mcp"
        source = " ".join(path.read_text(encoding="utf-8") for path in loop_root.rglob("*.py"))
        self.assertNotIn("agent_workflow", source)

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
        workflow.assert_called_once_with(
            "고단백 도시락을 기획해줘",
            self.settings,
            min_margin=0.0,
            enable_evaluation=True,
        )
        self.assertEqual(result["tool_calls"][0]["agent_id"], "food-rnd")
        self.assertEqual(result["tool_calls"][0]["name"], "open_food_facts_search")
        self.assertIn("02 Agent loop", result["execution_boundary"])
        self.assertTrue(all(not tool["write"] for tool in list_food_mcp_tools()))

    def test_food_loop_returns_no_tool_observations_for_chat_route(self):
        with patch("src.agent_loop_mcp.lab_core.run_workflow", return_value={"route": "chat", "result": "대화 응답", "trace": []}):
            result = run_food_mcp_loop("안녕", self.settings)
        self.assertEqual(result["tool_calls"], [])

    def test_sequential_stream_exposes_agent_events_and_final_tool_audit(self):
        completed = {
            "route": "work",
            "result": "출시 권고",
            "agent_results": {
                "food-rnd": {
                    "tool_calls": [{"name": "open_food_facts_search", "arguments": {"query": "chicken breast"}}],
                }
            },
            "trace": [],
        }
        stream_events = iter([
            {"type": "agent_started", "trace_event": {"event": "agent_started"}},
            {"type": "agent_completed", "agent_result": {"agent_id": "food-rnd", "tool_calls": []}},
            {"type": "complete", "result": completed},
        ])
        with patch("src.agent_loop_mcp.lab_core.run_workflow_stream", return_value=stream_events) as workflow_stream:
            events = list(run_food_mcp_loop_stream("고단백 도시락을 기획해줘", self.settings))
        workflow_stream.assert_called_once_with(
            "고단백 도시락을 기획해줘",
            self.settings,
            min_margin=0.0,
            enable_evaluation=True,
            sequential_agents=True,
        )
        self.assertEqual([event["type"] for event in events], ["agent_started", "agent_completed", "complete"])
        self.assertEqual(events[-1]["result"]["tool_calls"][0]["agent_id"], "food-rnd")
        self.assertIn("no external write actions", events[-1]["result"]["execution_boundary"])

    def test_lab_steps_groups_one_agent_and_its_tool_calls_per_next_call(self):
        streamed_events = iter([
            {"type": "conversation_observation", "observation": {"use_history": False}, "trace_event": {"event": "conversation_observation"}},
            {"type": "route", "trace_event": {"payload": {"selected": "work"}}},
            {"type": "agent_started", "trace_event": {"payload": {"agent_id": "food-rnd", "rework": False}}},
            {"type": "agent_delta", "agent_id": "food-rnd", "delta": "근거"},
            {"type": "agent_completed", "agent_result": {"agent_id": "food-rnd", "agent_label": "R&D Agent", "answer": "검토안", "tool_calls": [{"name": "open_food_facts_search"}]}, "trace_event": {"event": "agent_completed"}},
            {"type": "complete", "result": {"route": "work", "result": "검토안", "tool_calls": []}},
        ])
        with patch("src.agent_loop_mcp.lab_core.run_food_mcp_loop_stream", return_value=streamed_events) as loop_stream:
            steps = list(run_food_mcp_loop_steps("출시안을 검토해줘", self.settings))
        loop_stream.assert_called_once_with(
            "출시안을 검토해줘",
            self.settings,
            min_margin=0.0,
            sequential_agents=True,
        )
        self.assertEqual([step["step"] for step in steps], ["observer", "route", "agent", "complete"])
        self.assertEqual(steps[2]["tool_calls"][0]["name"], "open_food_facts_search")
        self.assertEqual(steps[2]["deltas"], ["근거"])

    def test_image_html_contract_is_prompted_without_runtime_forcing(self):
        marketing_prompt = agent_prompt("marketing")
        evaluation_prompt = get_prompt("evaluation_middleware")
        self.assertIn("generate_marketing_image first and generate_marketing_html", marketing_prompt)
        self.assertIn("generate_marketing_html with embedded_image=true", evaluation_prompt)

    def test_cli_uses_the_independent_public_loop_api(self):
        with patch("src.agent_loop_mcp.main.run_food_mcp_loop", return_value={"route": "work"}) as loop:
            result = main(["출시안을 검토해줘", "--min-margin", "0.2"])
        loop.assert_called_once_with("출시안을 검토해줘", min_margin=0.2)
        self.assertEqual(result, {"route": "work"})

    def test_loop_ui_exposes_tool_and_middleware_scenarios(self):
        self.assertEqual(
            [scenario["title"] for scenario in LOOP_SCENARIOS],
            ["파일럿 Go / No-Go 평가", "근거 부족 보완 Loop", "프로모션 HTML Tool Audit"],
        )
        app = build_loop_ui(self.settings)
        self.assertTrue(app.blocks)
        app.close()

if __name__ == "__main__":
    unittest.main()
