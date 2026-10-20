from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lab_common.ai_core import (
    _chat_timeout_seconds,
    _deployment_model_name,
    llm_model_params,
)
from lab_common.config import DEFAULT_LLM_MODEL, DEFAULT_LLM_SEED, Settings


class StreamContentTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            "base", "auth", "client", "secret", "default",
            "gpt-5.6-luna", "", "", "reranker", False,
            llm_seed=1234, llm_deployment_id="luna-deployment",
        )

    def test_extracts_a_model_name_from_an_ai_core_deployment(self):
        deployment = SimpleNamespace(
            details={"resources": {"backend_details": {"model": {"name": "gpt-4.1"}}}}
        )
        self.assertEqual(_deployment_model_name(deployment), "gpt-4.1")

    def test_uses_a_safe_chat_timeout_for_invalid_configuration(self):
        previous = os.environ.get("CHAT_TIMEOUT_SECONDS")
        try:
            os.environ["CHAT_TIMEOUT_SECONDS"] = "not-a-number"
            self.assertEqual(_chat_timeout_seconds(), 90.0)
        finally:
            if previous is None:
                os.environ.pop("CHAT_TIMEOUT_SECONDS", None)
            else:
                os.environ["CHAT_TIMEOUT_SECONDS"] = previous

    def test_luna_defaults_and_prompt_templating_parameters_use_one_seed(self):
        self.assertEqual(DEFAULT_LLM_MODEL, "gpt-5.6-luna")
        self.assertIsInstance(DEFAULT_LLM_SEED, int)
        self.assertEqual(
            llm_model_params(self.settings, max_tokens=200),
            {"max_tokens": 200, "seed": 1234},
        )

