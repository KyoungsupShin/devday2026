"""Durable repository boundary for cognitive state and run history."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from abc import ABC, abstractmethod
from pathlib import Path
from threading import Lock
from typing import Any

from src.paths import HARNESS_ROOT

from .models import CognitiveRun, CognitiveState, Goal, Task


class CognitiveRepository(ABC):
    """Port for the future HANA implementation and the notebook local store."""

    @abstractmethod
    def load_state(self, cognitive_id: str) -> CognitiveState: ...

    @abstractmethod
    def save_state(self, state: CognitiveState) -> None: ...

    @abstractmethod
    def start_run(self, run: CognitiveRun) -> bool: ...

    @abstractmethod
    def finish_run(self, run: CognitiveRun) -> None: ...

    @abstractmethod
    def list_runs(self, cognitive_id: str) -> list[CognitiveRun]: ...

    # Portfolio methods deliberately live on the repository boundary so a later
    # HANA implementation does not leak storage details into the Runtime.
    @abstractmethod
    def list_goals(self, cognitive_id: str) -> list[Goal]: ...

    @abstractmethod
    def list_tasks(self, cognitive_id: str, *, goal_id: str | None = None) -> list[Task]: ...


class JsonCognitiveRepository(CognitiveRepository):
    """Atomic local persistence used by the hands-on notebook.

    The JSON document is intentionally small and follows the same repository
    contract a HANA adapter will implement.  A running row provides a durable
    duplicate-run guard across notebook kernel restarts.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (HARNESS_ROOT / "artifacts" / "cognitive_core" / "state.json")
        self._lock = Lock()

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        return value if isinstance(value, dict) else {}

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(self.path)

    def load_state(self, cognitive_id: str) -> CognitiveState:
        with self._lock:
            states = self._read().get("states", {})
            payload = states.get(cognitive_id) if isinstance(states, dict) else None
            return CognitiveState.model_validate(payload or {"cognitive_id": cognitive_id})

    def save_state(self, state: CognitiveState) -> None:
        with self._lock:
            value = self._read()
            states = value.setdefault("states", {})
            states[state.cognitive_id] = state.model_dump(mode="json")
            self._write(value)

    def start_run(self, run: CognitiveRun) -> bool:
        with self._lock:
            value = self._read()
            runs = value.setdefault("runs", {})
            entries = runs.setdefault(run.cognitive_id, [])
            # A notebook kernel can be stopped while an LLM call is in flight.
            # Do not let that abandoned local record block every later manual run.
            stale_before = datetime.now(UTC) - timedelta(minutes=10)
            changed = False
            for row in entries:
                if not isinstance(row, dict) or row.get("status") != "running":
                    continue
                try:
                    started_at = datetime.fromisoformat(str(row.get("started_at", "")).replace("Z", "+00:00"))
                except ValueError:
                    started_at = datetime.min.replace(tzinfo=UTC)
                if started_at < stale_before:
                    row["status"] = "failed"
                    row["error"] = "Notebook 실행이 중단되어 오래된 실행을 종료 처리했습니다."
                    row["completed_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
                    changed = True
            if changed:
                self._write(value)
            if any(row.get("status") == "running" for row in entries if isinstance(row, dict)):
                return False
            entries.append(run.model_dump(mode="json"))
            self._write(value)
            return True

    def finish_run(self, run: CognitiveRun) -> None:
        with self._lock:
            value = self._read()
            entries = value.setdefault("runs", {}).setdefault(run.cognitive_id, [])
            for index, row in enumerate(entries):
                if isinstance(row, dict) and row.get("run_id") == run.run_id:
                    entries[index] = run.model_dump(mode="json")
                    break
            else:
                entries.append(run.model_dump(mode="json"))
            self._write(value)

    def list_runs(self, cognitive_id: str) -> list[CognitiveRun]:
        with self._lock:
            entries = self._read().get("runs", {}).get(cognitive_id, [])
            return [CognitiveRun.model_validate(row) for row in entries if isinstance(row, dict)]

    def list_goals(self, cognitive_id: str) -> list[Goal]:
        return self.load_state(cognitive_id).goals

    def list_tasks(self, cognitive_id: str, *, goal_id: str | None = None) -> list[Task]:
        tasks = self.load_state(cognitive_id).tasks
        return [task for task in tasks if goal_id is None or task.goal_id == goal_id]
