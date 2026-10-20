from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "1_gen_ai_hub" / "src"), str(ROOT / "4_agent_patterns")]

from lab_common.config import Settings
from src.agent_to_agent import sop_grounding


def settings() -> Settings:
    return Settings(
        "https://aicore.example", "https://auth.example", "id", "secret",
        "default", "model", "", "", "", False,
    )


class SopGroundingTests(unittest.TestCase):
    def setUp(self):
        self.process = """## 프로세스

1. 요청 접수

2. 설비팀 → 구매팀 → 제조기획팀 순서로 검토한다.
"""
        self.restore_process = """## 프로세스

1. 복구 기준 절차
"""
        self.original = """# SOP

## 프로세스

1. 기존 절차

## Stakeholder와 책임

| 역할 | 책임 |
| --- | --- |
"""
        self.document = {
            "id": "original-resource",
            "metadata": [{"key": "id", "value": ["sop.md"]}],
        }

    def _source_file(self, directory: str) -> Path:
        source = Path(directory) / "sop.md"
        source.write_text(self.original, encoding="utf-8")
        return source

    @patch("src.agent_to_agent.sop_grounding.list_documents")
    def test_prepare_uses_explicit_restore_text_and_keeps_source_file(
        self, list_documents
    ):
        list_documents.return_value = [self.document]
        with tempfile.TemporaryDirectory() as directory:
            source = self._source_file(directory)
            change = sop_grounding.prepare_sop_replacement(
                settings(),
                source,
                self.process,
                repository_id="training-repository",
                restore_process=self.restore_process,
            )
            self.assertEqual(source.read_text(encoding="utf-8"), self.original)

        self.assertIn("설비팀 → 구매팀 → 제조기획팀", change.revised_text)
        self.assertIn("복구 기준 절차", change.original_text)
        self.assertIn("--- 복구할 SOP", sop_grounding.preview_sop_replacement(change))
        self.assertEqual(change.original_resource_id, "original-resource")

    @patch("src.agent_to_agent.sop_grounding.list_documents")
    def test_prepare_requires_exactly_one_metadata_match(self, list_documents):
        list_documents.return_value = []
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "정확히 하나"):
                sop_grounding.prepare_sop_replacement(
                    settings(), self._source_file(directory), self.process, repository_id="training-repository"
                )

    @patch("src.agent_to_agent.sop_grounding.prepare_sop_replacement")
    @patch("src.agent_to_agent.sop_grounding.load_settings")
    def test_default_prepare_hides_project_setup_from_the_notebook(
        self, load_settings, prepare_sop_replacement
    ):
        load_settings.return_value = "settings"
        prepare_sop_replacement.return_value = "change"

        result = sop_grounding.prepare_default_sop_replacement(
            self.process, self.restore_process
        )

        self.assertEqual(result, "change")
        prepare_sop_replacement.assert_called_once_with(
            "settings",
            sop_grounding.DEFAULT_SOP_SOURCE_PATH,
            self.process,
            restore_process=self.restore_process,
        )

    @patch("src.agent_to_agent.sop_grounding.upload_text_document", return_value={"status": "accepted"})
    @patch("src.agent_to_agent.sop_grounding.delete_document")
    @patch("src.agent_to_agent.sop_grounding.list_documents")
    def test_replace_then_restore_swaps_revised_and_original_text(
        self, list_documents, delete_document, upload_text_document
    ):
        list_documents.side_effect = [[self.document], [
            {"id": "revised-resource", "metadata": [{"key": "id", "value": ["sop.md"]}]}
        ]]
        with tempfile.TemporaryDirectory() as directory:
            change = sop_grounding.prepare_sop_replacement(
                settings(),
                self._source_file(directory),
                self.process,
                repository_id="training-repository",
                restore_process=self.restore_process,
            )
        sop_grounding.replace_sop(change)
        self.assertTrue(change.active)
        self.assertEqual(upload_text_document.call_args.kwargs["text"], change.revised_text)

        sop_grounding.restore_sop(change)
        self.assertFalse(change.active)
        self.assertEqual(
            upload_text_document.call_args.kwargs["text"], change.original_text
        )
        self.assertIn("복구 기준 절차", change.original_text)
        self.assertEqual(
            [call.args[2] for call in delete_document.call_args_list],
            ["original-resource", "revised-resource"],
        )


if __name__ == "__main__":
    unittest.main()
