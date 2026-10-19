from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lab_common.config import Settings, save_grounding_repository_id
from lab_common.grounding_repository import delete_document, list_documents, upload_text_document


def settings() -> Settings:
    return Settings("https://aicore.example", "https://auth.example", "id", "secret", "default", "model", "", "", "", False)


class Response:
    content = b"{}"

    def __init__(self, payload=None):
        self.payload = payload if payload is not None else {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class GroundingRepositoryTests(unittest.TestCase):
    def test_repository_id_is_added_then_updated_in_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("LLM_MODEL=test\nGROUNDING_REPOSITORY_ID=old\n", encoding="utf-8")
            save_grounding_repository_id("new-id", env_file)
            self.assertEqual(
                env_file.read_text(encoding="utf-8"),
                "LLM_MODEL=test\nGROUNDING_REPOSITORY_ID=new-id\n",
            )

    @patch("lab_common.grounding_repository.api_headers", return_value={"Authorization": "Bearer test"})
    @patch("lab_common.grounding_repository.requests.post")
    def test_upload_sends_filename_and_multiple_chunks(self, post, _headers):
        post.return_value = Response({"status": "accepted"})
        result = upload_text_document(settings(), "repo id", filename="guide.md", text="a" * 3_001)
        self.assertEqual(result, {"status": "accepted"})
        self.assertEqual(post.call_args.kwargs["json"]["documents"][0]["metadata"][0]["value"], ["guide.md"])
        self.assertEqual(len(post.call_args.kwargs["json"]["documents"][0]["chunks"]), 2)

    @patch("lab_common.grounding_repository.api_headers", return_value={})
    @patch("lab_common.grounding_repository.requests.get")
    def test_list_documents_reads_resources(self, get, _headers):
        get.return_value = Response({"resources": [{"id": "document-1"}]})
        self.assertEqual(list_documents(settings(), "repo"), [{"id": "document-1"}])

    @patch("lab_common.grounding_repository.api_headers", return_value={})
    @patch("lab_common.grounding_repository.requests.delete")
    def test_delete_escapes_document_id(self, delete, _headers):
        delete.return_value = Response()
        delete_document(settings(), "repo id", "a/b")
        self.assertTrue(delete.call_args.args[0].endswith("/a%2Fb"))


if __name__ == "__main__":
    unittest.main()
