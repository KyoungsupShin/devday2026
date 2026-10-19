import sys
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "4_agent_patterns"))

from lab_common.config import Settings
from lab_common.models import RankedCandidate, RouteDecision
from src.agent_workflow.food_agents import FOOD_AGENT_DEFINITIONS, evaluate_workflow_execution, list_food_agents, plan_work_agents, run_food_agent
from src.agent_workflow.food_tools import execute_food_tool, latest_marketing_html_draft, marketing_image_asset
from src.agent_workflow.routing import FAST_ROUTE_CANDIDATES, decide
from src.agent_workflow.lab_core import build_contextual_request, run_workflow, run_workflow_stream
from src.agent_workflow.ui import write_latest_workflow_debug_log


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
        self.assertIn("API / read-only", tool_types)
        self.assertIn("Agent as a Tool", tool_types)

    def test_marketing_agent_as_tool_generates_an_html_draft(self):
        with patch("src.agent_workflow.food_tools.chat_text", return_value="<section><h1>프로틴 런치</h1></section>") as html_agent:
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

    def test_marketing_image_agent_asset_is_embedded_in_html_draft(self):
        session: dict[str, str] = {}
        with patch("src.agent_workflow.food_tools.generate_image_data_url", return_value="data:image/png;base64,aW1hZ2U=") as image_agent:
            image = execute_food_tool(
                "generate_marketing_image",
                {"product_name": "프로틴 런치", "visual_brief": "닭가슴살 도시락 제품 사진"},
                settings=self.settings,
                tool_session=session,
            )
        self.assertEqual(image["agent_label"], "Marketing Image Agent")
        self.assertEqual(marketing_image_asset(image["asset_id"]), "data:image/png;base64,aW1hZ2U=")
        with patch("src.agent_workflow.food_tools.chat_text", return_value="<section><h1>프로틴 런치</h1></section>"):
            html_result = execute_food_tool(
                "generate_marketing_html",
                {"product_name": "프로틴 런치", "positioning": "고단백", "key_messages": ["단백질 30g 이상"]},
                settings=self.settings,
                tool_session=session,
            )
        self.assertIn('src="data:image/png;base64,aW1hZ2U="', html_result["html"])
        self.assertTrue(image_agent.called)

    def test_marketing_html_image_bytes_are_excluded_from_follow_up_llm_context(self):
        tool_call = SimpleNamespace(
            id="call_html",
            function=SimpleNamespace(
                name="generate_marketing_html",
                arguments='{"product_name":"프로틴 런치","positioning":"고단백","key_messages":["단백질 30g"]}',
            ),
        )
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tool_call]))])
        image_payload = "data:image/png;base64," + ("a" * 100_000)
        raw_result = {
            "agent_label": "Marketing HTML Agent",
            "html": f'<section><img src="{image_payload}"></section>',
            "execution_boundary": "draft HTML only",
        }
        final_response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="시안이 생성되었습니다.", tool_calls=[]))])
        with patch("src.agent_workflow.food_agents.chat_tool_completion", side_effect=[response, final_response]) as completion, patch("src.agent_workflow.food_agents.execute_food_tool", return_value=raw_result):
            result = run_food_agent("marketing", "HTML 시안을 만들어줘", self.settings)

        tool_message = completion.call_args_list[1].args[1][-1]["content"]
        self.assertNotIn(image_payload, tool_message)
        self.assertLess(len(tool_message), 1_000)
        self.assertTrue(result["tool_calls"][0]["result"]["html_draft_created"])
        self.assertNotIn("html", result["tool_calls"][0]["result"])

    def test_api_tool_returns_read_only_product_data(self):
        fake_response = Mock()
        fake_response.json.return_value = {"products": [{"product_name": "Protein Chicken", "nutrition_grades": "a", "nutriments": {"proteins_100g": 20}}]}
        with patch("src.agent_workflow.food_tools.requests.get", return_value=fake_response) as get:
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
        with patch("src.agent_workflow.routing.cohere_rank", return_value=(ranked, "btp_cohere_rerank")):
            decision = decide("???", FAST_ROUTE_CANDIDATES, self.settings, min_margin=0.25)
        self.assertTrue(decision.fallback)

    def test_low_confidence_chat_does_not_start_agents(self):
        decision = RouteDecision("chat", {"chat": 0.5, "work": 0.4}, 0.1, "btp_cohere_rerank", fallback=True)
        with patch("src.agent_workflow.lab_core.decide", return_value=decision), patch("src.agent_workflow.lab_core.run_food_agent") as run_agent:
            events = list(run_workflow_stream("안녕", self.settings, min_margin=1.01))
        self.assertFalse(run_agent.called)
        self.assertEqual(events[-1]["result"]["route"], "chat")
        self.assertTrue(events[0]["trace_event"]["payload"]["low_confidence"])

    def test_follow_up_uses_plain_recent_conversation_for_routing(self):
        decision = RouteDecision("chat", {"chat": 0.8, "work": 0.2}, 0.6, "btp_cohere_rerank")
        history = [
            {"role": "user", "content": "프로틴 런치 마케팅 HTML을 만들어줘."},
            {"role": "assistant", "content": "초안 HTML을 만들었습니다."},
        ]
        with patch("src.agent_workflow.lab_core.decide", return_value=decision) as decide_route:
            list(run_workflow_stream("이미지를 더 밝게 수정해줘.", self.settings, conversation_history=history))
        routed_request = decide_route.call_args.args[0]
        self.assertIn("프로틴 런치 마케팅 HTML", routed_request)
        self.assertIn("[현재 사용자 요청]\n이미지를 더 밝게 수정해줘.", routed_request)

    def test_follow_up_includes_previous_html_structure_without_inline_image_bytes(self):
        context = build_contextual_request(
            "가격을 5,000원으로 수정해줘.",
            marketing_html_draft='<section><img src="data:image/png;base64,aW1hZ2U="><h1>프로틴 런치</h1></section>',
        )
        self.assertIn("[현재 Marketing HTML 초안", context)
        self.assertIn("<h1>프로틴 런치</h1>", context)
        self.assertIn("[이전 생성 이미지 asset]", context)
        self.assertNotIn("aW1hZ2U=", context)

    def test_latest_conversation_debug_log_is_json_and_replaces_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest_workflow_conversation.json"
            write_latest_workflow_debug_log({"status": "running", "user_message": "A"}, path)
            write_latest_workflow_debug_log({"status": "completed", "user_message": "B"}, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["user_message"], "B")
        self.assertIn("updated_at", payload)

    def test_orchestrator_plan_selects_only_needed_agents(self):
        plan = {
            "brief": "HTML 수정은 마케팅 관점만 검토합니다.",
            "stages": [{"agent_ids": ["marketing"], "objective": "HTML 시안을 수정합니다."}],
            "final_agent_id": "marketing",
        }

        def fake_agent(agent_id, request, settings, on_delta=None):
            if on_delta:
                on_delta(f"{agent_id} partial answer")
            return {"agent_id": agent_id, "agent_label": agent_id, "answer": f"{agent_id} answer", "tool_calls": []}

        decision = RouteDecision("work", {"chat": 0.1, "work": 0.9}, 0.8, "btp_cohere_rerank")
        with patch("src.agent_workflow.lab_core.decide", return_value=decision), patch("src.agent_workflow.lab_core.plan_work_agents", return_value=plan), patch("src.agent_workflow.lab_core.run_food_agent", side_effect=fake_agent) as agents, patch("src.agent_workflow.lab_core.evaluate_workflow_execution", return_value={"verdict": "pass", "reason": "충분합니다.", "revision_stages": []}):
            events = list(run_workflow_stream("기존 HTML을 수정해줘", self.settings))
        completed = [event["agent_result"]["agent_id"] for event in events if event["type"] == "agent_completed"]
        self.assertEqual(completed, ["work-planning", "marketing"])
        self.assertEqual([call.args[0] for call in agents.call_args_list], ["marketing"])

    def test_orchestrated_workflow_streams_llm_selected_stages(self):
        calls: list[tuple[str, str]] = []
        plan = {
            "brief": "출시 가능성을 종합 검토합니다.",
            "stages": [
                {"agent_ids": ["food-rnd", "marketing"], "objective": "제품과 시장안을 만듭니다."},
                {"agent_ids": ["procurement", "quality-assurance"], "objective": "원가와 안전성을 검토합니다."},
                {"agent_ids": ["finance"], "objective": "출시 권고를 통합합니다."},
            ],
            "final_agent_id": "finance",
        }

        def fake_agent(agent_id, request, settings, on_delta=None):
            calls.append((agent_id, request))
            if on_delta:
                on_delta(f"{agent_id} partial answer")
            return {"agent_id": agent_id, "agent_label": agent_id, "answer": f"{agent_id} answer", "tool_calls": []}

        decision = RouteDecision("work", {"chat": 0.1, "work": 0.9}, 0.8, "btp_cohere_rerank")
        with patch("src.agent_workflow.lab_core.decide", return_value=decision), patch("src.agent_workflow.lab_core.plan_work_agents", return_value=plan), patch("src.agent_workflow.lab_core.run_food_agent", side_effect=fake_agent), patch("src.agent_workflow.lab_core.evaluate_workflow_execution", return_value={"verdict": "pass", "reason": "충분합니다.", "revision_stages": []}):
            events = list(run_workflow_stream("고단백 도시락을 개발해줘", self.settings))
            result = run_workflow("고단백 도시락을 개발해줘", self.settings)

        completed = [event["agent_result"]["agent_id"] for event in events if event["type"] == "agent_completed"]
        streamed = [event["agent_id"] for event in events if event["type"] == "agent_delta"]
        self.assertCountEqual(completed, [agent.id for agent in FOOD_AGENT_DEFINITIONS])
        self.assertCountEqual(streamed, [agent.id for agent in FOOD_AGENT_DEFINITIONS if agent.id != "work-planning"])
        self.assertIn("[Orchestrator 공통 브리프]\n출시 가능성을 종합 검토합니다.", next(request for agent_id, request in calls if agent_id == "food-rnd"))
        self.assertIn("[food-rnd 결과]\nfood-rnd answer", next(request for agent_id, request in calls if agent_id == "procurement"))
        self.assertIn("[procurement 결과]\nprocurement answer", next(request for agent_id, request in calls if agent_id == "finance"))
        self.assertEqual(result["route"], "work")
        self.assertEqual(result["result"], "finance answer")
        self.assertTrue(result["evaluation"]["passed"])

    def test_evaluation_middleware_returns_llm_selected_revision_stage(self):
        plan = {
            "brief": "가격을 HTML 제목에 반영합니다.",
            "stages": [{"agent_ids": ["marketing"], "objective": "HTML을 수정합니다."}],
            "final_agent_id": "marketing",
        }
        revision = {
            "verdict": "revise",
            "reason": "HTML Agent Tool 호출 증거가 없습니다.",
            "revision_stages": [{"agent_ids": ["marketing"], "objective": "HTML Agent Tool로 가격을 반영해 다시 생성합니다."}],
        }
        with patch("src.agent_workflow.food_agents.chat_text", return_value=json.dumps(revision, ensure_ascii=False)):
            result = evaluate_workflow_execution("가격을 넣어줘", plan, {"marketing": {"agent_label": "Marketing Agent", "answer": "코드블록", "tool_calls": []}}, self.settings)
        self.assertEqual(result["verdict"], "revise")
        self.assertEqual(result["revision_stages"][-1]["agent_ids"], ["marketing"])

    def test_evaluation_rework_is_bounded_to_three_reviews(self):
        plan = {
            "brief": "HTML을 수정합니다.",
            "stages": [{"agent_ids": ["marketing"], "objective": "초안을 만듭니다."}],
            "final_agent_id": "marketing",
        }
        revise = {
            "verdict": "revise",
            "reason": "HTML Tool 호출이 필요합니다.",
            "revision_stages": [{"agent_ids": ["marketing"], "objective": "Tool Calling으로 HTML을 보완합니다."}],
        }

        def fake_agent(agent_id, request, settings, on_delta=None):
            return {"agent_id": agent_id, "agent_label": "Marketing Agent", "answer": "초안", "tool_calls": []}

        decision = RouteDecision("work", {"chat": 0.1, "work": 0.9}, 0.8, "btp_cohere_rerank")
        with patch("src.agent_workflow.lab_core.decide", return_value=decision), patch("src.agent_workflow.lab_core.plan_work_agents", return_value=plan), patch("src.agent_workflow.lab_core.run_food_agent", side_effect=fake_agent) as agents, patch("src.agent_workflow.lab_core.evaluate_workflow_execution", return_value=revise) as evaluate:
            result = run_workflow("HTML 가격 수정", self.settings)
        self.assertEqual(evaluate.call_count, 3)
        self.assertEqual(agents.call_count, 3)
        self.assertTrue(result["evaluation"]["limit_reached"])
        self.assertFalse(result["evaluation"]["passed"])

    def test_orchestrator_rejects_an_invalid_execution_plan_without_fallback(self):
        invalid_plan = '{"brief":"검토","stages":[{"agent_ids":["unknown"],"objective":"x"}],"final_agent_id":"unknown"}'
        with patch("src.agent_workflow.food_agents.chat_text", return_value=invalid_plan):
            with self.assertRaisesRegex(RuntimeError, "허용되지 않은"):
                plan_work_agents("도시락을 검토해줘", self.settings)

    def test_orchestrator_rejects_a_misplaced_final_agent_without_rewriting_the_plan(self):
        misplaced_plan = {
            "brief": "출시안을 검토합니다.",
            "stages": [
                {"agent_ids": ["finance"], "objective": "손익을 계산합니다."},
                {"agent_ids": ["marketing"], "objective": "판매안을 작성합니다."},
            ],
            "final_agent_id": "finance",
        }
        with (
            patch(
                "src.agent_workflow.food_agents.chat_text",
                return_value=json.dumps(misplaced_plan, ensure_ascii=False),
            ),
            self.assertRaisesRegex(RuntimeError, "마지막 실행 단계"),
        ):
            plan_work_agents("도시락 출시안을 검토해줘", self.settings)


if __name__ == "__main__":
    unittest.main()
