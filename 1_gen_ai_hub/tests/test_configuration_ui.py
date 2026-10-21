from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "1_gen_ai_hub" / "src"))

import configuration_ui as ui


def complete_values() -> dict[str, str]:
    values = {key: "configured" for key in ui.ENVIRONMENT_KEYS}
    values.update(
        {
            "AICORE_BASE_URL": "https://ai-core.example.test",
            "AICORE_AUTH_URL": "https://auth.example.test",
            "AICORE_CLIENT_SECRET": "very-secret-value",
            "HANA_ENABLED": "false",
            "HANA_PORT": "443",
            "HANA_ENCRYPT": "true",
            "HANA_SSL_VALIDATE_CERTIFICATE": "true",
            "GRAPH_FORWARDER_B_MAILBOX": "hands-on@example.test",
            "OUTLOOK_GRAPH_SEND_ENDPOINT": "https://mail.example.test/send",
            "OUTLOOK_GRAPH_SEND_TIMEOUT_SECONDS": "30",
            "ALLOW_WRITE_TOOLS": "false",
        }
    )
    return values


class ConfigurationUiTests(unittest.TestCase):
    def test_catalog_contains_all_35_keys_in_five_cards(self):
        self.assertEqual(len(ui.CARDS), 5)
        self.assertEqual(len(ui.ENVIRONMENT_KEYS), 35)
        self.assertEqual(len(set(ui.ENVIRONMENT_KEYS)), 35)
        self.assertEqual(
            [card.name for card in ui.CARDS],
            ["AI CORE", "HANA DB", "OBJECT Store", "Grounding", "Graph API"],
        )

    def test_sidebar_visibility_selects_only_requested_card(self):
        self.assertEqual(ui.card_visibility("Grounding"), (False, False, False, True, False))

    def test_summary_uses_stacked_traffic_lights(self):
        summary = ui.render_environment_summary(
            {
                "AI CORE": {"state": "ready", "message": "설정됨"},
                "HANA DB": {"state": "error", "message": "누락"},
                "Graph API": {"state": "optional", "message": "선택"},
            }
        )
        self.assertIn("environment-status__light--ready", summary)
        self.assertIn("environment-status__light--error", summary)
        self.assertIn("environment-status__light--optional", summary)

    def test_missing_env_file_marks_each_card_as_an_error(self):
        statuses = ui.environment_status({key: "" for key in ui.ENVIRONMENT_KEYS}, env_exists=False)
        self.assertTrue(all(status["state"] == "error" for status in statuses.values()))
        self.assertIn(".env", statuses["AI CORE"]["message"])

    def test_optional_cards_are_skipped_only_when_entirely_empty(self):
        values = complete_values()
        for key in (
            "HANA_ENABLED", "HANA_HOST", "HANA_PORT", "HANA_USER", "HANA_PASSWORD",
            "HANA_ITEMS_TABLE", "HANA_ENCRYPT", "HANA_SSL_VALIDATE_CERTIFICATE", "HANA_SCHEMA",
            "GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_OAUTH_REFRESH_TOKEN",
            "GRAPH_FORWARDER_B_MAILBOX", "OUTLOOK_GRAPH_SEND_ENDPOINT",
            "A2A_GRAPH_MAIL_SERVICE_TOKEN", "OUTLOOK_GRAPH_SEND_TIMEOUT_SECONDS", "ALLOW_WRITE_TOOLS",
        ):
            values[key] = ""
        self.assertEqual(ui.validate_card(ui.CARD_BY_NAME["HANA DB"], values)["state"], "optional")
        self.assertEqual(ui.validate_card(ui.CARD_BY_NAME["Graph API"], values)["state"], "optional")

        values["GRAPH_CLIENT_ID"] = "configured"
        graph = ui.validate_card(ui.CARD_BY_NAME["Graph API"], values)
        self.assertEqual(graph["state"], "error")
        self.assertIn("GRAPH_TENANT_ID", graph["message"])

    def test_hana_schema_uses_the_connected_default_when_blank(self):
        values = complete_values()
        values["HANA_ENABLED"] = "true"
        values["HANA_SCHEMA"] = ""
        self.assertEqual(ui.validate_card(ui.CARD_BY_NAME["HANA DB"], values)["state"], "ready")

    def test_writer_preserves_comments_and_unmanaged_values(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("# keep this comment\nLLM_MODEL=old\nUNRELATED=value\n", encoding="utf-8")
            updated = ui._write_env(
                {"LLM_MODEL": "new", "EMBED_MODEL": "embed", "UNRELATED": "ignored"},
                env_file,
            )
            self.assertEqual(updated, ["LLM_MODEL", "EMBED_MODEL"])
            self.assertEqual(
                env_file.read_text(encoding="utf-8"),
                "# keep this comment\nLLM_MODEL=new\nUNRELATED=value\n\nEMBED_MODEL=embed\n",
            )

    def test_connection_check_uses_safe_results_and_hides_probe_details(self):
        values = complete_values()

        def failing_probe() -> str:
            raise RuntimeError("very-secret-value must never be displayed")

        probes = {name: (lambda name=name: f"{name} ok") for name in ["OBJECT Store", "Grounding", "Graph API"]}
        probes["AI CORE"] = failing_probe
        with patch.dict(os.environ, {}, clear=True):
            results = ui.run_environment_checks(values, probes=probes)
        self.assertEqual(results["HANA DB"], "⚪ 비활성 (HANA_ENABLED=false)")
        self.assertIn("연결 확인 실패: RuntimeError", results["AI CORE"])
        self.assertNotIn("very-secret-value", results["AI CORE"])
        self.assertEqual(results["Graph API"], "✅ Graph API ok")

    def test_card_check_runs_only_the_selected_card(self):
        values = complete_values()
        probes = {name: (lambda name=name: f"{name} ok") for name in ["AI CORE", "OBJECT Store", "Grounding", "Graph API"]}
        with patch.dict(os.environ, {}, clear=True):
            result = ui.run_card_check("Grounding", values, probes=probes)
        self.assertEqual(result, "✅ Grounding ok")


if __name__ == "__main__":
    unittest.main()
