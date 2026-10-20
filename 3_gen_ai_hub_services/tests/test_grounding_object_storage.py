from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "1_gen_ai_hub" / "src"), str(ROOT / "3_gen_ai_hub_services")]

from lab_common.config import Settings
from src.grounding.object_storage import (
    ObjectStorageConfig,
    upload_markdown_to_object_storage_and_grounding,
)


def settings() -> Settings:
    return Settings("https://aicore.example", "https://auth.example", "id", "secret", "default", "model", "", "", "", False)


class FakeStorageClient:
    def __init__(self):
        self.request = {}

    def put_object(self, **kwargs):
        self.request = kwargs
        return {"ETag": "etag-123"}


class ObjectStorageGroundingTests(unittest.TestCase):
    def test_object_key_uses_prefix_and_rejects_parent_directory(self):
        storage = ObjectStorageConfig("https://storage.example", "key", "secret", "manuals", prefix="knowledge")
        self.assertEqual(storage.object_key("guide.md"), "knowledge/guide.md")
        with self.assertRaisesRegex(ValueError, "상대 경로"):
            storage.object_key("guide.md", "../guide.md")
        with self.assertRaisesRegex(ValueError, "상대 경로"):
            storage.object_key("guide.md", "/guide.md")

    @patch("src.grounding.object_storage.upload_text_document")
    def test_markdown_is_stored_then_indexed_with_source_metadata(self, index_document):
        storage = ObjectStorageConfig("https://storage.example", "key", "secret", "manuals", prefix="knowledge")
        client = FakeStorageClient()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "guide.md"
            source.write_text("# Grounding guide", encoding="utf-8")
            result = upload_markdown_to_object_storage_and_grounding(
                settings(), "vector-repository", file_path=source, storage=storage, storage_client=client
            )

        self.assertEqual(client.request["Bucket"], "manuals")
        self.assertEqual(client.request["Key"], "knowledge/guide.md")
        self.assertEqual(client.request["ContentType"], "text/markdown; charset=utf-8")
        self.assertEqual(result.document_id, "s3://manuals/knowledge/guide.md")
        self.assertEqual(result.etag, "etag-123")
        self.assertEqual(index_document.call_args.kwargs["document_id"], result.document_id)
        self.assertEqual(index_document.call_args.kwargs["metadata"]["object_storage_key"], "knowledge/guide.md")

    @patch("src.grounding.object_storage.upload_text_document", side_effect=ValueError("index failed"))
    def test_index_error_reports_the_uploaded_object_for_retry(self, _index_document):
        storage = ObjectStorageConfig("https://storage.example", "key", "secret", "manuals")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "guide.md"
            source.write_text("# Grounding guide", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "s3://manuals/grounding/guide.md"):
                upload_markdown_to_object_storage_and_grounding(
                    settings(), "vector-repository", file_path=source, storage=storage, storage_client=FakeStorageClient()
                )
