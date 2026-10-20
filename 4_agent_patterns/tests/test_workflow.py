import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "4_agent_patterns"))

from lab_common.config import Settings
from lab_common.models import RankedCandidate, RouteDecision
from src.agent_workflow.agents.registry import EXECUTABLE_AGENT_IDS
from src.agent_workflow.food_agents import FOOD_AGENT_DEFINITIONS, list_food_agents, plan_work_agents
from src.agent_workflow.lab_core import inspect_route, run_workflow, run_workflow_steps
from src.agent_workflow.prompts import agent_prompt, routing_candidate
from src.agent_workflow.routing import FAST_ROUTE_CANDIDATES, decide
from src.agent_workflow.ui import build_workflow_ui, launch_workflow_ui, write_latest_workflow_debug_log


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings("base", "auth", "client", "secret", "default", "gpt-5.6-luna", "", "", "cohere-reranker", False)

    def test_agent_catalog_has_no_tool_or_isolation_contract(self):
        self.assertIn("Orchestrator", agent_prompt("work-planning"))
        self.assertEqual(routing_candidate("work")["label"], "Work")
        self.assertEqual(
            [agent.id for agent in FOOD_AGENT_DEFINITIONS],
            ["work-planning", "food-rnd", "procurement", "quality-assurance", "marketing", "finance", "synthesis"],
        )
        self.assertEqual(EXECUTABLE_AGENT_IDS[-1], "synthesis")
        self.assertTrue(all(set(agent) == {"agent_id", "agent_label", "description", "system_prompt"} for agent in list_food_agents()))

    def test_workflow_has_no_tools_or_context_isolation_package(self):
        root = ROOT / "4_agent_patterns" / "src" / "agent_workflow"
        self.assertFalse((root / "tools").exists())
        self.assertFalse((root / "context.py").exists())

    def test_reranker_keeps_low_confidence_signal(self):
        ranked = [RankedCandidate(FAST_ROUTE_CANDIDATES[0], 0.5), RankedCandidate(FAST_ROUTE_CANDIDATES[1], 0.5)]
        with patch("src.agent_workflow.runtime.routing.cohere_rank", return_value=(ranked, "btp_cohere_rerank")):
            decision = decide("???", FAST_ROUTE_CANDIDATES, self.settings, min_margin=0.25)
        self.assertTrue(decision.fallback)

    def test_inspect_route_does_not_start_an_agent(self):
        decision = RouteDecision("work", {"chat": 0.2, "work": 0.8}, 0.6, "rerank")
        with patch("src.agent_workflow.lab_core.decide", return_value=decision), patch("src.agent_workflow.lab_core.run_food_agent") as run_agent:
            result = inspect_route("재고 분석을 해줘", self.settings)
        self.assertEqual(result["selected"], "work")
        self.assertFalse(run_agent.called)

    def test_chat_route_returns_chat_response(self):
        decision = RouteDecision("chat", {"chat": 0.9, "work": 0.1}, 0.8, "rerank")
        with patch("src.agent_workflow.lab_core.decide", return_value=decision), patch("src.agent_workflow.lab_core.chat_text", return_value="안녕하세요!"):
            result = run_workflow("안녕하세요", self.settings)
        self.assertEqual(result["route"], "chat")
        self.assertEqual(result["result"], "안녕하세요!")

    def test_workflow_runs_the_llm_plan_without_appending_synthesis(self):
        plan = {"brief": "가격을 검토합니다.", "stages": [{"agent_ids": ["marketing"], "objective": "판매안을 작성합니다."}], "final_agent_id": "marketing"}
        decision = RouteDecision("work", {"chat": 0.1, "work": 0.9}, 0.8, "rerank")

        def fake_agent(agent_id, _request, _settings, on_delta=None):
            if on_delta:
                on_delta("초안")
            return {"agent_id": agent_id, "agent_label": agent_id, "answer": "출시안"}

        with patch("src.agent_workflow.lab_core.decide", return_value=decision), patch("src.agent_workflow.lab_core.plan_work_agents", return_value=plan), patch("src.agent_workflow.lab_core.run_food_agent", side_effect=fake_agent) as run_agent:
            result = run_workflow("출시안을 작성해줘", self.settings)
        self.assertEqual(result["final_agent_id"], "marketing")
        self.assertEqual(result["result"], "출시안")
        self.assertEqual([call.args[0] for call in run_agent.call_args_list], ["marketing"])

    def test_steps_group_each_agent_execution(self):
        streamed_events = iter([
            {"type": "route", "trace_event": {"payload": {"selected": "work"}}},
            {"type": "orchestration_plan", "plan": {"stages": []}, "trace_event": {"event": "orchestration_plan"}},
            {"type": "agent_started", "trace_event": {"payload": {"agent_id": "marketing"}}},
            {"type": "agent_delta", "agent_id": "marketing", "delta": "초안"},
            {"type": "agent_completed", "agent_result": {"agent_id": "marketing", "agent_label": "Marketing Agent", "answer": "출시안"}, "trace_event": {"event": "agent_completed"}},
            {"type": "complete", "result": {"route": "work", "result": "출시안"}},
        ])
        with patch("src.agent_workflow.lab_core.run_workflow_stream", return_value=streamed_events) as stream:
            steps = list(run_workflow_steps("출시안을 작성해줘", self.settings))
        stream.assert_called_once_with("출시안을 작성해줘", self.settings, 0.0, None)
        self.assertEqual([step["step"] for step in steps], ["route", "plan", "agent", "complete"])
        self.assertEqual(steps[2]["deltas"], ["초안"])

    def test_orchestrator_rejects_unknown_agent(self):
        invalid_plan = '{"brief":"검토","stages":[{"agent_ids":["unknown"],"objective":"x"}],"final_agent_id":"unknown"}'
        with patch("src.agent_workflow.food_agents.chat_text", return_value=invalid_plan):
            with self.assertRaisesRegex(RuntimeError, r"허용되지 않은"):
                plan_work_agents("도시락을 검토해줘", self.settings)

    def test_ui_and_debug_snapshot(self):
        app = build_workflow_ui(self.settings)
        self.assertTrue(app.blocks)
        app.close()
        with patch("src.agent_workflow.ui.build_workflow_ui", return_value=app) as build, patch.object(type(app), "launch"):
            launch_workflow_ui()
        build.assert_called_once_with()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest_workflow_conversation.json"
            write_latest_workflow_debug_log({"status": "completed", "user_message": "B"}, path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["user_message"], "B")


if __name__ == "__main__":
    unittest.main()
