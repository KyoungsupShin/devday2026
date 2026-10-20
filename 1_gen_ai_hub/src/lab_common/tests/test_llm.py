from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lab_common.config import Settings
from lab_common.llm import chat_text


class LlmTests(unittest.TestCase):
    def test_direct_chat_sends_the_shared_seed(self):
        settings = Settings(
            "base", "auth", "client", "secret", "default",
            "gpt-5.6-luna", "", "", "reranker", False,
            llm_seed=1234, llm_deployment_id="luna-deployment",
        )
        inference_client = Mock()
        inference_client.rest_client.post.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }
        with (
            patch(
                "lab_common.llm.model_deployment_url",
                return_value="https://deployment.example",
            ),
            patch(
                "lab_common.llm._aicore_sdk_client",
                return_value=inference_client,
            ),
        ):
            self.assertEqual(
                chat_text(settings, [{"role": "user", "content": "test"}]),
                "OK",
            )

        self.assertEqual(
            inference_client.rest_client.post.call_args.kwargs["body"],
            {
                "model": "gpt-5.6-luna",
                "messages": [{"role": "user", "content": "test"}],
                "seed": 1234,
            },
        )
