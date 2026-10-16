from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "1_gen_ai_hub"))

from src.litellm_adapter import (
    LiteLLMConfig,
    chat_completion,
    litellm_connection_status,
    load_litellm_config,
    openai_client,
)


class LiteLLMAdapterTests(unittest.TestCase):
    def test_loads_ai_secret_key_as_compatibility_alias(self):
        config = load_litellm_config({
            "LITELLM_BASE_URL": "https://litellm.example.test/v1/",
            "AI_SECRET_KEY": "do-not-display",
            "LLM_MODEL": "gateway-model",
        })
        self.assertEqual(config.base_url, "https://litellm.example.test/v1")
        self.assertEqual(config.api_key, "do-not-display")
        self.assertEqual(config.model, "gateway-model")

    def test_status_never_exposes_api_key(self):
        status = litellm_connection_status(LiteLLMConfig("https://proxy.example/v1", "secret-value", "model"))
        self.assertTrue(status["litellm_ready"])
        self.assertEqual(status["api_key"], "configured")
        self.assertNotIn("secret-value", status.values())

    def test_openai_client_receives_proxy_base_url_and_secret(self):
        calls: dict[str, str] = {}

        def factory(**kwargs):
            calls.update(kwargs)
            return "client"

        result = openai_client(LiteLLMConfig("https://proxy.example/v1", "key", "model"), client_factory=factory)
        self.assertEqual(result, "client")
        self.assertEqual(calls, {"base_url": "https://proxy.example/v1", "api_key": "key"})

    def test_chat_completion_uses_openai_compatible_shape(self):
        received: dict[str, object] = {}

        def create(**kwargs):
            received.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="안녕하세요"))])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        reply = chat_completion(
            [{"role": "user", "content": "안녕"}],
            LiteLLMConfig("https://proxy.example/v1", "key", "default-model"),
            model="chosen-model",
            client=client,
        )
        self.assertEqual(reply, "안녕하세요")
        self.assertEqual(received, {"model": "chosen-model", "messages": [{"role": "user", "content": "안녕"}]})


if __name__ == "__main__":
    unittest.main()
