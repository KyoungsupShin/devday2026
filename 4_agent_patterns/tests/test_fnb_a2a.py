import csv
import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "1_gen_ai_hub" / "src"))
sys.path.insert(0, str(ROOT / "4_agent_patterns"))

from lab_common.config import Settings
from src.agent_to_agent import executor, grounding, human_approval
from src.agent_to_agent import orchestration as orchestration_module
from src.agent_to_agent.catalog import (
    AGENT_CATALOG,
    AGENT_URLS,
    DEFAULT_REQUEST,
    MESSAGE_MODES,
    SCENARIO_REQUEST_DEPARTMENTS,
    SCENARIO_REQUESTS,
    SUBAGENT_BY_LABEL,
    SUBAGENT_CATALOG,
)
from src.agent_to_agent.orchestration import (
    _orchestrator_turn,
    _parse_decision,
    _parse_observation,
    list_agents,
    plan_handoff,
    run_handoff_steps,
)
from src.agent_to_agent_advanced import harness
from src.agent_to_agent_advanced import grounding as advanced_grounding
from src.agent_to_agent_advanced import ui as advanced_ui
from src.agent_to_agent_advanced.tools import business_context as advanced_business_context
from src.agent_to_agent_advanced.orchestration import (
    _orchestrator_turn as _advanced_orchestrator_turn,
)
from src.agent_to_agent_advanced.ui import _harness_chat_html, _harness_dashboard_html
from src.agent_to_agent.prompts import get_optional_prompt, get_prompt, render_prompt
from src.agent_to_agent.server import build_agent_card, create_a2a_app
from src.agent_to_agent.tools import snapshot_reader
from src.agent_to_agent.tools.business_context import search_business_context
from src.agent_to_agent.tools.erp_change_records import lookup_erp_readiness_evidence
from src.agent_to_agent.tools.facility_records import lookup_facility_context
from src.agent_to_agent.tools.financial_records import (
    lookup_business_outlook_evidence,
    lookup_cost_driver_evidence,
    lookup_financial_control_evidence,
)
from src.agent_to_agent.tools.process_engineering_records import lookup_process_evidence
from src.agent_to_agent.tools.production_execution_records import (
    lookup_production_execution_evidence,
)
from src.agent_to_agent.tools.profitability_forecast import (
    calculate_profitability_scenarios,
)
from src.agent_to_agent.tools.purchasing_records import (
    lookup_procurement_evidence,
    lookup_supply_evidence,
)
from src.agent_to_agent.tools.quality_records import lookup_quality_evidence
from src.agent_to_agent.tools.research_development_records import lookup_rnd_evidence
from src.agent_to_agent.tools.safety_environment_records import lookup_ehs_evidence
from src.agent_to_agent.tools.site_services_records import (
    lookup_general_affairs_evidence,
)
from src.agent_to_agent.tools.tool_registry import (
    TOOL_EXECUTORS,
    TOOL_SCHEMAS,
    execute_tool,
    schemas_for_tool_ids,
)
from src.agent_to_agent.tools.workforce_records import lookup_hr_workforce_evidence
from src.agent_to_agent.transport import _status_signature, resolve_agent_urls
from src.agent_to_agent.ui import (
    _agent_card_modal_html,
    _artifact_chat_message,
    _chat_message_html,
    _default_outlook_recipient,
    _delivery_failed_for_chat_review,
    _field_response_chat_message,
    _human_approval_chat_message,
    _human_approval_fallback_chat_message,
    _human_approval_sent_chat_message,
    _human_reviewed_in_chat,
    _scenario_card_html,
    _subagent_chat_message,
    _task_plan_chat_message,
)


def _schemas_for_subagent(label: str) -> list[dict[str, object]]:
    return schemas_for_tool_ids(SUBAGENT_BY_LABEL[label]["tool_ids"])


def _completion(content: str, tool_calls: list[dict[str, object]] | None = None):
    return {
        "choices": [{"message": {"content": content, "tool_calls": tool_calls or []}}]
    }


