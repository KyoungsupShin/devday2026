from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "1_gen_ai_hub" / "src"))
sys.path.insert(0, str(ROOT / "3_gen_ai_hub_services"))

from lab_common.config import Settings
from src.grounding.lab_core import (
    run_help_grounded_query_with_trace,
    run_vector_grounded_query_with_trace,
)
from src.orchestration.lab_core import (
    DEFAULT_INPUT_PLACEHOLDER,
    get_orchestration_config,
    input_placeholders,
    invoke_saved_orchestration_config,
    list_orchestration_configs,
    run_orchestration,
)
from src.orchestration.str_lab import (
    SYNTHETIC_STR_CASE,
    SYNTHETIC_STR_DATABASE_RESULT,
    build_str_database_input,
    build_str_draft_request,
    summarize_str_database_result,
)


def settings() -> Settings:
    return Settings("", "", "", "", "default", "test", "", "", "test", False)


class FakeRegistryClient:
    def get_orchestration_configs(self, **kwargs):
        self.listed = kwargs
        class Resource:
            def model_dump(self, **_kwargs):
                return {"id": "config-123", "name": "assistant", "version": "1.0.0", "scenario": "devday"}
        return SimpleNamespace(
            count=1,
            resources=[Resource()],
        )


class FakeInvocationService:
    def __init__(self, config_ref):
        self.config_ref = config_ref

    def run(self, *, placeholder_values):
        return SimpleNamespace(
            final_result=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"answer: {placeholder_values['user_query']}"))]
            )
        )


class FakeRegistryRestClient:
    def __init__(self):
        self.requests = []

    def get(self, **kwargs):
        self.requests.append(kwargs)
        if kwargs["path"].endswith("config-123"):
            return {
                "id": "config-123",
                "spec": {"modules": {
                    "masking": {"providers": [{"mask_file_input_method": "anonymization"}]},
                    "prompt_templating": {"prompt": {"template": [{"content": "{{?question}}"}]}},
                }},
            }
        return {
            "count": 1,
            "resources": [{"id": "config-123", "spec": {"modules": {"prompt_templating": {}}}}],
        }


class RawRegistryClient:
    def __init__(self):
        self.rest_client = FakeRegistryRestClient()


class FakeGroundingService:
    def run(self, *, placeholder_values):
        return SimpleNamespace(
            final_result=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=f"grounded: {placeholder_values['user_query']}"
                        )
                    )
                ]
            ),
            intermediate_results=SimpleNamespace(
                grounding=SimpleNamespace(
                    message="retrieved 1 document",
                    data={"citations": [{"document_id": "guide-1"}]},
                )
            ),
        )


