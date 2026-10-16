import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "4_agent_patterns"))

from lab_common.config import Settings
from lab_common.models import RankedCandidate, RouteDecision
from src.food_agents import FOOD_AGENT_DEFINITIONS, list_food_agents, run_food_agent
from src.food_tools import execute_food_tool, latest_marketing_html_draft
from src.routing import FAST_ROUTE_CANDIDATES, decide
from src.workflow import run_workflow, run_workflow_stream


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings("", "", "", "", "default", "gpt-5.6-luna", "", "", "cohere-reranker", False)

    def test_all_six_food_specialists_are_registered(self):
        self.assertEqual(
            [agent.id for agent in FOOD_AGENT_DEFINITIONS],
            ["work-planning", "food-rnd", "procurement", "quality-assurance", "marketing", "finance"],
        )

    def test_agent_configuration_is_public_and_exposes_tool_types(self):
        agents = list_food_agents()
        self.assertEqual(len(agents), 6)
        self.assertTrue(all(agent["system_prompt"] for agent in agents))
        tool_types = {tool["type"] for agent in agents for tool in agent["tools"]}
        self.assertIn("Function / calculation", tool_types)
        self.assertIn("API / read-only", tool_types)
        self.assertIn("Agent as a Tool", tool_types)

    def test_finance_agent_executes_assigned_tool_call_before_final_answer(self):
        tool_call = SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(name="unit_economics", arguments='{"retail_price_krw": 4500, "unit_cost_krw": 2700}'),
        )
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tool_call]))])
        with patch("src.food_agents.chat_tool_completion", return_value=response), patch("src.food_agents.chat_text", return_value="공헌이익은 1,800원입니다."):
            result = run_food_agent("finance", "4,500원 도시락 수익성을 검토해줘", self.settings)
        self.assertEqual(result["tool_calls"][0]["name"], "unit_economics")
        self.assertEqual(result["tool_calls"][0]["result"]["contribution_krw"], 1800)

    def test_marketing_agent_as_tool_generates_an_html_draft(self):
        with patch("src.food_tools.chat_text", return_value="<section><h1>프로틴 런치</h1></section>") as html_agent:
            result = execute_food_tool(
                "generate_marketing_html",
                {"product_name": "프로틴 런치", "positioning": "직장인용 고단백 도시락", "key_messages": ["단백질 30g 이상"]},
                request="도시락 기획",
                settings=self.settings,
            )
        self.assertEqual(result["agent_label"], "Marketing HTML Agent")
        self.assertIn("프로틴 런치", result["html"])
        self.assertEqual(latest_marketing_html_draft()["html"], result["html"])
        self.assertTrue(html_agent.called)

    def test_api_tool_returns_read_only_product_data(self):
        fake_response = Mock()
        fake_response.json.return_value = {"products": [{"product_name": "Protein Chicken", "nutrition_grades": "a", "nutriments": {"proteins_100g": 20}}]}
        with patch("src.food_tools.requests.get", return_value=fake_response) as get:
            result = execute_food_tool("open_food_facts_search", {"query": "chicken breast"})
        self.assertEqual(result["source"], "Open Food Facts public API")
        self.assertEqual(result["products"][0]["name"], "Protein Chicken")
        self.assertTrue(get.called)

    def test_tied_route_is_marked_low_confidence(self):
        self.assertEqual([candidate.id for candidate in FAST_ROUTE_CANDIDATES], ["chat", "work"])
        ranked = [
            RankedCandidate(FAST_ROUTE_CANDIDATES[0], 0.5),
            RankedCandidate(FAST_ROUTE_CANDIDATES[1], 0.5),
        ]
        with patch("src.routing.cohere_rank", return_value=(ranked, "btp_cohere_rerank")):
            decision = decide("???", FAST_ROUTE_CANDIDATES, self.settings, min_margin=0.25)
        self.assertTrue(decision.fallback)

    def test_low_confidence_chat_does_not_start_agents(self):
        decision = RouteDecision("chat", {"chat": 0.5, "work": 0.4}, 0.1, "btp_cohere_rerank", fallback=True)
        with patch("src.workflow.decide", return_value=decision), patch("src.workflow.run_food_agent") as run_agent:
            events = list(run_workflow_stream("안녕", self.settings, min_margin=1.01))
        self.assertFalse(run_agent.called)
        self.assertEqual(events[-1]["result"]["route"], "chat")
        self.assertTrue(events[0]["trace_event"]["payload"]["low_confidence"])

    def test_food_workflow_streams_all_agents_with_dependencies(self):
        calls: list[tuple[str, str]] = []

        def fake_agent(agent_id, request, settings, on_delta=None):
            calls.append((agent_id, request))
            if on_delta:
                on_delta(f"{agent_id} partial answer")
            return {"agent_id": agent_id, "agent_label": agent_id, "answer": f"{agent_id} answer"}

        decision = RouteDecision("work", {"chat": 0.1, "work": 0.9}, 0.8, "btp_cohere_rerank")
        with patch("src.workflow.decide", return_value=decision), patch("src.workflow.run_food_agent", side_effect=fake_agent):
            events = list(run_workflow_stream("고단백 도시락을 개발해줘", self.settings))
            result = run_workflow("고단백 도시락을 개발해줘", self.settings)

        completed = [event["agent_result"]["agent_id"] for event in events if event["type"] == "agent_completed"]
        streamed = [event["agent_id"] for event in events if event["type"] == "agent_delta"]
        self.assertCountEqual(completed, [agent.id for agent in FOOD_AGENT_DEFINITIONS])
        self.assertCountEqual(streamed, [agent.id for agent in FOOD_AGENT_DEFINITIONS])
        self.assertIn("[work-planning 결과]\nwork-planning answer", next(request for agent_id, request in calls if agent_id == "food-rnd"))
        self.assertIn("[food-rnd 결과]\nfood-rnd answer", next(request for agent_id, request in calls if agent_id == "procurement"))
        self.assertIn("[procurement 결과]\nprocurement answer", next(request for agent_id, request in calls if agent_id == "finance"))
        self.assertEqual(result["route"], "work")
        self.assertEqual(result["result"], "finance answer")


if __name__ == "__main__":
    unittest.main()
