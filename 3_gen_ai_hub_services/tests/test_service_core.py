from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "1_gen_ai_hub" / "src"))
sys.path.insert(0, str(ROOT / "3_gen_ai_hub_services"))

from lab_common.config import Settings
from src.grounding.lab_core import run_help_grounded_query_with_trace
from src.orchestration.lab_core import (
    get_orchestration_config,
    invoke_saved_orchestration_config,
    list_orchestration_configs,
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
                "spec": {"modules": {"masking": {"providers": [{"mask_file_input_method": "anonymization"}]}}},
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
            "hello", settings(), config_id="config-123", service_factory=service_factory
        )
        self.assertEqual(seen["id"], "config-123")
        self.assertEqual(result, {"config_id": "config-123", "answer": "answer: hello"})

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