class ServiceCoreTests(unittest.TestCase):
    def test_synthetic_str_case_builds_a_fact_bound_human_review_prompt(self):
        request = build_str_draft_request(SYNTHETIC_STR_CASE)

        self.assertIn("STR-TRAIN-2026-001", request)
        self.assertIn("외부계좌-***-1842", request)
        self.assertIn("자동 생성된 내부 검토용 초안", request)
        self.assertIn("범죄·자금 출처·의도를 단정", request)

    def test_str_case_requires_transactions_risk_indicators_and_limitations(self):
        invalid_case = {**SYNTHETIC_STR_CASE, "transactions": []}

        with self.assertRaisesRegex(ValueError, "한 건 이상의 거래"):
            build_str_draft_request(invalid_case)

    def test_database_result_is_rendered_as_raw_masked_json_input(self):
        database_input = build_str_database_input(SYNTHETIC_STR_DATABASE_RESULT)

        self.assertEqual(json.loads(database_input), SYNTHETIC_STR_DATABASE_RESULT)
        self.assertIn('"ledger_transactions"', database_input)
        self.assertIn('"account_no_masked": "110-***-0427"', database_input)
        self.assertNotIn("내부 컴플라이언스 검토용 STR 초안", database_input)

    def test_database_result_summary_is_fact_only_and_uses_raw_ledger(self):
        summary = summarize_str_database_result(SYNTHETIC_STR_DATABASE_RESULT)

        self.assertEqual(summary["ledger_transaction_count"], 4)
        self.assertEqual(summary["total_credit_krw"], 9800000)
        self.assertEqual(summary["total_debit_krw"], 9600000)
        self.assertEqual(summary["masked_debit_counterparty_count"], 3)
        self.assertEqual(summary["time_window_minutes"], 16.0)

    def test_database_input_rejects_an_empty_ledger_before_orchestration(self):
        invalid_result = {**SYNTHETIC_STR_DATABASE_RESULT, "ledger_transactions": []}

        with self.assertRaisesRegex(ValueError, "ledger_transactions"):
            build_str_database_input(invalid_result)

    def test_list_configs_allows_empty_filters(self):
        registry = FakeRegistryClient()
        result = list_orchestration_configs(registry_client=registry)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["resources"][0]["id"], "config-123")
        self.assertEqual(
            registry.listed,
            {"scenario": None, "name": None, "version": None, "include_spec": False, "resolve_template_ref": False},
        )

    def test_registry_reads_raw_json_when_response_has_newer_module_fields(self):
        registry = RawRegistryClient()
        listed = list_orchestration_configs(registry_client=registry)
        detail = get_orchestration_config("config-123", registry_client=registry)

        self.assertEqual(listed["resources"][0]["id"], "config-123")
        self.assertEqual(detail["spec"]["modules"]["masking"]["providers"][0]["mask_file_input_method"], "anonymization")
        self.assertEqual(registry.rest_client.requests[0]["path"], "/registry/v2/orchestrationConfigs")

    def test_invoke_saved_config_passes_config_reference_to_service(self):
        seen = {}

        def service_factory(config_ref):
            seen["id"] = config_ref.id
            return FakeInvocationService(config_ref)

        result = invoke_saved_orchestration_config(
            "hello", settings(), config_id="config-123", placeholder_names=["user_query"],
            service_factory=service_factory,
        )
        self.assertEqual(seen["id"], "config-123")
        self.assertEqual(result, {"config_id": "config-123", "answer": "answer: hello"})

    def test_input_placeholders_uses_saved_config_names_and_excludes_generated_values(self):
        config = {
            "spec": {
                "modules": {
                    "grounding": {
                        "config": {
                            "placeholders": {"input": ["question"], "output": "grounding_response"}
                        }
                    },
                    "prompt_templating": {
                        "prompt": {
                            "template": [
                                {"content": "Question: {{?question}}\nContext: {{?grounding_response}}"}
                            ]
                        }
                    },
                }
            }
        }

        self.assertEqual(input_placeholders(config), ["question"])

    def test_input_placeholders_allows_static_saved_config(self):
        self.assertEqual(input_placeholders({"spec": {"modules": {}}}), [])

    def test_invoke_saved_config_uses_the_registered_placeholder_name(self):
        registry = RawRegistryClient()

        def service_factory(_config_ref):
            return SimpleNamespace(
                run=lambda *, placeholder_values: SimpleNamespace(
                    final_result=SimpleNamespace(
                        choices=[SimpleNamespace(
                            message=SimpleNamespace(content=f"answer: {placeholder_values['question']}")
                        )]
                    )
                )
            )

        result = invoke_saved_orchestration_config(
            "hello", settings(), config_id="config-123", registry_client=registry,
            service_factory=service_factory,
        )

        self.assertEqual(result, {"config_id": "config-123", "answer": "answer: hello"})

    def test_direct_orchestration_uses_input_var1(self):
        received: dict[str, str] = {}

        def run(*, placeholder_values):
            received.update(placeholder_values)
            return SimpleNamespace(
                final_result=SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))]
                )
            )

        with patch(
            "src.orchestration.lab_core.build_orchestration_service",
            return_value=SimpleNamespace(run=run),
        ):
            self.assertEqual(run_orchestration("DB 결과", settings()), "answer")

        self.assertEqual(received, {DEFAULT_INPUT_PLACEHOLDER: "DB 결과"})

    def test_grounded_query_trace_keeps_answer_and_returned_evidence(self):
        with patch(
            "src.grounding.lab_core.build_help_grounded_service",
            return_value=FakeGroundingService(),
        ):
            outcome = run_help_grounded_query_with_trace("What is Joule?", settings())

        self.assertEqual(outcome["answer"], "grounded: What is Joule?")
        self.assertEqual(outcome["grounding"]["configured_source"], "help.sap.com")
        self.assertTrue(outcome["grounding"]["metadata_available"])
        self.assertEqual(
            outcome["grounding"]["data"]["citations"][0]["document_id"], "guide-1"
        )

    def test_vector_grounded_query_trace_identifies_the_selected_repository(self):
        with patch(
            "src.grounding.lab_core.build_vector_grounded_service",
            return_value=FakeGroundingService(),
        ):
            outcome = run_vector_grounded_query_with_trace(
                "SOP 절차를 알려줘", settings(), repository_id="training-sop"
            )

        self.assertEqual(outcome["answer"], "grounded: SOP 절차를 알려줘")
        self.assertEqual(outcome["grounding"]["configured_source"], "vector:training-sop")

    def test_grounded_query_trace_does_not_invent_missing_evidence(self):
        response = SimpleNamespace(
            final_result=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="answer only"))]
            ),
            intermediate_results=SimpleNamespace(grounding=None),
        )
        service = SimpleNamespace(run=lambda **_kwargs: response)
        with patch(
            "src.grounding.lab_core.build_help_grounded_service", return_value=service
        ):
            outcome = run_help_grounded_query_with_trace("question", settings())

        self.assertFalse(outcome["grounding"]["metadata_available"])
        self.assertIsNone(outcome["grounding"]["data"])


if __name__ == "__main__":
    unittest.main()
