from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "1_gen_ai_hub" / "src"))
sys.path.insert(0, str(ROOT / "1_gen_ai_hub"))

from lab_common.config import Settings
from src.environment import deployment_status, environment_status, write_environment_updates


def settings(*, client_secret: str = "secret") -> Settings:
    return Settings(
        base_url="https://api.example.test",
        auth_url="https://auth.example.test",
        client_id="client",
        client_secret=client_secret,
        resource_group="demo",
        llm_model="test-model",
        rerank_endpoint="",
        rerank_api_key="",
        rerank_model="test-rerank",
        allow_write_tools=False,
    )


class EnvironmentCoreTests(unittest.TestCase):
    def test_status_masks_credentials_and_reports_missing_fields(self):
        result = environment_status(settings(), embed_model="embed-test")
        self.assertTrue(result["ai_core_ready"])
        self.assertEqual(result["client_secret"], "configured")
        self.assertNotIn("secret", result.values())
        self.assertEqual(result["embedding_model"], "embed-test")

    def test_deployment_status_uses_injected_loader(self):
        result = deployment_status(
            settings(),
            deployment_loader=lambda _: [{"scenarioId": "orchestration", "status": "RUNNING", "deploymentUrl": "https://deployment.example.test"}],
        )
        self.assertEqual(result["resource_group"], "demo")
        self.assertEqual(result["running_deployments"][0]["scenario_id"], "orchestration")

    def test_environment_writer_preserves_comments_and_unrelated_values(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("# keep\nLLM_MODEL=old\nUNRELATED=value\n", encoding="utf-8")
            updated = write_environment_updates({"LLM_MODEL": "new", "EMBED_MODEL": "embed", "UNRELATED": "ignored"}, env_file)
            self.assertEqual(updated, ["LLM_MODEL", "EMBED_MODEL"])
            self.assertEqual(env_file.read_text(encoding="utf-8"), "# keep\nLLM_MODEL=new\nUNRELATED=value\n\nEMBED_MODEL=embed\n")


if __name__ == "__main__":
    unittest.main()
