"""A schema-grounded read-only SQL Generator behind an A2A Agent Card."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from itertools import count
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from time import monotonic
from typing import Any

from a2a.helpers import new_data_part, new_task_from_user_message, new_text_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Role, TaskState
from google.protobuf.json_format import MessageToDict

from .catalog import HANDOFF_SCHEMA_VERSION
from .tools.hana_database import (
    HanaQueryError,
    discover_hana_schema,
    execute_hana_readonly_query,
)

CODEX_SQL_GENERATOR_AGENT_ID = "codex-sql-generator-agent"
# Preserve the initial notebook import name while the public Agent ID changes.
CODEX_REVIEW_AGENT_ID = CODEX_SQL_GENERATOR_AGENT_ID
_RESPONSE_TIMEOUT_SECONDS = 180
SQL_GENERATOR_SYSTEM_PROMPT = """You are Codex SQL Generator Agent for an F&B A2A workflow. Your only job is to generate one safe, executable, read-only SAP HANA SQL query from the supplied request and trusted schema metadata. The host has collected that metadata from the configured HANA schema. Use only its tables, columns, join keys, values, and SQL dialect; never invent schema elements or business facts.

Generate a single SELECT statement or a WITH ... SELECT query. Use SAP HANA SQL unless a supplied dialect explicitly says otherwise. For a HANA connection or metadata check, SELECT from DUMMY is permitted; use the exact scalar expressions CURRENT_SCHEMA and CURRENT_UTCTIMESTAMP without parentheses. Never generate INSERT, UPDATE, DELETE, MERGE, UPSERT, CREATE, ALTER, DROP, TRUNCATE, GRANT, REVOKE, CALL, EXECUTE, transaction-control statements, or multiple statements. Do not run shell commands, inspect files, or call external systems.

