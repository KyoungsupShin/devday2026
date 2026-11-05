"""Capability handoff boundary for autonomous portfolio work.

Only the local, read-only CSV adapter is available today.  Other adapters can
implement the same protocol later without changing the cognitive runtime.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .datasets import analyze_csv_datasets, simulate_csv_scenario


class HandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handoff_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    goal_id: str | None = None
    capability: str
    objective: str
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


class HandoffResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handoff_id: str
    task_id: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    error: str | None = None


class CapabilityAdapter(Protocol):
    def execute(self, request: HandoffRequest) -> HandoffResult: ...


class LocalCSVCapabilityAdapter:
    """Executes only registered, privacy-safe CSV operations."""

    supported_capabilities = {
        "inspect_csv_snapshot", "profile_tabular_snapshot", "simulate_csv_scenario",
    }

    def execute(self, request: HandoffRequest) -> HandoffResult:
        if request.capability not in self.supported_capabilities:
            return HandoffResult(handoff_id=request.handoff_id, task_id=request.task_id, status="FAILED", error="지원하지 않는 CSV 분석 역량입니다.")
        try:
            if request.capability == "simulate_csv_scenario":
                simulation = request.context.get("simulation") or {}
                text = simulate_csv_scenario(
                    str(simulation["dataset_id"]), str(simulation["baseline_column"]),
                    str(simulation["scenario_column"]), simulation.get("group_by"),
                )
                return HandoffResult(handoff_id=request.handoff_id, task_id=request.task_id, status="COMPLETED", output={"summary": text}, evidence=[text])
            ids = request.context.get("dataset_ids")
            profiles = analyze_csv_datasets(set(ids) if isinstance(ids, list) else None)
            evidence = [observation for profile in profiles for observation in profile["observations"]]
            return HandoffResult(handoff_id=request.handoff_id, task_id=request.task_id, status="COMPLETED", output={"profiles": profiles}, evidence=evidence)
        except (KeyError, TypeError, ValueError) as error:
            return HandoffResult(handoff_id=request.handoff_id, task_id=request.task_id, status="FAILED", error=str(error))
