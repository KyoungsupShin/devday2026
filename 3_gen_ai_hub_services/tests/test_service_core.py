from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "3_gen_ai_hub_services"))

from lab_common.config import Settings
from src.service_core import MemoryChatbot, configured_document_repository


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


if __name__ == "__main__":
    unittest.main()