If the trusted schema metadata has no appropriate table or a required column, relationship, filter value, or time definition is absent, return an empty sql string and list the exact missing inputs. Return only the required JSON object."""


class CodexAppServer:
    """Small synchronous JSON-RPC client for one local App Server process."""

    def __init__(self) -> None:
        codex = shutil.which("codex")
        if not codex:
            raise RuntimeError("codex CLI를 찾을 수 없습니다. Codex CLI를 설치하고 로그인하세요.")
        self.process = subprocess.Popen(
            [codex, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._messages: Queue[dict[str, Any]] = Queue()
        self._events: list[dict[str, Any]] = []
        self._request_ids = count(1)
        Thread(target=self._read_stdout, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                self._messages.put(value)

    def _send(self, message: dict[str, Any]) -> None:
        if self.process.poll() is not None:
            raise RuntimeError("Codex App Server가 종료되었습니다.")
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def request(
        self, method: str, params: dict[str, Any] | None = None, timeout: int = 30
    ) -> dict[str, Any]:
        request_id = next(self._request_ids)
        self._send({"id": request_id, "method": method, "params": params or {}})
        deadline = monotonic() + timeout
        while True:
            try:
                message = self._messages.get(timeout=max(0.1, deadline - monotonic()))
            except Empty as error:
                raise TimeoutError(f"{method} 응답을 {timeout}초 안에 받지 못했습니다.") from error
            if message.get("id") != request_id:
                self._events.append(message)
                continue
            if "error" in message:
                raise RuntimeError(f"{method} 실패: {message['error']}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError(f"{method} 결과가 JSON 객체가 아닙니다.")
            return result

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "fnb_a2a_codex_sql_generator_agent",
                    "title": "F&B A2A Codex SQL Generator Agent",
                    "version": "1.0",
                },
                "capabilities": {},
            },
        )
        self._send({"method": "initialized", "params": {}})

    def next_event(self, timeout: int = _RESPONSE_TIMEOUT_SECONDS) -> dict[str, Any]:
        if self._events:
            return self._events.pop(0)
        try:
            return self._messages.get(timeout=timeout)
        except Empty as error:
            raise TimeoutError("Codex App Server event를 기다리는 시간이 초과되었습니다.") from error

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


def _handoff_payload(context: RequestContext) -> dict[str, Any]:
    if context.message is None:
        raise ValueError("A2A Message가 없습니다.")
    for part in context.message.parts:
        if not part.HasField("data"):
            continue
        handoff = MessageToDict(part.data, preserving_proto_field_name=True)
        if (
            handoff.get("schema_version") == HANDOFF_SCHEMA_VERSION
            and handoff.get("target_agent_id") == CODEX_SQL_GENERATOR_AGENT_ID
            and isinstance(handoff.get("input"), dict)
        ):
            return handoff["input"]
    raise ValueError("Codex SQL Generator Agent를 대상으로 한 JSON DataPart가 필요합니다.")


def _sql_generation_prompt(
    payload: dict[str, Any], schema_metadata: dict[str, Any]
) -> str:
    record = {
        "request": payload.get("request"),
        "sql_context": payload.get("sql_context") or {"dialect": "SAP HANA SQL"},
        "schema_metadata": schema_metadata,
        "grounding": payload.get("grounding"),
        "artifacts": payload.get("artifacts", []),
    }
    return (
        "Generate SQL for this A2A record. The JSON response schema is enforced.\n"
        "Do not explain outside the response object.\n\nA2A record:\n"
        + json.dumps(record, ensure_ascii=False)
    )


def _sql_generation_result(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.strip())
    except json.JSONDecodeError:
        value = {}
    keys = ("dialect", "sql", "explanation", "safety_notes")
    if isinstance(value, dict) and all(isinstance(value.get(key), str) for key in keys) and isinstance(value.get("missing_inputs"), list) and all(isinstance(item, str) for item in value["missing_inputs"]):
        return {**{key: value[key].strip() for key in keys}, "missing_inputs": [item.strip() for item in value["missing_inputs"] if item.strip()]}
    text = raw.strip() or "Codex App Server가 SQL 생성 결과를 반환하지 않았습니다."
    return {
        "dialect": "unknown", "sql": "", "explanation": text,
        "missing_inputs": ["SQL 응답 형식 또는 스키마 정보"],
        "safety_notes": "생성된 SQL은 실행하지 않았습니다.",
    }


def _codex_artifact(
    *,
    schema_metadata: dict[str, Any] | None,
    sql_generation: dict[str, Any],
    hana_result: dict[str, Any] | None = None,
    hana_error: str | None = None,
    schema_error: str | None = None,
) -> dict[str, Any]:
    table_count = schema_metadata.get("table_count", 0) if schema_metadata else 0
    if hana_result is not None:
        summary = f"HANA 조회를 완료했습니다. {hana_result['row_count']}건을 반환했습니다."
        chat_summary = "HANA 읽기 전용 조회 결과를 받았습니다."
    elif schema_error:
        summary = "HANA 스키마 메타데이터를 확인하지 못했습니다."
        chat_summary = "HANA 연결 또는 메타데이터 설정을 확인해야 합니다."
    else:
        summary = sql_generation["explanation"]
        chat_summary = "SQL 생성을 위해 스키마 정보를 더 확인해야 합니다."
    return {
        "type": "codex_sql_generation",
        "payload": {
            "team_agent_id": CODEX_SQL_GENERATOR_AGENT_ID,
            "schema_metadata": schema_metadata,
            "schema_error": schema_error,
            "sql_generation": sql_generation,
            "hana_result": hana_result,
            "hana_error": hana_error,
            "team_synthesis": {
                "summary": summary,
                "evidence": (
                    f"기본 HANA 스키마에서 테이블 {table_count}개 메타데이터를 읽기 전용으로 "
                    "확인하고, 그 범위에서 SQL을 생성했습니다."
                    if schema_metadata
                    else "HANA 스키마 메타데이터를 읽기 전용으로 확인하려 했습니다."
                ),
                "next_action": schema_error or hana_error or sql_generation["safety_notes"],
                "chat_summary": chat_summary,
            },
            "execution_boundary": "Codex App Server는 읽기 전용·무승인으로 실행됩니다. HANA Tool은 기본 스키마의 메타데이터와 단일 SELECT만 조회하며 파일·명령·외부 쓰기를 수행하지 않습니다.",
        },
    }


def run_codex_sql_generation(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        schema_metadata = discover_hana_schema()
    except HanaQueryError as error:
        return _codex_artifact(
            schema_metadata=None,
            schema_error=str(error),
            sql_generation={
                "dialect": "SAP HANA SQL",
                "sql": "",
                "explanation": "HANA 스키마 메타데이터를 확인할 수 없어 SQL을 생성하지 않았습니다.",
                "missing_inputs": ["HANA 연결 또는 기본 스키마 메타데이터"],
                "safety_notes": "메타데이터 확인 실패로 SQL을 실행하지 않았습니다.",
            },
        )
    server: CodexAppServer | None = CodexAppServer()
    try:
        server.initialize()
        thread = server.request(
            "thread/start",
            {
                "cwd": str(Path.cwd()),
                "ephemeral": True,
                "sandbox": "read-only",
                "approvalPolicy": "never",
                "developerInstructions": SQL_GENERATOR_SYSTEM_PROMPT,
            },
        ).get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise RuntimeError("Codex App Server가 thread ID를 반환하지 않았습니다.")
        turn = server.request(
            "turn/start",
            {
                "threadId": thread["id"],
                "input": [
                    {
                        "type": "text",
                        "text": _sql_generation_prompt(payload, schema_metadata),
                    }
                ],
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "dialect": {"type": "string"}, "sql": {"type": "string"},
                        "explanation": {"type": "string"},
                        "missing_inputs": {"type": "array", "items": {"type": "string"}},
                        "safety_notes": {"type": "string"},
                    },
                    "required": ["dialect", "sql", "explanation", "missing_inputs", "safety_notes"],
                    "additionalProperties": False,
                },
            },
            timeout=60,
        ).get("turn")
        if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
            raise RuntimeError("Codex App Server가 turn ID를 반환하지 않았습니다.")
        deltas: list[str] = []
        completed_message = ""
        while True:
            event = server.next_event()
            method = event.get("method")
            params = event.get("params")
            if not isinstance(params, dict):
                continue
            event_turn = params.get("turn")
            if isinstance(event_turn, dict) and event_turn.get("id") == turn["id"]:
                if method == "turn/completed":
                    if event_turn.get("status") != "completed":
                        raise RuntimeError(f"Codex turn이 완료되지 않았습니다: {event_turn.get('status')}")
                    break
            if params.get("threadId") != thread["id"]:
                continue
            if method in {"agentMessage/delta", "item/agentMessage/delta"}:
                delta = params.get("delta")
                if isinstance(delta, str):
                    deltas.append(delta)
            elif method == "item/completed":
                item = params.get("item")
                if isinstance(item, dict) and item.get("type") == "agentMessage":
                    text = item.get("text")
                    if isinstance(text, str):
                        completed_message = text
        sql_generation = _sql_generation_result(completed_message or "".join(deltas))
        hana_result: dict[str, Any] | None = None
        hana_error: str | None = None
        if sql_generation["sql"]:
            try:
                hana_result = execute_hana_readonly_query(sql_generation["sql"])
            except HanaQueryError as error:
                hana_error = str(error)
        return _codex_artifact(
            schema_metadata=schema_metadata,
            sql_generation=sql_generation,
            hana_result=hana_result,
            hana_error=hana_error,
        )
    finally:
        if server is not None:
            server.close()


class CodexAppServerExecutor(AgentExecutor):
    """Expose a local App Server SQL Generator as a streaming A2A Agent."""

    def __init__(self, agent_id: str) -> None:
        if agent_id != CODEX_SQL_GENERATOR_AGENT_ID:
            raise ValueError(f"알 수 없는 Codex App Server Agent: {agent_id}")
        self.agent_id = agent_id

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task_from_user_message(context.message)
        if context.current_task is None:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id)
        message = lambda text: new_text_message(
            text,
            media_type="text/plain",
            context_id=task.context_id,
            task_id=task.id,
            role=Role.ROLE_AGENT,
        )
        try:
            await updater.update_status(
                TaskState.TASK_STATE_WORKING,
                message(json.dumps({"event": "codex_sql_generation_started"}, ensure_ascii=False)),
            )
            result = await asyncio.to_thread(run_codex_sql_generation, _handoff_payload(context))
        except Exception as error:  # noqa: BLE001 - return every bridge failure through A2A
            await updater.failed(message(str(error)))
            return
        await updater.add_artifact(
            parts=[
                new_text_part("Schema-grounded read-only SQL generated by Codex App Server", media_type="text/plain"),
                new_data_part(result, media_type="application/json"),
            ],
            name=result["type"],
        )
        await updater.complete(
            message(json.dumps({"event": "codex_sql_generation_completed", "team": self.agent_id}, ensure_ascii=False))
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError
