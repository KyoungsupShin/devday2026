import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "1_gen_ai_hub" / "src"))
sys.path.insert(0, str(ROOT / "4_agent_patterns"))

from src.agent_to_agent_advanced import codex_app_server
from src.agent_to_agent_advanced.tools import hana_database
from src.agent_to_agent_advanced.ui import (
    _artifact_chat_message,
    _chat_message_html,
    _team_sections,
)


@contextmanager
def _connection(connection):
    yield connection


class _MetadataCursor:
    def __init__(self, calls):
        self.calls = calls

    def execute(self, statement, params=()):
        self.calls.append((statement, params))
        self.statement = statement

    def fetchall(self):
        if "SYS.TABLES" in self.statement:
            return [("CUSTOMER_ORDER",), ("PRODUCT",)]
        return [
            ("CUSTOMER_ORDER", "ORDER_ID", "NVARCHAR", 1),
            ("CUSTOMER_ORDER", "BUYER_PARTY_NAME", "NVARCHAR", 2),
            ("CUSTOMER_ORDER", "NET_AMOUNT", "DECIMAL", 3),
        ]


class _MetadataConnection:
    def __init__(self, calls):
        self.calls = calls

    def cursor(self):
        return _MetadataCursor(self.calls)


class _FakeCodexServer:
    def __init__(self):
        self.turn_start = None
        self.events = [
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thread-1",
                    "item": {
                        "type": "agentMessage",
                        "text": json.dumps(
                            {
                                "dialect": "SAP HANA SQL",
                                "sql": "SELECT BUYER_PARTY_NAME FROM CUSTOMER_ORDER LIMIT 10",
                                "explanation": "고객 주문을 조회합니다.",
                                "missing_inputs": [],
                                "safety_notes": "단일 읽기 전용 SELECT입니다.",
                            }
                        ),
                    },
                },
            },
            {
                "method": "turn/completed",
                "params": {"turn": {"id": "turn-1", "status": "completed"}},
            },
        ]

    def initialize(self):
        return None

    def request(self, method, params=None, timeout=30):
        if method == "thread/start":
            return {"thread": {"id": "thread-1"}}
        if method == "turn/start":
            self.turn_start = params
            return {"turn": {"id": "turn-1"}}
        return {}

    def next_event(self):
        return self.events.pop(0)

    def close(self):
        return None


class HanaSqlAgentTests(unittest.TestCase):
    def test_schema_discovery_is_bounded_and_parameterized(self):
        calls = []
        with (
            patch.object(hana_database, "_load_env_file"),
            patch.object(hana_database, "_connection", return_value=_connection(_MetadataConnection(calls))),
            patch.object(hana_database.os, "getenv", return_value="SAFE_SCHEMA"),
        ):
            metadata = hana_database.discover_hana_schema(max_tables=99, max_columns=999)

        self.assertEqual(metadata["schema_name"], "SAFE_SCHEMA")
        self.assertEqual(metadata["table_count"], 2)
        self.assertEqual(metadata["column_count"], 3)
        self.assertEqual(metadata["limits"], {"max_tables": 50, "max_columns": 500})
        self.assertTrue(all("SAFE_SCHEMA" not in statement for statement, _ in calls))
        self.assertEqual(calls[0][1], ("SAFE_SCHEMA", 50))
        self.assertEqual(calls[1][1][-1], 500)

    def test_schema_discovery_hides_driver_error(self):
        class BrokenCursor:
            def execute(self, statement, params=()):
                raise RuntimeError("password=not-for-output")

        class BrokenConnection:
            def cursor(self):
                return BrokenCursor()

        with (
            patch.object(hana_database, "_load_env_file"),
            patch.object(hana_database, "_connection", return_value=_connection(BrokenConnection())),
            patch.object(hana_database.os, "getenv", return_value="SAFE_SCHEMA"),
        ):
            with self.assertRaisesRegex(hana_database.HanaQueryError, "스키마 메타데이터") as error:
                hana_database.discover_hana_schema()
        self.assertNotIn("password", str(error.exception))

    def test_sql_generation_uses_discovered_metadata_without_sql_context(self):
        metadata = {
            "source": "sap_hana_schema_metadata",
            "schema_name": "SAFE_SCHEMA",
            "tables": [{"table_name": "CUSTOMER_ORDER", "columns": []}],
            "table_count": 1,
            "column_count": 0,
            "limits": {"max_tables": 50, "max_columns": 500},
        }
        server = _FakeCodexServer()
        with (
            patch.object(codex_app_server, "discover_hana_schema", return_value=metadata),
            patch.object(codex_app_server, "CodexAppServer", return_value=server),
            patch.object(
                codex_app_server,
                "execute_hana_readonly_query",
                return_value={"row_count": 1, "rows": [{"BUYER_PARTY_NAME": "A"}]},
            ),
        ):
            result = codex_app_server.run_codex_sql_generation(
                {"request": "고객 주문 상위 10개를 조회해줘"}
            )

        prompt = server.turn_start["input"][0]["text"]
        self.assertIn('"dialect": "SAP HANA SQL"', prompt)
        self.assertIn("CUSTOMER_ORDER", prompt)
        self.assertEqual(result["payload"]["hana_result"]["row_count"], 1)

    def test_ui_shows_sql_and_query_result(self):
        artifact = {
            "payload": {
                "sql_generation": {"sql": "SELECT * FROM CUSTOMER_ORDER", "missing_inputs": []},
                "hana_result": {"row_count": 1, "rows": [{"ORDER_ID": "1"}]},
                "team_synthesis": {"summary": "HANA 조회를 완료했습니다."},
            }
        }
        sections = _team_sections(artifact)
        labels = [section["label"] for section in sections]
        self.assertIn("생성 SQL", labels)
        self.assertIn("조회 결과", labels)
        message = _artifact_chat_message(
            {"producer": "codex-sql-generator-agent", "artifact": artifact},
            {"codex-sql-generator-agent": "Codex SQL Generator Agent"},
        )
        rendered = _chat_message_html(message)
        self.assertIn("생성 SQL", rendered)
        self.assertIn("SELECT * FROM CUSTOMER_ORDER", rendered)


if __name__ == "__main__":
    unittest.main()
