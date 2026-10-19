"""Durable local execution logs for the F&B A2A lesson."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEBUG_DIRECTORY = PROJECT_ROOT / "artifacts" / "debug"
LATEST_LOG_PATH = DEBUG_DIRECTORY / "latest_a2a_conversation.json"
HISTORY_LOG_PATH = DEBUG_DIRECTORY / "a2a_conversations.jsonl"
_LOG_WRITE_LOCK = Lock()


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def persist_a2a_conversation(
    snapshot: dict[str, Any],
    *,
    latest_path: Path = LATEST_LOG_PATH,
    history_path: Path = HISTORY_LOG_PATH,
) -> dict[str, str]:
    """Write one A2A run as the latest snapshot and an append-only history row.

    The log contains execution input, rendered conversation, event audit, and A2A
    outcome. Settings, environment variables, and credentials are never included.
    """
    record = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        **snapshot,
    }
    serialized = json.dumps(record, ensure_ascii=False, indent=2, default=str)
    history_row = json.dumps(record, ensure_ascii=False, default=str)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)

    with _LOG_WRITE_LOCK:
        temporary_path = latest_path.with_suffix(".tmp")
        temporary_path.write_text(serialized, encoding="utf-8")
        temporary_path.replace(latest_path)
        with history_path.open("a", encoding="utf-8") as history_file:
            history_file.write(history_row + "\n")

    return {
        "latest": _display_path(latest_path),
        "history": _display_path(history_path),
    }


def persist_human_approval_action(
    approval: dict[str, Any],
    result: dict[str, Any],
    conversation_message: dict[str, Any] | None = None,
    *,
    latest_path: Path = LATEST_LOG_PATH,
    history_path: Path = HISTORY_LOG_PATH,
) -> dict[str, str]:
    """Attach one explicit reviewer action without logging recipient addresses.

    The reviewed draft is already part of the conversation snapshot.  Keeping
    recipient addresses out of the JSONL audit makes the log useful for the
    lesson without turning it into a mailbox-address store.
    """
    safe_approval = {
        key: approval.get(key)
        for key in ("approval_id", "recipient_role", "reason", "state")
        if isinstance(approval.get(key), str)
    }
    safe_result = {
        key: result.get(key)
        for key in (
            "state",
            "provider",
            "failure_kind",
            "message_id",
            "recipient_count",
        )
        if result.get(key) not in (None, "")
    }
    action = {
        "event": "human_approval_action",
        "recorded_at": datetime.now(UTC).isoformat(),
        "approval": safe_approval,
        "result": safe_result,
    }
    with _LOG_WRITE_LOCK:
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            latest = {"schema_version": 1}
        actions = latest.get("human_approval_actions")
        latest["human_approval_actions"] = [
            *(actions if isinstance(actions, list) else []),
            action,
        ]
        if isinstance(conversation_message, dict):
            conversation = latest.get("conversation")
            latest["conversation"] = [
                *(conversation if isinstance(conversation, list) else []),
                conversation_message,
            ]
        temporary_path = latest_path.with_suffix(".tmp")
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(latest, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary_path.replace(latest_path)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as history_file:
            history_file.write(
                json.dumps(action, ensure_ascii=False, default=str) + "\n"
            )
    return {
        "latest": _display_path(latest_path),
        "history": _display_path(history_path),
    }