class FnbA2ATests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            "base",
            "auth",
            "client",
            "secret",
            "default",
            "gpt-5.6-luna",
            "",
            "",
            "cohere-reranker",
            False,
        )

    def test_catalog_exposes_twelve_independent_team_cards(self):
        self.assertEqual(
            set(AGENT_URLS),
            {
                "fb-facilities-team",
                "fb-procurement-team",
                "manufacturing-planning-team",
                "finance-business-planning-team",
                "it-team",
                "ehs-team",
                "hr-team",
                "general-affairs-team",
                "process-engineering-team",
                "rnd-team",
                "production-team",
                "quality-team",
            },
        )
        self.assertEqual({item["agent_id"] for item in AGENT_CATALOG}, set(AGENT_URLS))
        self.assertEqual({item["agent_id"] for item in list_agents()}, set(AGENT_URLS))
        self.assertEqual(len(SUBAGENT_CATALOG), 34)
        finance = next(
            item
            for item in AGENT_CATALOG
            if item["agent_id"] == "finance-business-planning-team"
        )
        self.assertEqual(
            finance["sub_agents"],
            [
                "수익성·원가 Agent",
                "사업성 전망 Agent",
                "예산·관리회계 Agent",
                "예산이관 검토 Agent",
            ],
        )
        planning = next(
            item
            for item in AGENT_CATALOG
            if item["agent_id"] == "manufacturing-planning-team"
        )
        self.assertEqual(
            planning["sub_agents"],
            ["생산기획 Agent", "원부자재 투입 Agent", "생산 투입 준비 Agent"],
        )
        new_teams = {
            "ehs-team": ["안전보건 Agent", "환경관리 Agent", "화학물질·작업허가 Agent"],
            "hr-team": ["인력운영 Agent", "교육·자격 Agent", "노무·근태 Agent"],
            "general-affairs-team": [
                "사업장 운영지원 Agent",
                "자산·비품 Agent",
                "출입·보안지원 Agent",
            ],
            "process-engineering-team": [
                "공정기술 Agent",
                "공정개선·수율 Agent",
                "공정변경·검증 Agent",
            ],
            "rnd-team": [
                "제품개발·배합 Agent",
                "원료·규격개발 Agent",
                "스케일업·기술이전 Agent",
            ],
            "production-team": [
                "생산운영 Agent",
                "라인운영 Agent",
                "생산실적·추적 Agent",
            ],
            "quality-team": ["품질보증 Agent", "품질관리 Agent", "출하·품질승인 Agent"],
        }
        self.assertEqual(
            {
                item["agent_id"]: item["sub_agents"]
                for item in AGENT_CATALOG
                if item["agent_id"] in new_teams
            },
            new_teams,
        )

    def test_prompt_resources_separate_common_roles_and_tool_guidance(self):
        self.assertIn("cumulative decision record", get_prompt("team.template"))
        self.assertIn("Contribute one perspective", get_prompt("subagent.template"))
        self.assertIn(
            "financial-control and enterprise-planning",
            get_prompt("teams.finance_business_planning.perspective"),
        )
        self.assertIn(
            "profitability-calculation observation",
            get_prompt("tools.calculate_profitability_scenarios.guidance"),
        )
        self.assertIsNone(get_optional_prompt("roles.legacy_finance.perspective"))
        self.assertTrue(
            all(
                "role_prompt_key" in agent and "system_prompt" not in agent
                for agent in AGENT_CATALOG
            )
        )
        self.assertTrue(
            all(
                "role_prompt_key" in agent
                and "responsibility" in agent
                and "system_prompt" not in agent
                for agent in SUBAGENT_CATALOG
            )
        )
        for agent in (*AGENT_CATALOG, *SUBAGENT_CATALOG):
            self.assertTrue(get_prompt(agent["role_prompt_key"]))

    def test_executor_uses_compact_subagent_responsibilities_and_tool_guidance(self):
        available = executor._available_subagents("finance-business-planning-team")
        profitability = next(
            item for item in available if item["agent"] == "수익성·원가 Agent"
        )
        self.assertEqual(
            profitability["responsibility"],
            "수익성, 원가, 환율·원자재 시나리오 근거를 검토합니다.",
        )
        self.assertNotIn("Contribute one perspective", profitability["responsibility"])
        finance = next(
            item
            for item in AGENT_CATALOG
            if item["agent_id"] == "finance-business-planning-team"
        )
        prompt = executor._role_prompt(finance, "수익성·원가 Agent")
        self.assertIn("Contribute one perspective", prompt)
        self.assertIn("profitability conclusion", prompt)
        self.assertIn(
            "profitability-calculation observation",
            executor._tool_guidance(_schemas_for_subagent("수익성·원가 Agent")),
        )
        self.assertEqual(
            executor._tool_guidance(_schemas_for_subagent("구매조달 Agent")),
            "",
        )

    def test_every_registered_team_builds_an_a2a_card(self):
        for agent_id, url in AGENT_URLS.items():
            with TestClient(create_a2a_app(agent_id, url, self.settings)) as client:
                response = client.get("/.well-known/agent-card.json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["version"], "1.0")
            self.assertTrue(response.json()["capabilities"]["streaming"])
        self.assertEqual(
            build_agent_card(
                "finance-business-planning-team",
                AGENT_URLS["finance-business-planning-team"],
            ).name,
            "재무·사업기획팀 Agent",
        )
        self.assertTrue(
            all(agent["input_modes"] == list(MESSAGE_MODES) for agent in list_agents())
        )

    def test_scenarios_remain_natural_language_requests(self):
        scenarios = dict(SCENARIO_REQUESTS)
        self.assertEqual(DEFAULT_REQUEST, "CIP 펌프 메커니컬 실 키트를 구매해 주세요.")
        self.assertEqual(
            scenarios["기존 원부자재 추가 발주"], "딸기 농축액을 추가 발주해 주세요."
        )
        self.assertEqual(scenarios["기존 설비 소모품 보충 구매"], DEFAULT_REQUEST)
        self.assertIn("레몬 탄산음료", scenarios["환율·원자재 가격 변동 사업성 평가"])
        self.assertIn("알룰로스 감미료", scenarios["신규 원부자재 등록·생산 투입"])
        self.assertIn("음료 1라인", scenarios["생산라인 Cost Center 변경"])
        self.assertTrue(all("Agent" not in request for request in scenarios.values()))
        self.assertTrue(all("FNB-" not in request for request in scenarios.values()))
        self.assertEqual(
            SCENARIO_REQUEST_DEPARTMENTS["환율·원자재 가격 변동 사업성 평가"],
            "경영기획 · 사업관리",
        )

    def test_sop_defers_human_approval_until_required_reviews_finish(self):
        paths = (
            ROOT / "data" / "context" / "interdepartmental_collaboration_sop.md",
            ROOT / "4_agent_patterns" / "docs" / "interdepartmental_collaboration_sop.md",
        )
        for path in paths:
            sop = path.read_text(encoding="utf-8")
            facilities = sop.index("먼저 설비팀이")
            procurement = sop.index("다음으로 구매팀이")
            planning = sop.index("이어서 제조기획팀이")
            human = sop.index("4. 결과 정리 및 Human-in-the-loop 확인")
            self.assertIn("설비팀 → 구매팀 → 제조기획팀 순서", sop)
            self.assertIn("이 단계에서 사람의 승인·결정을 요청하지 않는다.", sop)
            self.assertIn("세 Team 검토가 끝난 뒤의 최종 단계", sop)
            self.assertLess(facilities, procurement)
            self.assertLess(procurement, planning)
            self.assertLess(planning, human)

    def test_notebook_sop_revision_keeps_human_approval_at_the_end(self):
        notebook_path = ROOT / "4_agent_patterns" / "notebooks" / "03_agent_to_agent.ipynb"
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        source = next(
            "".join(cell["source"])
            for cell in notebook["cells"]
            if "REVISED_SOP_PROCESS" in "".join(cell.get("source", []))
        )
        self.assertIn("구매팀 → 설비팀 순서", source)
        self.assertIn("구매팀·설비팀 확인이 끝난 뒤의 최종 단계", source)
        self.assertNotIn("RESTORE_SOP_PROCESS", source)
        self.assertIn(
            "prepare_default_sop_replacement(REVISED_SOP_PROCESS)", source
        )
        self.assertIn("원복 원본 파일: {sop_change.source_path}", source)
        self.assertNotIn("설비팀 관리자가", source)

        fresh_plan_source = next(
            "".join(cell["source"])
            for cell in notebook["cells"]
            if cell.get("id") == "a2a-sop-grounding-compare"
        )
        self.assertIn("plan_handoff(DEFAULT_REQUEST)", fresh_plan_source)
        self.assertNotIn("next_step", fresh_plan_source)
        self.assertNotIn("a2a_steps", fresh_plan_source)

    def test_context_rows_have_local_snapshot_scope_and_registered_relations(self):
        data_root = snapshot_reader.DATA_DIRECTORY
        with (data_root / "business_context.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            contexts = list(csv.DictReader(handle))
        self.assertEqual(len(contexts), 12)
        self.assertTrue(all(row["DATA_SCOPE"] == "LOCAL_SNAPSHOT" for row in contexts))
        self.assertTrue(all(row["CONTEXT_ID"] for row in contexts))
        self.assertTrue(all("COST_CENTER" in row for row in contexts))
        self.assertTrue(
            {
                "CTX-EHS-CIP-CHEMICAL",
                "CTX-HR-BEV-SHIFT",
                "CTX-GA-SITE-SUPPORT",
                "CTX-PROC-LEMON-CHANGE",
                "CTX-RND-ALLULOSE-FORMULATION",
                "CTX-PROD-BEV-LINE",
                "CTX-QUALITY-ALLULOSE",
            }.issubset({row["CONTEXT_ID"] for row in contexts})
        )
        for filename in (
            "supplier_master.csv",
            "material_planning_parameter.csv",
            "sales_forecast.csv",
            "erp_data_mapping.csv",
        ):
            with (data_root / filename).open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(rows, filename)
            self.assertTrue(all(row["DATA_SCOPE"] == "LOCAL_SNAPSHOT" for row in rows))
            self.assertTrue(
                all(
                    row["CONTEXT_ID"] in {item["CONTEXT_ID"] for item in contexts}
                    for row in rows
                )
            )

    def test_search_only_identifies_context_and_never_a_team(self):
        result = search_business_context("CIP 펌프 메커니컬 실 키트를 구매해 주세요.")
        self.assertEqual(result["state"], "found")
        self.assertEqual(result["records"][0]["CONTEXT_ID"], "CTX-EQP-CIP-SEAL")
        self.assertIn(
            "Agent 선택이나 업무 단계 판단은 수행하지 않습니다",
            result["search_boundary"],
        )
        self.assertNotIn("target_agent_id", result)

    def test_advanced_context_search_uses_llm_selected_registered_ids(self):
        selection = {
            "context_ids": ["CTX-EQP-CIP-SEAL"],
            "reason": "요청 대상이 CIP 펌프 실 키트 후보와 직접 일치합니다.",
        }
        with patch.object(advanced_business_context, "chat_text", return_value=json.dumps(selection)) as model:
            result = advanced_business_context.search_business_context("CIP 펌프 메커니컬 실 키트를 구매해 주세요.")
        self.assertEqual(model.call_count, 1)
        self.assertEqual(result["state"], "found")
        self.assertEqual([row["CONTEXT_ID"] for row in result["records"]], ["CTX-EQP-CIP-SEAL"])
        self.assertIn("LLM이 등록 Context 후보에서 선택", result["search_boundary"])

    def test_focused_procurement_and_supply_tools_return_separate_evidence(self):
        procurement = lookup_procurement_evidence("CTX-RM-STRAWBERRY")
        supply = lookup_supply_evidence("CTX-RM-STRAWBERRY")
        self.assertEqual(procurement["state"], "found")
        self.assertEqual(supply["state"], "found")
        self.assertIn("supplier", procurement["records_by_snapshot"])
        self.assertIn("quote", procurement["records_by_snapshot"])
        self.assertNotIn("stock", procurement["records_by_snapshot"])
        self.assertIn("stock", supply["records_by_snapshot"])
        self.assertIn("material_planning", supply["records_by_snapshot"])
        self.assertTrue(
            all(
                item["DATA_SCOPE"] == "LOCAL_SNAPSHOT"
                for item in procurement["records_by_snapshot"]["supplier"]
            )
        )
        self.assertIn(
            {
                "snapshot": "open_purchase_schedule",
                "field": "SCHEDULE_STATUS",
                "value": "NO_OPEN_PURCHASE_ORDER",
            },
            procurement["status_tokens"],
        )

    def test_facility_financial_control_and_erp_tools_are_context_scoped(self):
        facility = lookup_facility_context("CTX-EQP-CIP-SEAL")
        financial = lookup_financial_control_evidence("CTX-EQP-CIP-SEAL")
        cost_driver = lookup_cost_driver_evidence("CTX-PROD-LEMON")
        outlook = lookup_business_outlook_evidence("CTX-PROD-LEMON")
        readiness = lookup_erp_readiness_evidence("CTX-INTAKE-ALLULOSE")
        self.assertEqual(facility["state"], "found")
        self.assertTrue(facility["records_by_snapshot"]["maintenance"])
        self.assertEqual(
            financial["records_by_snapshot"]["opex_budget"][0]["SHORTFALL_AMOUNT"],
            "850000",
        )
        self.assertEqual(
            financial["records_by_snapshot"]["approval"][0]["REQUIRED_APPROVERS"],
            "시설관리책임자;구매책임자",
        )
        self.assertTrue(cost_driver["records_by_snapshot"]["product_cost_assumption"])
        self.assertNotIn("sales_forecast", cost_driver["records_by_snapshot"])
        self.assertTrue(outlook["records_by_snapshot"]["sales_forecast"])
        self.assertNotIn("product_cost_assumption", outlook["records_by_snapshot"])
        self.assertTrue(readiness["records_by_snapshot"]["erp_mapping"])
        self.assertEqual(
            readiness["records_by_snapshot"]["erp_mapping"][0]["PRECONDITION_STATUS"],
            "PENDING_MDM_AND_QUALITY",
        )
        self.assertNotIn("mdm", readiness["records_by_snapshot"])
        self.assertIn(
            {
                "snapshot": "erp_mapping",
                "field": "PRECONDITION_STATUS",
                "value": "PENDING_MDM_AND_QUALITY",
            },
            readiness["status_tokens"],
        )

    def test_new_operational_team_tools_expose_only_context_scoped_observations(self):
        cases = (
            (
                "안전보건 Agent",
                "lookup_ehs_evidence",
                lookup_ehs_evidence,
                "CTX-EHS-CIP-CHEMICAL",
                "ehs",
            ),
            (
                "인력운영 Agent",
                "lookup_hr_workforce_evidence",
                lookup_hr_workforce_evidence,
                "CTX-HR-BEV-SHIFT",
                "hr",
            ),
            (
                "사업장 운영지원 Agent",
                "lookup_general_affairs_evidence",
                lookup_general_affairs_evidence,
                "CTX-GA-SITE-SUPPORT",
                "general_affairs",
            ),
            (
                "공정기술 Agent",
                "lookup_process_evidence",
                lookup_process_evidence,
                "CTX-PROC-LEMON-CHANGE",
                "process",
            ),
            (
                "제품개발·배합 Agent",
                "lookup_rnd_evidence",
                lookup_rnd_evidence,
                "CTX-RND-ALLULOSE-FORMULATION",
                "rnd",
            ),
            (
                "생산운영 Agent",
                "lookup_production_execution_evidence",
                lookup_production_execution_evidence,
                "CTX-PROD-BEV-LINE",
                "production",
            ),
            (
                "품질보증 Agent",
                "lookup_quality_evidence",
                lookup_quality_evidence,
                "CTX-QUALITY-ALLULOSE",
                "quality",
            ),
        )
        for label, tool_name, lookup, context_id, snapshot in cases:
            tools = {item["function"]["name"] for item in _schemas_for_subagent(label)}
            self.assertEqual(tools, {"search_business_context", tool_name})
            result = lookup(context_id)
            self.assertEqual(result["state"], "found")
            self.assertTrue(result["records_by_snapshot"][snapshot])
            self.assertTrue(
                all(
                    row["DATA_SCOPE"] == "LOCAL_SNAPSHOT"
                    for row in result["records_by_snapshot"][snapshot]
                )
            )
        self.assertEqual(
            lookup_ehs_evidence("CTX-EQP-CIP-SEAL")["state"],
            "not_applicable",
        )

    def test_explicit_context_lineage_prevents_cost_center_cross_contamination(self):
        strawberry = lookup_financial_control_evidence("CTX-RM-STRAWBERRY")
        line = lookup_financial_control_evidence("CTX-LINE-BEV-01")
        self.assertTrue(strawberry["records_by_snapshot"]["material_budget"])
        self.assertEqual(strawberry["records_by_snapshot"]["cost_center_change"], [])
        self.assertEqual(strawberry["records_by_snapshot"]["budget_transfer"], [])
        self.assertTrue(line["records_by_snapshot"]["cost_center_change"])
        self.assertEqual(line["records_by_snapshot"]["material_budget"], [])

    def test_context_tools_reject_missing_or_unknown_context_without_fallback(self):
        invalid = lookup_financial_control_evidence(None)
        missing = lookup_procurement_evidence("CTX-NOT-REGISTERED")
        self.assertEqual(invalid["state"], "invalid_input")
        self.assertEqual(missing["state"], "no_match")
        self.assertEqual(missing["records"], [])

    def test_profitability_calculation_returns_monthly_and_quarterly_values(self):
        result = calculate_profitability_scenarios("CTX-PROD-LEMON")

        self.assertEqual(result["state"], "found")
        self.assertEqual(
            result["inputs_used"],
            {
                "bom_component_count": 1,
                "month_count": 3,
                "scenario_count": 3,
                "data_scope": "LOCAL_SNAPSHOT",
            },
        )
        self.assertEqual(
            [item["scenario"] for item in result["scenario_summaries"]],
            ["호조", "기준", "악화"],
        )
        self.assertEqual(len(result["monthly_forecasts"]), 9)

        baseline_january = next(
            item
            for item in result["monthly_forecasts"]
            if item["scenario"] == "기준" and item["forecast_period"] == "2027-01"
        )
        self.assertEqual(baseline_january["unit_cogs_krw"], 920)
        self.assertEqual(baseline_january["total_cost_krw"], 62600000)
        self.assertEqual(baseline_january["bep_quantity_ea"], 20690)
        self.assertEqual(baseline_january["bep_revenue_krw"], 31035000)

        baseline = next(
            item for item in result["scenario_summaries"] if item["scenario"] == "기준"
        )
        downside = next(
            item for item in result["scenario_summaries"] if item["scenario"] == "악화"
        )
        self.assertEqual(baseline["revenue_krw"], 270000000)
        self.assertEqual(baseline["total_cost_krw"], 206875000)
        self.assertEqual(baseline["operating_profit_krw"], 63125000)
        self.assertEqual(baseline["bep_quantity_ea"], 66062)
        self.assertGreater(
            downside["average_unit_cogs_krw"], baseline["average_unit_cogs_krw"]
        )
        self.assertGreater(downside["bep_quantity_ea"], baseline["bep_quantity_ea"])

    def test_profitability_calculation_rejects_missing_duplicate_and_currency_mismatch_inputs(
        self,
    ):
        original_read_rows = snapshot_reader.read_rows

        def missing_price(lookup):
            state, rows, path = original_read_rows(lookup)
            return (
                (state, rows[:-1], path)
                if lookup == "material_price"
                else (state, rows, path)
            )

        with patch(
            "src.agent_to_agent.tools.snapshot_reader.read_rows",
            side_effect=missing_price,
        ):
            missing = calculate_profitability_scenarios("CTX-PROD-LEMON")
        self.assertEqual(missing["state"], "insufficient_input")
        self.assertIn(
            "missing_input:material_price.악화.2027-03.RM-LEMON-CONC-001",
            missing["errors"],
        )

        def duplicate_price(lookup):
            state, rows, path = original_read_rows(lookup)
            if lookup == "material_price":
                return state, [*rows, dict(rows[0])], path
            return state, rows, path

        with patch(
            "src.agent_to_agent.tools.snapshot_reader.read_rows",
            side_effect=duplicate_price,
        ):
            duplicate = calculate_profitability_scenarios("CTX-PROD-LEMON")
        self.assertEqual(duplicate["state"], "insufficient_input")
        self.assertIn(
            "duplicate_input:material_price.호조.2027-01.RM-LEMON-CONC-001",
            duplicate["errors"],
        )

        def mismatched_currency(lookup):
            state, rows, path = original_read_rows(lookup)
            if lookup == "material_price":
                rows = [dict(row) for row in rows]
                rows[0]["CURRENCY"] = "EUR"
            return state, rows, path

        with patch(
            "src.agent_to_agent.tools.snapshot_reader.read_rows",
            side_effect=mismatched_currency,
        ):
            mismatch = calculate_profitability_scenarios("CTX-PROD-LEMON")
        self.assertEqual(mismatch["state"], "insufficient_input")
        self.assertIn(
            "currency_mismatch:material_price_and_exchange_rate.호조.2027-01.RM-LEMON-CONC-001",
            mismatch["errors"],
        )

    def test_grounding_requests_new_evidence_for_each_identical_query(self):
        documents = [{"id": "sop-1"}]
        with (
            patch(
                "src.agent_to_agent.grounding.list_documents",
                return_value=documents,
            ),
            patch(
                "src.agent_to_agent.grounding._grounded_answer",
                return_value="SOP 근거",
            ) as answer,
        ):
            first = grounding.collect_grounding_context(
                "구매 승인 조건을 확인해 주세요.",
                self.settings,
                repository_id="repository-1",
            )
            second = grounding.collect_grounding_context(
                "구매 승인 조건을 확인해 주세요.",
                self.settings,
                repository_id="repository-1",
            )

        self.assertEqual(first["evidence"], "SOP 근거")
        self.assertEqual(second["evidence"], "SOP 근거")
        self.assertEqual(answer.call_count, 2)

    def test_role_scoped_tools_match_subagent_responsibilities(self):
        self.assertEqual(
            [
                schema["function"]["name"]
                for schema in _schemas_for_subagent("구매조달 Agent")
            ],
            ["search_business_context", "lookup_procurement_evidence"],
        )
        self.assertEqual(
            [
                schema["function"]["name"]
                for schema in _schemas_for_subagent("예산·관리회계 Agent")
            ],
            ["search_business_context", "lookup_financial_control_evidence"],
        )
        self.assertEqual(
            [
                schema["function"]["name"]
                for schema in _schemas_for_subagent("사업성 전망 Agent")
            ],
            [
                "search_business_context",
                "lookup_business_outlook_evidence",
                "calculate_profitability_scenarios",
            ],
        )
        self.assertEqual(
            [
                schema["function"]["name"]
                for schema in _schemas_for_subagent("수익성·원가 Agent")
            ],
            [
                "search_business_context",
                "lookup_cost_driver_evidence",
                "calculate_profitability_scenarios",
            ],
        )
        self.assertEqual(
            [
                schema["function"]["name"]
                for schema in _schemas_for_subagent("ERP·MDM 데이터 Agent")
            ],
            ["search_business_context", "lookup_erp_readiness_evidence"],
        )
        known_labels = {item["label"] for item in SUBAGENT_CATALOG}
        self.assertEqual(set(SUBAGENT_BY_LABEL), known_labels)
        self.assertTrue(all(item["tool_ids"] for item in SUBAGENT_CATALOG))
        registered = set(TOOL_EXECUTORS)
        self.assertEqual(set(TOOL_SCHEMAS), registered)
        self.assertTrue(
            all(set(item["tool_ids"]).issubset(registered) for item in SUBAGENT_CATALOG)
        )
        self.assertNotIn("lookup_material_mdm", TOOL_SCHEMAS)
        self.assertNotIn("lookup_profitability_context", TOOL_SCHEMAS)
        self.assertNotIn("product_cost", snapshot_reader.SNAPSHOT_PATHS)
        self.assertFalse(
            (snapshot_reader.DATA_DIRECTORY / "product_cost_snapshot.csv").exists()
        )
        finance_labels = {"수익성·원가 Agent", "사업성 전망 Agent"}
        for subagent in SUBAGENT_CATALOG:
            if subagent["label"] not in finance_labels:
                self.assertNotIn(
                    "calculate_profitability_scenarios", subagent["tool_ids"]
                )

    def test_dispatcher_only_executes_registered_context_tools(self):
        result = execute_tool(
            "lookup_financial_control_evidence", {"context_id": "CTX-LINE-BEV-01"}
        )
        self.assertEqual(result["state"], "found")
        with self.assertRaisesRegex(ValueError, "허용되지 않은"):
            execute_tool("route_to_finance", {})

    def test_invalid_orchestration_target_has_no_fallback(self):
        cards = {
            agent_id: SimpleNamespace(name=agent_id, description="test")
            for agent_id in AGENT_URLS
        }
        with self.assertRaisesRegex(RuntimeError, "문자열"):
            _parse_decision(
                '{"action":"complete","target_agent_id":null,"reason":"done"}'
            )
        with self.assertRaisesRegex(ValueError, "등록되지 않은"):
            resolve_agent_urls({"none": "http://127.0.0.1:9999"})
        self.assertEqual(set(cards), set(AGENT_URLS))

    def test_transport_status_signature_ignores_repeated_delivery(self):
        original = {
            "status": {
                "state": "TASK_STATE_WORKING",
                "message": {"parts": [{"text": '{"event":"synthesis_completed"}'}]},
            },
            "artifacts": [{"name": "first"}],
        }
        repeated_with_artifact = {
            **original,
            "artifacts": [{"name": "first"}, {"name": "second"}],
        }
        changed_status = {
            "status": {
                "state": "TASK_STATE_COMPLETED",
                "message": {"parts": [{"text": '{"event":"team_completed"}'}]},
            }
        }
        self.assertEqual(
            _status_signature(original), _status_signature(repeated_with_artifact)
        )
        self.assertNotEqual(
            _status_signature(original), _status_signature(changed_status)
        )

    def test_observation_accepts_empty_factual_categories_without_fallback(self):
        observation = _parse_observation(
            """{
                \"completed_work\": [\"현장 요청이 수신되었습니다.\"],
                \"new_evidence\": [],
                \"unresolved_decisions\": [],
                \"available_capabilities\": [\"등록 Team의 역할을 검토할 수 있습니다.\", \"추가 Team의 역할을 검토할 수 있습니다.\", \"다른 관점을 검토할 수 있습니다.\"],
                \"decision_focus\": [\"현재 기록의 완료 여부를 판단합니다.\"]
            }"""
        )
        self.assertEqual(observation["new_evidence"], [])
        self.assertEqual(observation["unresolved_decisions"], [])
        self.assertEqual(len(observation["available_capabilities"]), 3)

    def test_decision_preserves_structured_requester_update(self):
        decision = _parse_decision(
            '{"action":"complete","target_agent_id":"complete","reason":"감사 기록",'
            '"requester_update":{"status":"검토 완료","summary":"검토 결과를 공유합니다.",'
            '"next_action":"담당자가 다음 조치를 확인해 주세요."}}'
        )
        self.assertEqual(decision["reason"], "감사 기록")
        self.assertEqual(decision["requester_update"]["status"], "검토 완료")

    def test_delegate_decision_renders_grounded_task_plan(self):
        decision = _parse_decision(
            '{"action":"delegate","target_agent_id":"fb-facilities-team",'
            '"purpose":"설비 확인을 요청합니다.","reason":"SOP 근거",'
            '"task_plan":{"grounding_basis":"설비 구매 전 기술 확인이 필요합니다.",'
            '"summary":"설비 확인부터 진행합니다.",'
            '"planned_tasks":["설비팀이 대상과 기술 제약을 확인합니다.",'
            '"확인 결과를 바탕으로 다음 검토 필요 여부를 판단합니다."]}}'
        )
        rendered = _chat_message_html(_task_plan_chat_message(decision))
        self.assertIn("업무 기준 기반 검토 계획", rendered)
        self.assertIn("설비 구매 전 기술 확인이 필요합니다.", rendered)
        self.assertIn("설비 확인부터 진행합니다.", rendered)
        self.assertIn("예정된 확인", rendered)

    def test_completed_decision_retries_only_the_requester_update(self):
        cards = {
            agent_id: SimpleNamespace(name=agent_id, description="test")
            for agent_id in AGENT_URLS
        }
        with patch(
            "src.agent_to_agent.orchestration.chat_tool_completion",
            side_effect=[
                _completion(
                    '{"action":"complete","target_agent_id":"complete","reason":"원본 감사 판단"}'
                ),
                _completion(
                    '{"action":"complete","target_agent_id":"complete","reason":"변경된 판단",'
                    '"requester_update":{"status":"검토 완료","summary":"요청을 검토했습니다.",'
                    '"next_action":"담당자가 결과를 확인해 주세요."}}'
                ),
            ],
        ) as completion:
            decision, _ = _orchestrator_turn(self.settings, "요청", [], cards)
        self.assertEqual(decision["reason"], "원본 감사 판단")
        self.assertEqual(
            decision["requester_update"]["summary"], "요청을 검토했습니다."
        )
        self.assertEqual(completion.call_count, 2)

    def test_display_summary_retry_preserves_original_artifact_fields(self):
        team = next(
            item for item in AGENT_CATALOG if item["agent_id"] == "fb-procurement-team"
        )
        with patch(
            "src.agent_to_agent.executor.chat_text",
            side_effect=[
                '{"finding":"원본 판단","evidence":"원본 근거","next_input":"추가 확인"}',
                '{"chat_summary":"현업 담당자가 확인할 내용을 정리했습니다."}',
            ],
        ) as completion:
            result = executor._json_object(
                self.settings,
                team,
                "검토 담당",
                {"request": "요청"},
                "{finding,evidence,next_input,chat_summary}",
                require_chat_summary=True,
            )
        self.assertEqual(result["finding"], "원본 판단")
        self.assertEqual(result["evidence"], "원본 근거")
        self.assertEqual(
            result["chat_summary"], "현업 담당자가 확인할 내용을 정리했습니다."
        )
        self.assertEqual(completion.call_count, 2)

    def test_final_card_uses_structured_update_without_reason_fallback(self):
        rendered = _chat_message_html(
            _field_response_chat_message(
                {
                    "status": "발송 전 검토 대기",
                    "summary": "검토용 메일 초안을 준비했습니다.",
                    "next_action": "검토자가 발송 여부를 결정해 주세요.",
                },
                "F&B 설비팀",
            )
        )
        self.assertIn("현재 상태", rendered)
        self.assertIn("발송 전 검토 대기", rendered)
        self.assertIn("다음 할 일", rendered)

    def test_orchestrator_prompt_is_evidence_based_without_keyword_route(self):
        cards = {
            agent_id: SimpleNamespace(name=agent_id, description="test")
            for agent_id in AGENT_URLS
        }
        captured: list[str] = []

        def fake_completion(settings, messages, tools, tool_choice=None):
            captured.append(messages[-1]["content"])
            return _completion(
                '{"action":"complete","target_agent_id":"complete","reason":"근거가 없습니다.","requester_update":{"status":"검토 완료","summary":"확인 가능한 근거가 없습니다.","next_action":"추가 정보를 확인해 주세요."}}'
            )

        with patch(
            "src.agent_to_agent.orchestration.chat_tool_completion",
            side_effect=fake_completion,
        ):
            _orchestrator_turn(self.settings, "일반 요청", [], cards)
        prompt = captured[0]
        self.assertIn(
            "Do not rely on a fixed Team order, keywords, or a preset", prompt
        )
        self.assertIn(
            "scoped Grounding evidence explicitly defines a bounded", prompt
        )
        self.assertIn(
            "defer\nHuman-in-the-loop approval and completion until artifacts from every",
            prompt,
        )
        self.assertIn("proactively assess whether a manual can establish", prompt)
        self.assertIn(
            "perform a focused manual search before deciding the first Team", prompt
        )
        self.assertIn("distinct observation or interpretation", prompt)
        self.assertIn("draft, proposal, prepared request, or review scenario", prompt)
        self.assertIn("prerequisite, required evidence, owner, or review state", prompt)
        self.assertIn("before/after mapping, target, or effective timing", prompt)
        self.assertIn("existing and proposed value", prompt)
        self.assertIn(
            "Internal artifacts and audit logs may retain exact Tool names", prompt
        )
        self.assertIn("never expose implementation details", prompt)
        self.assertIn("Do not mention Tool calls, Tool names, API/A2A terms", prompt)
        self.assertIn("requester-friendly Korean", prompt)
        self.assertNotIn("CIP 펌프", prompt)

    def test_manual_search_tool_call_records_grounding_evidence(self):
        cards = {
            agent_id: SimpleNamespace(name=agent_id, description="test")
            for agent_id in AGENT_URLS
        }
        tool_call = {
            "id": "manual-search-1",
            "function": {
                "name": "search_manuals",
                "arguments": '{"query": "구매 절차와 승인 조건"}',
            },
        }
        events: list[dict[str, object]] = []
        grounding_result = {
            "state": "grounded",
            "repository_id": "repository-1",
            "document_ids": ["sop-1"],
            "evidence": "SOP 근거",
        }

        with (
            patch(
                "src.agent_to_agent.orchestration.chat_tool_completion",
                side_effect=[
                    _completion("", [tool_call]),
                    _completion(
                        '{"action":"complete","target_agent_id":"complete","reason":"절차를 확인했습니다.","requester_update":{"status":"검토 완료","summary":"구매 절차를 확인했습니다.","next_action":"담당자 검토를 진행해 주세요."}}'
                    ),
                ],
            ),
            patch(
                "src.agent_to_agent.orchestration.collect_grounding_context",
                return_value=grounding_result,
            ),
        ):
            decision, grounding = _orchestrator_turn(
                self.settings,
                "구매를 진행해 주세요.",
                [],
                cards,
                on_grounding=events.append,
            )

        self.assertEqual(decision["target_agent_id"], "complete")
        self.assertEqual(grounding["state"], "grounded")
        self.assertEqual(grounding["searches"][0]["query"], "구매 절차와 승인 조건")
        self.assertEqual(
            [event["type"] for event in events],
            ["grounding_started", "grounding_context"],
        )

    def test_human_approval_tool_creates_a_draft_without_external_send(self):
        cards = {
            agent_id: SimpleNamespace(name=agent_id, description="test")
            for agent_id in AGENT_URLS
        }
        tool_call = {
            "id": "approval-draft-1",
            "function": {
                "name": "request_human_email_approval",
                "arguments": (
                    '{"recipient_role":"구매 책임자",'
                    '"subject":"구매 초안 검토 요청",'
                    '"body":"초안을 검토해 주세요.",'
                    '"reason":"공식 제출과 예산 판단은 사람 권한이 필요합니다.",'
                    '"chat_summary":"사람 검토가 필요한 메일 초안을 준비했습니다."}'
                ),
            },
        }
        drafts: list[dict[str, object]] = []
        with patch(
            "src.agent_to_agent.orchestration.chat_tool_completion",
            side_effect=[
                _completion("", [tool_call]),
                _completion(
                    '{"action":"complete","target_agent_id":"complete",'
                    '"reason":"초안은 사람 검토 후 발송할 수 있습니다.",'
                    '"requester_update":{"status":"발송 전 검토 대기","summary":"검토용 메일 초안을 준비했습니다.","next_action":"검토자가 초안을 확인하고 발송 여부를 결정해 주세요."}}'
                ),
            ],
        ) as completion:
            decision, _grounding = _orchestrator_turn(
                self.settings,
                "구매를 진행해 주세요.",
                [],
                cards,
                on_human_approval=lambda event: drafts.append(event["draft"]),
            )

        self.assertEqual(decision["target_agent_id"], "complete")
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["state"], "pending_human_approval")
        self.assertEqual(completion.call_count, 2)
        self.assertEqual(
            completion.call_args_list[1].args[1][-1]["role"],
            "tool",
        )

    def test_outlook_send_requires_explicit_write_setting_and_uses_eai_bridge(self):
        draft = human_approval.create_human_approval_draft(
            {
                "recipient_role": "구매 책임자",
                "subject": "구매 초안 검토 요청",
                "body": "초안을 검토해 주세요.",
                "reason": "사람 권한이 필요합니다.",
            }
        )
        with self.assertRaises(human_approval.OutlookMailError):
            human_approval.send_outlook_mail(
                self.settings,
                draft,
                recipients="reviewer@example.com",
                subject="제목",
                body="본문",
            )

        writable = Settings(
            "base",
            "auth",
            "client",
            "secret",
            "default",
            "gpt-5.6-luna",
            "",
            "",
            "cohere-reranker",
            True,
        )
        response = SimpleNamespace(
            status_code=202, json=lambda: {"state": "sent", "messageId": "msg-1"}
        )
        with (
            patch.dict(
                os.environ,
                {
                    "OUTLOOK_GRAPH_SEND_ENDPOINT": "http://127.0.0.1:18005/api/erp-eai/outbound/graph-mail/send/",
                    "A2A_GRAPH_MAIL_SERVICE_TOKEN": "test-token",
                },
                clear=False,
            ),
            patch(
                "src.agent_to_agent.human_approval.requests.post", return_value=response
            ) as post,
        ):
            result = human_approval.send_outlook_mail(
                writable,
                draft,
                recipients="reviewer@example.com",
                subject="제목",
                body="본문",
            )

        self.assertEqual(result["state"], "sent")
        self.assertEqual(result["recipient_count"], 1)
        request = post.call_args.kwargs
        self.assertEqual(request["headers"]["X-A2A-Graph-Mail-Token"], "test-token")
        self.assertEqual(request["json"]["toRecipients"], ["reviewer@example.com"])

    def test_human_approval_defaults_to_the_connected_graph_mailbox(self):
        with patch.dict(
            os.environ, {"GRAPH_FORWARDER_B_MAILBOX": "me@example.com"}, clear=False
        ):
            self.assertEqual(_default_outlook_recipient(), "me@example.com")

    def test_outlook_failure_exposes_an_explicit_chat_human_review_path(self):
        draft = {
            "approval_id": "approval-1",
            "state": "pending_human_approval",
        }
        failed = _delivery_failed_for_chat_review(draft)
        self.assertEqual(failed["state"], "pending_chat_human_review")
        self.assertEqual(failed["delivery_result"]["state"], "delivery_failed")
        self.assertEqual(failed["delivery_result"]["provider"], "outlook")
        self.assertEqual(draft["state"], "pending_human_approval")

        fallback_html = _chat_message_html(_human_approval_fallback_chat_message())
        self.assertIn("data-a2a-human-review-complete", fallback_html)
        self.assertIn("Human in the loop으로 검토 완료", fallback_html)

        reviewed = _human_reviewed_in_chat(failed)
        self.assertEqual(reviewed["state"], "human_reviewed")
        self.assertEqual(
            reviewed["review_result"]["provider"], "chat_human_in_the_loop"
        )
        self.assertEqual(reviewed["delivery_result"]["state"], "delivery_failed")

    def test_successful_graph_delivery_keeps_the_human_decision_in_chat(self):
        rendered = _chat_message_html(_human_approval_sent_chat_message())

        self.assertIn("Human in the loop", rendered)
        self.assertIn("명시적으로 승인", rendered)
        self.assertIn("Microsoft Graph", rendered)

    def test_human_approval_is_rendered_as_chat_actions_with_draft_tooltip(self):
        message = _human_approval_chat_message(
            {
                "recipient_role": "구매 책임자",
                "subject": "구매 요청 검토",
                "body": "초안의 발송 여부를 확인해 주세요.",
                "reason": "권한 있는 사람의 판단이 필요합니다.",
                "chat_summary": "검토자가 발송 여부를 결정할 메일 초안을 준비했습니다.",
            }
        )
        rendered = _chat_message_html(message)

        self.assertIn('data-a2a-approval-action="send"', rendered)
        self.assertIn('data-a2a-approval-action="cancel"', rendered)
        self.assertIn("Outlook 메일 발송", rendered)
        self.assertIn("발송하지 않음", rendered)
        self.assertIn("내용 보기", rendered)
        self.assertIn("구매 요청 검토", rendered)
        self.assertIn("검토자가 발송 여부를 결정할 메일 초안을 준비했습니다.", rendered)
        self.assertNotIn("a2a-group-chat__section", rendered)

    def test_runtime_prompt_templates_live_outside_python_modules(self):
        orchestration_source = Path(orchestration_module.__file__).read_text(
            encoding="utf-8"
        )
        executor_source = Path(executor.__file__).read_text(encoding="utf-8")

        self.assertIn("orchestration.observation_user", orchestration_source)
        self.assertIn("orchestration.decision_user", orchestration_source)
        self.assertIn("executor.review_user", executor_source)
        self.assertNotIn("Create a concise public observation", orchestration_source)
        self.assertNotIn(
            "Decide the next action entirely from the request", orchestration_source
        )
        self.assertNotIn("You are {role}. Ground the review", executor_source)

        rendered = render_prompt(
            "orchestration.decision_user",
            available="[]",
            observation="{}",
            grounding="{}",
            request="요청",
            artifacts="[]",
            conversation_history="[]",
        )
        self.assertIn('"action":"delegate|handoff|complete"', rendered)
        self.assertIn(
            "requester-friendly Korean", get_prompt("orchestration.decision_user")
        )

    def test_subagent_tool_is_role_scoped_while_the_model_selects_its_call(self):
        captured: list[object] = []

        def fake_completion(settings, messages, tools, tool_choice=None):
            captured.append(tool_choice)
            return _completion(
                '{"finding":"근거 요약","evidence":"기존 artifact","next_input":"없음"}'
            )

        team = next(
            item for item in AGENT_CATALOG if item["agent_id"] == "fb-procurement-team"
        )
        with patch(
            "src.agent_to_agent.executor.chat_tool_completion",
            side_effect=fake_completion,
        ):
            result = executor._json_object(
                self.settings,
                team,
                "구매조달 Agent",
                {"request": "요청"},
                "{finding,evidence,next_input}",
                "구매조달 Agent",
            )
        self.assertEqual(result["finding"], "근거 요약")
        self.assertEqual(captured, ["required"])

    def test_delegation_validation_accepts_only_team_owned_subagents(self):
        team = next(
            item
            for item in AGENT_CATALOG
            if item["agent_id"] == "finance-business-planning-team"
        )
        available = executor._available_subagents(team["agent_id"])
        valid = executor._valid_delegations(
            {
                "delegations": [
                    {"agent": "예산·관리회계 Agent", "goal": "예산 근거 검토"}
                ]
            },
            available,
        )
        invalid = executor._valid_delegations(
            {"delegations": [{"agent": "구매조달 Agent", "goal": "구매 검토"}]},
            available,
        )
        self.assertIsNotNone(valid)
        self.assertIsNone(invalid)

    def test_ui_topology_and_scenario_cards_render_new_responsibilities(self):
        topology = _agent_card_modal_html()
        self.assertIn("재무·사업기획팀 Agent", topology)
        self.assertIn("수익성·원가 Agent", topology)
        self.assertIn("lookup_financial_control_evidence", topology)
        self.assertIn("EHS 환경안전팀 Agent", topology)
        self.assertIn("화학물질·작업허가 Agent", topology)
        self.assertIn("lookup_ehs_evidence", topology)
        self.assertIn("품질팀 Agent", topology)
        self.assertIn("lookup_quality_evidence", topology)
        card = _scenario_card_html(
            "환율·원자재 가격 변동 사업성 평가",
            "경영기획 · 사업관리",
            "최근 환율과 원자재 가격 변동을 검토해 주세요.",
        )
        self.assertIn("요청 부서", card)
        self.assertIn("경영기획", card)

    def test_subagent_chat_uses_one_card_and_keeps_evidence_in_a_tooltip(self):
        message = _subagent_chat_message(
            {
                "agent": "구매조달 Agent",
                "team": "fb-procurement-team",
                "artifact": {
                    "finding": "구매 기록을 검토했습니다.",
                    "evidence": "로컬 스냅샷의 재고와 견적 기록입니다.",
                    "next_input": "필요 수량을 확인해 주세요.",
                    "chat_summary": "구매 가능 여부를 검토했고 필요한 수량 확인이 남아 있습니다.",
                    "tool_calls": [
                        {"name": "search_business_context"},
                        {"name": "lookup_procurement_evidence"},
                    ],
                },
            },
            {"fb-procurement-team": "F&B 구매팀 Agent"},
        )
        self.assertIsNotNone(message)
        self.assertEqual(message["sender"], "F&B 구매팀 Agent · 구매조달 Agent")
        rendered = _chat_message_html(message)

        self.assertEqual(rendered.count("a2a-group-chat__subagent-card"), 1)
        self.assertIn(
            "구매 가능 여부를 검토했고 필요한 수량 확인이 남아 있습니다.", rendered
        )
        self.assertNotIn("a2a-group-chat__tool-chip", rendered)
        self.assertIn("상세 보기", rendered)
        self.assertIn("로컬 스냅샷의 재고와 견적 기록입니다.", rendered)
        self.assertNotIn(">근거</div>", rendered)
        self.assertIn("근거\n로컬 스냅샷의 재고와 견적 기록입니다.", message["text"])

    def test_profitability_calculation_renders_scenario_and_collapsible_monthly_tables(
        self,
    ):
        calculation = calculate_profitability_scenarios("CTX-PROD-LEMON")
        message = _subagent_chat_message(
            {
                "agent": "수익성·원가 Agent",
                "team": "finance-business-planning-team",
                "artifact": {
                    "finding": "시나리오별 원가와 손익을 비교했습니다.",
                    "evidence": "월별 원가 계산 결과입니다.",
                    "next_input": "없음",
                    "chat_summary": "시나리오별 수익성을 비교했습니다.",
                    "tool_calls": [
                        {
                            "name": "calculate_profitability_scenarios",
                            "result": calculation,
                        }
                    ],
                },
            },
            {"finance-business-planning-team": "재무·사업기획팀 Agent"},
        )
        self.assertIsNotNone(message)
        rendered = _chat_message_html(message)

        self.assertIn("시나리오별 사업성", rendered)
        self.assertIn("호조", rendered)
        self.assertIn("기준", rendered)
        self.assertIn("악화", rendered)
        self.assertIn("월별 예상원가 · BEP 보기 (9건)", rendered)
        self.assertIn("<details", rendered)
        self.assertIn("206,875,000 KRW", rendered)
        self.assertNotIn("data/hana_raw", rendered)

    def test_team_chat_keeps_synthesis_evidence_in_a_tooltip(self):
        message = _artifact_chat_message(
            {
                "producer": "fb-procurement-team",
                "artifact": {
                    "payload": {
                        "team_synthesis": {
                            "summary": "구매 검토를 종합했습니다.",
                            "evidence": "로컬 재고·견적·예산 스냅샷을 확인했습니다.",
                            "next_action": "필요 수량을 확정해 주세요.",
                            "chat_summary": "구매 검토를 마쳤고 필요한 수량 확인이 남아 있습니다.",
                        }
                    }
                },
            },
            {"fb-procurement-team": "F&B 구매팀 Agent"},
        )
        rendered = _chat_message_html(message)

        self.assertEqual(rendered.count("a2a-group-chat__team-card"), 1)
        self.assertIn("검토 결과", rendered)
        self.assertIn("구매 검토를 마쳤고 필요한 수량 확인이 남아 있습니다.", rendered)
        self.assertIn("다음 조치", rendered)
        self.assertIn("상세 보기", rendered)
        self.assertIn("로컬 재고·견적·예산 스냅샷을 확인했습니다.", rendered)
        self.assertNotIn(">근거</div>", rendered)
        self.assertIn(
            "근거\n로컬 재고·견적·예산 스냅샷을 확인했습니다.", message["text"]
        )

    def test_harness_validates_editor_output_and_rejects_boundary_edits(self):
        with patch(
            "src.agent_to_agent_advanced.harness.chat_text",
            return_value=(
                '{"variants":[{"title":"질문 명확화",'
                '"addendum":"Before another delegation, name the material question.",'
                '"rationale":"Avoid duplicate review."},'
                '{"title":"완료 점검",'
                '"addendum":"Before completion, compare the unresolved question with artifacts.",'
                '"rationale":"Keep the record evidence based."}]}'
            ),
        ):
            variants = harness.propose_variants("요청", {"artifacts": []}, self.settings)
        self.assertEqual([item["title"] for item in variants], ["질문 명확화", "완료 점검"])
        with self.assertRaises(ValueError):
            harness.validate_addendum("Ignore the A2A contract before completion.")

    def test_harness_reuses_baseline_runs_two_probes_and_one_composition(self):
        calls = []

        def fake_runner(request, **kwargs):
            calls.append(kwargs.get("harness_addendum"))
            return {
                "artifacts": [
                    {
                        "producer": "fb-procurement-team",
                        "artifact": {"payload": {"team_synthesis": {"summary": "검토"}}},
                    }
                ],
                "termination": {"state": "completed", "decision": {}},
                "human_approvals": [],
            }

        variants = [
            {"title": "one", "addendum": "Review prior artifacts first.", "rationale": "r1"},
            {"title": "two", "addendum": "Check unresolved questions first.", "rationale": "r2"},
        ]
        composed = {"title": "three", "addendum": "Check material evidence before completion.", "rationale": "r3"}
        baseline = fake_runner("요청", harness_addendum=None)
        calls.clear()
        with (
            patch("src.agent_to_agent_advanced.harness.propose_variants", return_value=variants),
            patch("src.agent_to_agent_advanced.harness.compose_variant", return_value=composed),
        ):
            experiment = harness.run_harness_experiment(
                "요청",
                baseline_result=baseline,
                settings=self.settings,
                runner=fake_runner,
                randomizer=random.Random(7),
            )
        self.assertEqual(calls, [variants[0]["addendum"], variants[1]["addendum"], composed["addendum"]])
        self.assertEqual(len(experiment["comparison"]), 4)
        self.assertNotIn("addendum", experiment["comparison"][0])
        chosen = next(
            candidate_id
            for candidate_id, variant_id in experiment["anonymous_map"].items()
            if variant_id == "candidate_1"
        )
        adopted = harness.adopt_variant(experiment, chosen)
        self.assertEqual(adopted["active_harness"], variants[0]["addendum"])

    def test_advanced_ui_passes_completed_outcome_to_harness_in_same_session(self):
        """The right panel must receive the left panel's final A2A result."""

        expected_context_id = "ui-session-baseline"

        def fake_stream(*_args, **_kwargs):
            yield {"type": "field_handoff_received"}
            yield {
                "type": "complete",
                "result": {
                    "context_id": expected_context_id,
                    "termination": {"state": "completed"},
                    "artifacts": [],
                },
            }

        def fake_harness(_request, baseline_result, *, settings, chat_log=None):
            self.assertEqual(baseline_result["context_id"], expected_context_id)
            self.assertIs(settings, self.settings)
            self.assertIsInstance(chat_log, list)
            return {"trace": baseline_result, "decision": "no_change"}

        with (
            patch.object(advanced_ui, "list_agents", return_value=[]),
            patch.object(advanced_ui, "run_handoff_stream", fake_stream),
            patch.object(
                advanced_ui,
                "persist_a2a_conversation",
                return_value={"status": "completed"},
            ),
            patch.object(
                advanced_ui, "active_runtime_overlays_for_request",
                return_value=("", ""),
            ),
            patch.object(advanced_ui, "analyse_trace", fake_harness),
        ):
            app = advanced_ui.build_a2a_ui(self.settings)
            workflow = next(
                item.fn
                for item in app.fns.values()
                if item.fn is not None and item.fn.__name__ == "run_workflow"
            )
            harness_panel = next(
                item.fn
                for item in app.fns.values()
                if item.fn is not None and item.fn.__name__ == "run_harness_panel"
            )
            final_output = list(workflow("상태 전달 테스트"))[-1]
            baseline_result = final_output[3]
            harness_output = harness_panel("상태 전달 테스트", baseline_result, [])

        self.assertEqual(baseline_result["context_id"], expected_context_id)
        self.assertEqual(harness_output[1]["trace"]["context_id"], expected_context_id)

    def test_harness_does_not_execute_invalid_editor_proposals(self):
        calls = []

        def fake_runner(request, **kwargs):
            calls.append(kwargs.get("harness_addendum"))
            return {"artifacts": [], "termination": {"state": "completed"}}

        with patch(
            "src.agent_to_agent_advanced.harness.propose_variants",
            side_effect=ValueError("invalid editor JSON"),
        ):
            experiment = harness.run_harness_experiment(
                "요청", settings=self.settings, runner=fake_runner, randomizer=random.Random(3)
            )
        self.assertEqual(calls, [None])
        self.assertEqual(experiment["trials"]["candidate_1"]["status"], "failed")
        self.assertEqual(experiment["trials"]["composed"]["status"], "failed")

    def test_trace_harness_proposes_ranked_options_without_a_probe(self):
        editor_response = {
            "decision": "propose",
            "rationale": "재고 근거가 누락됐습니다.",
            "evidence": ["procurement artifact에 재고 확인이 없습니다."],
            "options": [
                {
                    "title": "Grounding 보강", "recommended": True,
                    "rationale": "영향 범위가 가장 좁습니다.",
                    "evidence": ["Grounding 검색이 없었습니다."],
                    "changes": [{"component": "grounding_document", "target": "procurement-sop", "instruction": "재고와 대체품 근거를 우선 확인한다."}],
                },
                {
                    "title": "Guardrail 보강", "recommended": False,
                    "rationale": "완료 전 검증을 추가합니다.",
                    "evidence": ["요청자 업데이트에 근거가 없습니다."],
                    "changes": [{"component": "guardrail", "target": "orchestration", "instruction": "근거 없이는 완료하지 않는다."}],
                },
            ],
        }
        result = {"context_id": "trace-1", "artifacts": [], "observations": [], "middleware": [], "grounding": {"searches": []}, "termination": {"state": "completed"}}
        with (
            patch.object(harness, "classify_request_domain", return_value="procurement"),
            patch("src.agent_to_agent_advanced.harness.chat_text", return_value=json.dumps(editor_response)) as editor,
        ):
            analysis = harness.analyse_trace("재고를 확인해 구매해 주세요.", result, self.settings)
        self.assertEqual(editor.call_count, 1)
        self.assertEqual(analysis["decision"], "propose")
        self.assertTrue(analysis["options"][0]["recommended"])
        self.assertEqual(analysis["options"][0]["option_id"], "option_1")
        self.assertIn("expected_benefit", analysis["options"][0]["impact"])

    def test_trace_summary_includes_repeated_chat_inputs_and_team_reuse(self):
        result = {
            "artifacts": [{"producer": "procurement"}, {"producer": "procurement"}],
            "termination": {"state": "completed"},
        }
        trace = harness.trace_summary(result, [
            {"kind": "field", "text": "납기일은 2026-10-30입니다."},
            {"kind": "field", "text": "납기일은 2026-10-30입니다."},
        ])
        self.assertEqual(trace["duplicate_teams"], ["procurement"])
        self.assertEqual(trace["user_input_count"], 2)
        self.assertEqual(trace["repeated_user_inputs"], ["납기일은 2026-10-30입니다."])

    def test_trace_summary_links_initial_task_to_missing_grounding_evidence(self):
        result = {
            "artifacts": [{
                "producer": "procurement",
                "orchestration": {
                    "purpose": "재고와 대체품을 확인합니다.",
                    "task_plan": {
                        "summary": "구매 가능 여부 검토",
                        "grounding_basis": "없음",
                        "planned_tasks": ["재고 기준을 확인합니다."],
                    },
                },
            }],
            "grounding": {
                "searches": [{
                    "query": "대체품 승인 기준",
                    "result": {
                        "state": "grounded", "document_ids": ["sop-1"],
                        "evidence": "제공된 문서에서 관련 근거를 찾지 못했습니다.",
                    },
                }],
            },
        }
        trace = harness.trace_summary(result)
        self.assertEqual(trace["initial_task"]["summary"], "구매 가능 여부 검토")
        self.assertTrue(trace["grounding_outcomes"][0]["no_relevant_evidence"])

    def test_skill_change_is_build_required_and_stages_manifest(self):
        option = harness._proposal_option({
            "title": "반복 입력 Skill", "recommended": True,
            "rationale": "반복 입력을 줄입니다.", "evidence": ["동일 입력이 반복됨"],
            "changes": [{"component": "skill", "target": "request-intake", "instruction": "반복 필드를 재사용 가능한 입력 양식으로 정리한다."}],
        }, 1)
        self.assertTrue(option["impact"]["build_required"])
        analysis = {
            "decision": "propose", "domain": "procurement", "trace_id": "trace-build",
            "request": "구매 요청", "options": [option],
        }
        with tempfile.TemporaryDirectory() as directory:
            revision = harness.apply_human_selection(analysis, "option_1", path=Path(directory) / "library.json")
            artifact = harness.build_revision_artifact(revision, directory=Path(directory) / "builds")
            manifest = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(revision["build_status"], "pending")
        self.assertEqual(manifest["deployment_status"], "staged")
        self.assertTrue(manifest["impact"]["build_required"])

    def test_grounding_revision_is_runtime_ready_and_reaches_live_search(self):
        option = harness._proposal_option({
            "title": "구매 SOP 근거 우선", "recommended": True,
            "rationale": "검색 근거를 보강합니다.", "evidence": ["Grounding 검색이 없었습니다."],
            "changes": [{"component": "grounding_document", "target": "procurement-sop", "instruction": "재고와 대체품 근거를 우선 확인한다."}],
        }, 1)
        self.assertFalse(option["impact"]["build_required"])
        with (
            patch.object(advanced_grounding, "list_documents", return_value=[{"id": "doc-1"}]),
            patch.object(advanced_grounding, "_grounded_answer", return_value="재고 근거") as search,
        ):
            result = advanced_grounding.collect_grounding_context(
                "재고를 확인해 주세요.", self.settings, repository_id="repo-1",
                runtime_overlay=harness.grounding_overlay_text(option["changes"]),
            )
        self.assertTrue(result["runtime_overlay_applied"])
        self.assertEqual(search.call_args.args[3], "[procurement-sop] 재고와 대체품 근거를 우선 확인한다.")

    def test_trace_harness_persists_human_selection_and_supports_rollback(self):
        analysis = {
            "decision": "propose", "domain": "procurement", "trace_id": "trace-2", "request": "구매 요청",
            "options": [{
                "option_id": "option_1", "title": "근거 보강", "recommended": True,
                "rationale": "재고 확인 누락", "evidence": ["재고 근거 없음"],
                "changes": [{"component": "guardrail", "target": "orchestration", "instruction": "재고 근거를 확인한다."}],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "library.json"
            revision = harness.apply_human_selection(analysis, "option_1", "납기 판단은 제외", path=path)
            self.assertIn("Human reviewer comment", revision["overlay"])
            with patch.object(harness, "classify_request_domain", return_value="procurement") as selector:
                overlay = harness.active_overlay_for_request("재고를 확인해 구매해 주세요.", self.settings, path=path)
            self.assertEqual(selector.call_count, 1)
            self.assertIn("재고 근거", overlay)
            rolled_back = harness.rollback_active_revision("procurement", path=path)
            self.assertEqual(rolled_back["status"], "rolled_back")
            self.assertEqual(harness.active_overlay_for_request("재고를 확인해 구매해 주세요.", self.settings, path=path), "")

    def test_harness_domain_is_selected_by_llm_and_restricted_to_allowed_values(self):
        with patch.object(harness, "chat_text", return_value='{"domain":"finance"}') as model:
            domain = harness.classify_request_domain("고객 주문의 비용 영향을 검토해 주세요.", self.settings)
        self.assertEqual(domain, "finance")
        self.assertEqual(model.call_count, 1)
        with patch.object(harness, "chat_text", return_value='{"domain":"unknown"}'):
            with self.assertRaises(ValueError):
                harness.classify_request_domain("일반 요청", self.settings)

    def test_harness_verifies_an_applied_flow_and_supports_session_rollback(self):
        baseline = {
            "team_order": ["procurement"],
            "artifact_count": 1,
            "termination_state": "completed",
            "requester_update": {"summary": "구매 검토 완료"},
            "evidence_summaries": ["재고 확인"],
        }
        experiment = {
            "request": "동일 요청",
            "trials": {"baseline": {"comparison": baseline}},
            "comparison": [{"candidate_id": "A", "status": "ok", **baseline}],
            "adoption": {
                "candidate_id": "A",
                "title": "근거 우선",
                "active_harness": "Review prior evidence before completion.",
            },
        }
        improved_result = {
            "artifacts": [
                {"producer": team, "artifact": {"payload": {"team_synthesis": {"summary": summary}}}}
                for team, summary in (
                    ("procurement", "재고 확인"),
                    ("planning", "생산 영향 확인"),
                    ("it", "ERP 준비 조건 확인"),
                )
            ],
            "termination": {
                "state": "completed",
                "decision": {"requester_update": {
                    "status": "ready", "summary": "검토 완료", "next_action": "승인 요청"
                }},
            },
            "human_approvals": [],
        }
        verification = harness.record_live_verification(experiment, improved_result, "동일 요청")
        self.assertEqual(verification["state"], "improved")
        self.assertGreater(verification["delta"], 0)
        self.assertIn("흐름 점수", _harness_dashboard_html(experiment))

        rollback = harness.rollback_adoption(experiment)
        self.assertEqual(rollback["candidate_id"], "A")
        self.assertNotIn("adoption", experiment)
        self.assertIn("세션 적용을 롤백했습니다", _harness_chat_html(experiment))

    def test_harness_panel_hides_addendum_until_human_adoption(self):
        self.assertIn("<svg", _harness_chat_html())
        self.assertNotIn(">H<", _harness_chat_html())
        self.assertNotIn("Harness² 비교 실행", _harness_chat_html())
        self.assertIn("Harness² 비교 실행", _harness_chat_html(baseline_ready=True))
        experiment = {
            "comparison": [
                {
                    "candidate_id": "A",
                    "status": "ok",
                    "team_order": ["fb-procurement-team"],
                    "artifact_count": 1,
                    "termination_state": "completed",
                    "requester_update": {"summary": "구매 검토 완료"},
                    "evidence_summaries": ["재고 확인"],
                }
            ]
        }
        before_adoption = _harness_chat_html(experiment)
        self.assertIn("Harness Labs", before_adoption)
        self.assertIn("Probe A", before_adoption)
        self.assertIn("사람 채택 후보 선택", before_adoption)
        self.assertNotIn("비공개 세션 보조 지침", before_adoption)

        after_adoption = _harness_chat_html(
            experiment,
            {
                "candidate_id": "A",
                "title": "근거 우선",
                "rationale": "결과를 확인한 뒤 채택했습니다.",
                "active_harness": "비공개 세션 보조 지침",
            },
        )
        self.assertIn("비공개 세션 보조 지침", after_adoption)

    def test_chat_actors_use_role_icons_instead_of_initial_letters(self):
        for sender, kind in (
            ("요청부서", "field"),
            ("Orchestration Agent", "orchestrator"),
            ("F&B 구매팀 Agent", "agent"),
            ("Human in the loop", "agent"),
            ("Outlook", "agent"),
        ):
            rendered = _chat_message_html(
                {"sender": sender, "kind": kind, "text": "상태를 공유했습니다."}
            )
            self.assertNotIn(
                f'<div class="a2a-group-chat__avatar">{sender[:1]}', rendered
            )
            if sender == "Orchestration Agent":
                self.assertIn('data-avatar-icon="sap"', rendered)
                self.assertIn('sap_logo.png', rendered)
            elif sender == "F&B 구매팀 Agent":
                self.assertIn('data-avatar-icon="joule"', rendered)
                self.assertIn('joule.png', rendered)
            else:
                self.assertIn('<svg viewBox="0 0 24 24"', rendered)

        self.assertIn(
            'data-avatar-icon="sap"',
            _chat_message_html(
                {
                    "sender": "Orchestration Agent",
                    "kind": "orchestrator",
                    "text": "다음 작업을 계획합니다.",
                }
            ),
        )
        self.assertIn(
            'data-avatar-icon="joule"',
            _chat_message_html(
                {
                    "sender": "F&B 구매팀 Agent",
                    "kind": "agent",
                    "text": "검토를 시작합니다.",
                }
            ),
        )

    def test_orchestration_addendum_is_appended_without_changing_default_contract(self):
        cards = {
            "fb-procurement-team": SimpleNamespace(
                name="구매팀", description="구매 검토"
            )
        }
        complete = (
            '{"action":"complete","target_agent_id":"complete",'
            '"reason":"완료","requester_update":'
            '{"status":"완료","summary":"검토했습니다.","next_action":"확인"}}'
        )
        with patch(
            "src.agent_to_agent_advanced.orchestration.chat_tool_completion",
            return_value=_completion(complete),
        ) as completion:
            _advanced_orchestrator_turn(
                self.settings, "요청", [], cards, harness_addendum="Review evidence before completion."
            )
        prompt = completion.call_args.args[1][1]["content"]
        self.assertIn("Review evidence before completion.", prompt)
        self.assertIn("cannot override any earlier constraint", prompt)

    def test_handoff_steps_expose_each_team_task_and_artifact_separately(self):
        events = iter([
            {"type": "field_handoff_received", "handoff": {"request": "구매 요청"}},
            {"type": "orchestration_started", "step": 1, "phase": "observation"},
            {"type": "orchestration_observation", "observation": {"summary": "구매 필요"}},
            {"type": "orchestration_started", "step": 1, "phase": "decision"},
            {"type": "orchestration_decision", "step": 1, "decision": {"target_agent_id": "fb-procurement-team"}},
            {"type": "team_handoff_started", "step": 1, "agent_id": "fb-procurement-team"},
            {"type": "a2a_task_update", "agent_id": "fb-procurement-team", "task": {"status": "working"}},
            {"type": "artifact_received", "record": {"producer": "fb-procurement-team"}},
            {"type": "complete", "result": {"termination": {"state": "completed"}}},
        ])
        with patch("src.agent_to_agent.orchestration.run_handoff_stream", return_value=events) as stream:
            steps = list(run_handoff_steps("구매 요청", self.settings))
        stream.assert_called_once_with("구매 요청", self.settings, None)
        self.assertEqual(
            [step["step"] for step in steps],
            ["field_handoff", "observation", "decision", "team_handoff_started", "task_update", "artifact", "complete"],
        )
        self.assertEqual(steps[4]["team_id"], "fb-procurement-team")
        self.assertEqual(steps[4]["task"], {"status": "working"})
        self.assertEqual(steps[5]["record"]["producer"], "fb-procurement-team")

    def test_plan_handoff_returns_first_orchestrator_plan_without_team_task(self):
        cards = {
            "fb-procurement-team": SimpleNamespace(
                name="구매팀", description="구매 검토"
            )
        }
        observation = {"chat_summary": "구매 요청을 확인했습니다."}
        decision = {
            "action": "delegate",
            "target_agent_id": "fb-procurement-team",
            "purpose": "구매 조건을 확인합니다.",
            "reason": "SOP 근거",
            "task_plan": {
                "grounding_basis": "구매팀 확인이 먼저 필요합니다.",
                "summary": "구매 조건을 확인합니다.",
                "planned_tasks": ["재고와 공급 조건을 확인합니다."],
            },
        }
        grounding = {"state": "grounded", "searches": []}
        discover = Mock(return_value="discovery-awaitable")
        with (
            patch(
                "src.agent_to_agent.orchestration.resolve_agent_urls",
                return_value={"fb-procurement-team": "http://team"},
            ),
            patch(
                "src.agent_to_agent.orchestration.discover_cards",
                new=discover,
            ),
            patch(
                "src.agent_to_agent.orchestration.run_sync", return_value=cards
            ),
            patch(
                "src.agent_to_agent.orchestration._orchestration_observation",
                return_value=observation,
            ) as observe,
            patch(
                "src.agent_to_agent.orchestration._orchestrator_turn",
                return_value=(decision, grounding),
            ) as decide,
        ):
            result = plan_handoff("구매 요청", self.settings)

        discover.assert_called_once_with({"fb-procurement-team": "http://team"})
        observe.assert_called_once()
        self.assertEqual(observe.call_args.args[:4], (self.settings, "구매 요청", [], cards))
        self.assertEqual(observe.call_args.args[4]["state"], "not_requested")
        self.assertEqual(result["decision"], decision)
        self.assertEqual(result["grounding"], grounding)
        self.assertIn("no Team Task", result["execution_boundary"])
        self.assertEqual(decide.call_args.kwargs["observation"], observation)


if __name__ == "__main__":
    unittest.main()
