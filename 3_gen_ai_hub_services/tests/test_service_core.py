from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "3_gen_ai_hub_services"))

from lab_common.config import Settings
from src.documents.lab_core import configured_document_repository
from src.memory.lab_core import MemoryChatbot
from src.orchestration import lab_core as orchestration_core
from src.orchestration.lab_core import (
    delete_orchestration_config,
    invoke_saved_orchestration_config,
    save_orchestration_config,
)


def settings() -> Settings:
    return Settings("", "", "", "", "default", "test", "", "", "test", False)


class FakeService:
    def __init__(self):
        self.received_history = []

    def run(self, *, placeholder_values, history):
        self.received_history.append(list(history))
        answer = SimpleNamespace(content=f"echo: {placeholder_values['user_query']}")
        return SimpleNamespace(
            final_result=SimpleNamespace(choices=[SimpleNamespace(message=answer)]),
            intermediate_results=SimpleNamespace(templating=[SimpleNamespace(content="prior")]),
        )


class FakeRegistryClient:
    def __init__(self):
        self.saved = []
        self.deleted = []

    def create_orchestration_config(self, **kwargs):
        self.saved.append(kwargs)
        return SimpleNamespace(
            id="config-123", name=kwargs["name"], version=kwargs["version"],
            scenario=kwargs["scenario"], message="saved",
        )

    def delete_orchestration_config_by_id(self, config_id):
        self.deleted.append(config_id)
        return SimpleNamespace(message="deleted successfully")


class FakeInvocationService:
    def __init__(self, config_ref):
        self.config_ref = config_ref

    def run(self, *, placeholder_values):
        return SimpleNamespace(
            final_result=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"answer: {placeholder_values['user_query']}"))]
            )
        )


class ServiceCoreTests(unittest.TestCase):
    def test_memory_bot_passes_then_resets_history(self):
        service = FakeService()
        bot = MemoryChatbot(settings(), service=service)
        self.assertEqual(bot.chat("첫 질문"), "echo: 첫 질문")
        self.assertEqual(bot.chat("둘째 질문"), "echo: 둘째 질문")
        self.assertEqual(len(service.received_history[1]), 2)
        bot.reset()
        self.assertEqual(bot.history, [])

    def test_document_repository_requires_configuration(self):
        import os
        original = os.environ.pop("GROUNDING_REPOSITORY_ID", None)
        try:
            with self.assertRaisesRegex(RuntimeError, "GROUNDING_REPOSITORY_ID"):
                configured_document_repository()
        finally:
            if original is not None:
                os.environ["GROUNDING_REPOSITORY_ID"] = original

    def test_save_config_builds_spec_and_returns_json_friendly_result(self):
        registry = FakeRegistryClient()
        original_builder = orchestration_core.build_saved_orchestration_spec
        orchestration_core.build_saved_orchestration_spec = lambda *args, **kwargs: {"built": kwargs}
        try:
            result = save_orchestration_config(
                settings(),
                name="assistant",
                version="1.0.0",
                scenario="devday",
                system_prompt="Be helpful.",
                registry_client=registry,
            )
        finally:
            orchestration_core.build_saved_orchestration_spec = original_builder

        self.assertEqual(result["id"], "config-123")
        self.assertEqual(result["operation"], "saved")
        self.assertEqual(registry.saved[0]["spec"]["built"]["system_prompt"], "Be helpful.")

    def test_delete_config_uses_registry_client(self):
        registry = FakeRegistryClient()
        result = delete_orchestration_config("config-123", registry_client=registry)
        self.assertEqual(registry.deleted, ["config-123"])
        self.assertEqual(result, {"operation": "deleted", "id": "config-123", "message": "deleted successfully"})

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


if __name__ == "__main__":
    unittest.main()
