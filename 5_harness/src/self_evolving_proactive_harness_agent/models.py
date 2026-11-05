"""Validated public state for the proactive cognitive loop."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LifecycleStatus(str, Enum):
    IDLE = "IDLE"
    THINKING = "THINKING"
    INVESTIGATING = "INVESTIGATING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    REFLECTING = "REFLECTING"
    WAITING = "WAITING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"


DecisionAction = Literal[
    "EXPLORE", "INVESTIGATE", "VALIDATE", "SIMULATE", "CREATE_GOAL", "CREATE_TASK", "DELEGATE",
    "REFLECT", "REVISE_GOAL", "WAIT", "COMPLETE", "REQUEST_APPROVAL",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


class CognitiveTask(BaseModel):
    """A compact, reviewable unit of autonomous work."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    objective: str
    required_capabilities: list[str] = Field(default_factory=list)
    status: Literal["pending", "completed", "blocked"] = "pending"
    created_at: datetime = Field(default_factory=utc_now)
    result_summary: str | None = None


GoalStatus = Literal["PROPOSED", "ACTIVE", "PAUSED", "COMPLETED", "CANCELLED"]
TaskStatus = Literal["PROPOSED", "READY", "RUNNING", "WAITING", "BLOCKED", "COMPLETED", "FAILED", "CANCELLED"]


class Goal(BaseModel):
    """A durable business outcome the agent is pursuing across cycles."""

    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str
    origin: str = "meta_cognitive_agent"
    expected_outcome: str
    priority: int = Field(default=3, ge=1, le=5)
    status: GoalStatus = "PROPOSED"
    related_problem_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Task(BaseModel):
    """An independently recoverable unit of work in a Goal."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    goal_id: str
    title: str
    objective: str
    capability: str | None = None
    status: TaskStatus = "PROPOSED"
    dependencies: list[str] = Field(default_factory=list)
    expected_output: str | None = None
    result: dict[str, Any] | None = None
    idempotency_key: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CognitiveDecision(BaseModel):
    """Schema accepted from the Meta Cognitive Agent.

    This model contains the decision rationale, not hidden chain-of-thought.
    """

    model_config = ConfigDict(extra="forbid")

    action: DecisionAction
    objective: str | None = None
    rationale: str = Field(min_length=1, max_length=2_000)
    expected_value: str | None = Field(default=None, max_length=1_000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    required_capabilities: list[str] = Field(default_factory=list, max_length=12)
    analysis_plan: list[str] = Field(default_factory=list, max_length=4)
    simulation: "SimulationSpec | None" = None
    discovered_problems: list[str] = Field(default_factory=list, max_length=6)
    hypotheses: list[str] = Field(default_factory=list, max_length=6)
    next_wakeup_at: datetime | None = None
    goal_id: str | None = None
    task_id: str | None = None
    goal: dict[str, Any] | None = None
    task: dict[str, Any] | None = None

    @field_validator("required_capabilities")
    @classmethod
    def _unique_capabilities(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("analysis_plan", "discovered_problems", "hypotheses")
    @classmethod
    def _bounded_korean_items(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(
            item.strip() for item in value
            if isinstance(item, str) and item.strip()
        ))


class Reflection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded_at: datetime = Field(default_factory=utc_now)
    decision_action: str
    outcome: str
    improvement: str | None = None
    reflection_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str | None = None
    goal_id: str | None = None
    expected_outcome: str | None = None
    actual_outcome: str | None = None
    findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)


class SimulationSpec(BaseModel):
    """An LLM-selected, read-only counterfactual comparison."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    baseline_column: str
    scenario_column: str
    group_by: str | None = None
    scenario_description: str = Field(min_length=1, max_length=500)


class ReactTurn(BaseModel):
    """One public, auditable ReAct turn without private model reasoning."""

    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=1)
    observations: list[str] = Field(default_factory=list)
    decision: CognitiveDecision
    action_summary: str
    evaluation: str
    terminal_reason: str | None = None


class CognitiveState(BaseModel):
    """Durable cognitive memory with only structured decision evidence."""

    model_config = ConfigDict(extra="forbid")

    cognitive_id: str = "default"
    current_objectives: list[str] = Field(default_factory=list)
    active_goals: list[str] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    discovered_problems: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    pending_tasks: list[CognitiveTask] = Field(default_factory=list)
    completed_tasks: list[CognitiveTask] = Field(default_factory=list)
    recent_observations: list[str] = Field(default_factory=list)
    observed_dataset_ids: list[str] = Field(default_factory=list)
    reasoning_summary: str = "No cognitive cycle has run."
    reflection_history: list[Reflection] = Field(default_factory=list)
    next_wakeup_at: datetime | None = None
    lifecycle_status: LifecycleStatus = LifecycleStatus.IDLE
    revision: int = 0
    updated_at: datetime = Field(default_factory=utc_now)

    def remember_observation(self, observation: str, *, limit: int = 12) -> None:
        if observation.strip():
            self.recent_observations = [*self.recent_observations, observation.strip()][-limit:]


class CognitiveRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    cognitive_id: str
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    status: Literal["running", "completed", "failed", "skipped"] = "running"
    decision: CognitiveDecision | None = None
    result_summary: str | None = None
    error: str | None = None
    react_turns: list[ReactTurn] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)
