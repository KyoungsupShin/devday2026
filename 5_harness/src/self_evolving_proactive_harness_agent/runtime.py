"""Bounded lifecycle runtime for one proactive cognitive cycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from collections.abc import Callable
from typing import Any

from .capabilities import capability_ids, discover_capabilities
from .datasets import analyze_csv_datasets
from .handoff import HandoffRequest, LocalCSVCapabilityAdapter
from .meta_agent import MetaCognitiveAgent
from .models import CognitiveDecision, CognitiveRun, CognitiveState, CognitiveTask, Goal, LifecycleStatus, ReactTurn, Reflection, Task, utc_now
from .repository import CognitiveRepository


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    max_tasks_per_cycle: int = 1
    max_llm_decisions_per_cycle: int = 6
    default_wait_minutes: int = 60


CycleEventCallback = Callable[[dict[str, Any]], None]


class CognitiveCore:
    """Coordinates state, Meta Agent decisions and read-only cognitive work."""

    def __init__(self, repository: CognitiveRepository, agent: MetaCognitiveAgent, *, policy: RuntimePolicy = RuntimePolicy()) -> None:
        self.repository, self.agent, self.policy = repository, agent, policy
        self.csv_adapter = LocalCSVCapabilityAdapter()

    def run_cycle(
        self, cognitive_id: str = "default", *, on_event: CycleEventCallback | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> CognitiveRun:
        state = self.repository.load_state(cognitive_id)
        run = CognitiveRun(cognitive_id=cognitive_id)
        self._emit(
            on_event, "react_evaluation", "completed", "이전 분석 이력과 현재 운영 상태를 불러왔습니다.", turn=0,
            lifecycle_status=state.lifecycle_status.value, revision=state.revision,
        )
        if state.lifecycle_status == LifecycleStatus.PAUSED:
            run.status, run.result_summary = "skipped", "자율 분석이 일시 중지되어 이번 검토는 실행하지 않습니다."
            self._emit(on_event, "react_evaluation", "blocked", run.result_summary, turn=0, terminal_reason="PAUSED")
            return run
        if not self.repository.start_run(run):
            run.status, run.result_summary = "skipped", "같은 분석 대상에 대한 실행이 이미 진행 중이어서 중복 실행하지 않습니다."
            self._emit(on_event, "react_evaluation", "blocked", run.result_summary, turn=0, terminal_reason="DUPLICATE_RUN")
            return run
        try:
            inventory = discover_capabilities()
            datasets = [item for item in inventory if item.get("kind") == "dataset"]
            known_dataset_ids = set(state.observed_dataset_ids)
            newly_available_datasets = [
                item for item in datasets if str(item.get("id", "")) not in known_dataset_ids
            ]
            # This is factual memory of the available inputs, not an action-routing rule.
            # It lets the Meta Agent explicitly decide whether newly supplied data merits review.
            state.observed_dataset_ids = sorted({
                *known_dataset_ids, *(str(item.get("id", "")) for item in datasets if item.get("id"))
            })
            tasks_executed_in_cycle = 0
            terminal_reason: str | None = None
            exit_reconsidered = False
            for turn_number in range(1, self.policy.max_llm_decisions_per_cycle + 1):
                if is_cancelled and is_cancelled():
                    run.status, run.result_summary = "skipped", "사용자가 실행 중단을 요청했습니다."
                    state.lifecycle_status, state.updated_at = LifecycleStatus.IDLE, utc_now()
                    self._emit(on_event, "react_evaluation", "blocked", run.result_summary, turn=turn_number, terminal_reason="CANCELLED")
                    return run
                observations = self._react_observations(
                    state, datasets, turn_number, newly_available_datasets if turn_number == 1 else []
                )
                self._emit(
                    on_event, "react_observation", "completed", observations[0], turn=turn_number,
                    observations=observations, datasets=[{"id": item.get("id"), "label": item.get("label")} for item in datasets],
                )
                state.lifecycle_status = LifecycleStatus.THINKING
                self._emit(on_event, "react_thinking", "running", "현재 근거를 바탕으로 우선순위가 높은 다음 조치를 판단하고 있습니다.", turn=turn_number)
                decision = self.agent.decide(state, inventory)
                exit_feedback = self._exit_consistency_feedback(state, decision, tasks_executed_in_cycle)
                if exit_feedback and not exit_reconsidered:
                    # This is a bounded correction, not a routing rule: the LLM
                    # receives the concrete contradiction and may still justify a WAIT.
                    exit_reconsidered = True
                    self._emit(on_event, "react_thinking", "running", "종료 판단과 진행 중인 업무의 일치 여부를 재확인하고 있습니다.", turn=turn_number, exit_feedback=exit_feedback)
                    decision = self.agent.decide(state, inventory, feedback=exit_feedback)
                if is_cancelled and is_cancelled():
                    run.status, run.result_summary = "skipped", "사용자가 실행 중단을 요청했습니다."
                    state.lifecycle_status, state.updated_at = LifecycleStatus.IDLE, utc_now()
                    self._emit(on_event, "react_evaluation", "blocked", run.result_summary, turn=turn_number, terminal_reason="CANCELLED")
                    return run
                if run.decision is None:
                    run.decision = decision
                self._record_agent_assessment(state, decision)
                self._emit(
                    on_event, "react_thinking", "completed",
                    f"{decision.action}: {decision.rationale}", turn=turn_number,
                    decision=decision.model_dump(mode="json"),
                )
                self._validate_decision(decision, inventory)
                self._emit(on_event, "react_action", "running", "승인된 읽기 전용 분석을 수행하고 있습니다.", turn=turn_number)
                outcome, task_executed = self._apply_decision(
                    state, decision, inventory, tasks_executed_in_cycle
                )
                tasks_executed_in_cycle += int(task_executed)
                if not state.recent_observations or state.recent_observations[-1] != outcome:
                    state.remember_observation(outcome)
                self._emit(
                    on_event, "react_action", "completed", outcome, turn=turn_number, action=decision.action
                    , goal_id=decision.goal_id, task_id=decision.task_id, handoff_id=self._handoff_id(state, decision.task_id),
                    remaining_decisions=self.policy.max_llm_decisions_per_cycle - turn_number
                )
                terminal_reason = self._terminal_reason(decision, turn_number, state)
                evaluation = self._evaluation_summary(decision, outcome, terminal_reason)
                react_turn = ReactTurn(
                    turn=turn_number, observations=observations, decision=decision,
                    action_summary=outcome, evaluation=evaluation, terminal_reason=terminal_reason,
                )
                run.react_turns.append(react_turn)
                self._emit(
                    on_event, "react_evaluation", "completed", evaluation, turn=turn_number,
                    evaluation=evaluation, terminal_reason=terminal_reason,
                )
                if terminal_reason:
                    break

            final_turn = run.react_turns[-1]
            state.lifecycle_status = LifecycleStatus.REFLECTING
            # A reflection is durable evidence for the next cycle, not a new
            # mandatory task.  It is recorded after a completed decision/action.
            state.reflection_history = [*state.reflection_history, Reflection(
                decision_action=final_turn.decision.action, outcome=final_turn.evaluation,
                task_id=final_turn.decision.task_id, goal_id=final_turn.decision.goal_id,
                expected_outcome=final_turn.decision.expected_value, actual_outcome=final_turn.action_summary,
                findings=[final_turn.action_summary], limitations=[] if final_turn.terminal_reason != "WAIT" else ["이번 실행에서는 추가 확인의 우선순위를 낮게 판단했습니다."],
            )][-20:]
            state.reasoning_summary = final_turn.decision.rationale
            state.lifecycle_status = LifecycleStatus.IDLE
            state.revision += 1
            state.updated_at = utc_now()
            run.status, run.result_summary = "completed", final_turn.evaluation
            run.audit = {
                "capability_count": len(inventory), "terminal_reason": final_turn.terminal_reason,
                "react_turns": [turn.model_dump(mode="json") for turn in run.react_turns],
            }
        except Exception as error:
            state.lifecycle_status = LifecycleStatus.FAILED
            state.remember_observation(f"Cognitive cycle failed: {error}")
            state.updated_at = utc_now()
            run.status, run.error = "failed", str(error)
            self._emit(on_event, "react_evaluation", "failed", f"Cycle failed: {error}", turn=len(run.react_turns) + 1, terminal_reason="FAILED")
        finally:
            run.completed_at = utc_now()
            self.repository.save_state(state)
            self.repository.finish_run(run)
        return run

    def run_due_cycle(self, cognitive_id: str = "default") -> CognitiveRun:
        """Compatibility entry point; scheduling is owned by the caller, not State."""
        return self.run_cycle(cognitive_id)

    @staticmethod
    def _emit(
        callback: CycleEventCallback | None, step: str, status: str, summary: str, **data: Any
    ) -> None:
        if callback:
            callback({"step": step, "status": status, "summary": summary, "data": data})

    def _react_observations(
        self, state: CognitiveState, datasets: list[dict[str, Any]], turn_number: int,
        newly_available_datasets: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        observations = [f"읽기 전용으로 확인 가능한 등록 데이터셋은 {len(datasets)}개입니다."]
        if newly_available_datasets:
            labels = ", ".join(str(item.get("label") or item.get("id")) for item in newly_available_datasets)
            observations.append(f"이번 검토에서 새로 확인된 데이터셋: {labels}. 기존 이력과 별도로 검토 필요성을 판단합니다.")
        if state.recent_observations:
            observations.append("이전 검토에서 확인한 사실을 이번 판단에 반영합니다: " + state.recent_observations[-1])
        else:
            observations.append("이전 검토 이력이 없어 현재 등록 데이터에서 기준 현황을 확인합니다.")
        return observations

    def _terminal_reason(self, decision: CognitiveDecision, turn_number: int, state: CognitiveState) -> str | None:
        if decision.action == "WAIT":
            return "WAIT"
        if decision.action == "REQUEST_APPROVAL":
            return "REQUEST_APPROVAL"
        if decision.action == "COMPLETE":
            if decision.goal_id and any(task.goal_id == decision.goal_id and task.status not in {"COMPLETED", "CANCELLED"} for task in state.tasks):
                return "COMPLETE_REJECTED"
            return "COMPLETE"
        if turn_number >= self.policy.max_llm_decisions_per_cycle:
            return "DECISION_BUDGET_REACHED"
        return None

    @staticmethod
    def _record_agent_assessment(state: CognitiveState, decision: CognitiveDecision) -> None:
        """Persist only the Meta Agent's explicit public cognitive memory."""
        for problem in decision.discovered_problems:
            if problem not in state.discovered_problems:
                state.discovered_problems.append(problem)
        for hypothesis in decision.hypotheses:
            if hypothesis not in state.hypotheses:
                state.hypotheses.append(hypothesis)

    @staticmethod
    def _evaluation_summary(decision: CognitiveDecision, outcome: str, terminal_reason: str | None) -> str:
        if terminal_reason == "WAIT":
            return f"평가 결과: 현재 근거로는 추가 조치의 우선순위가 낮아 이번 실행을 마칩니다. {outcome}"
        if terminal_reason == "REQUEST_APPROVAL":
            return "평가 결과: 외부 변경이 필요한 사안이므로 담당자 승인 전까지 자율 실행을 멈춥니다."
        if terminal_reason == "DECISION_BUDGET_REACHED":
            return f"평가 결과: 이번 회차의 데이터 이해와 후속 판단을 완료했습니다. 최신 분석 결과: {outcome}"
        if terminal_reason == "COMPLETE_REJECTED":
            return f"평가 결과: 완료 근거가 충분하지 않아 목표 상태를 유지했습니다. {outcome}"
        return f"평가 결과: 분석 결과를 다음 판단의 근거로 반영합니다. {outcome}"

    def pause(self, cognitive_id: str = "default") -> CognitiveState:
        state = self.repository.load_state(cognitive_id)
        state.lifecycle_status, state.updated_at = LifecycleStatus.PAUSED, utc_now()
        self.repository.save_state(state)
        return state

    def resume(self, cognitive_id: str = "default") -> CognitiveState:
        state = self.repository.load_state(cognitive_id)
        state.lifecycle_status, state.updated_at = LifecycleStatus.IDLE, utc_now()
        self.repository.save_state(state)
        return state

    def _validate_decision(self, decision: CognitiveDecision, inventory: list[dict[str, Any]]) -> None:
        unavailable = set(decision.required_capabilities) - capability_ids(inventory)
        if unavailable:
            raise ValueError("Decision requested unknown capabilities: " + ", ".join(sorted(unavailable)))
        if decision.action in {"CREATE_GOAL", "CREATE_TASK", "DELEGATE", "REVISE_GOAL", "EXPLORE", "INVESTIGATE", "VALIDATE"} and not decision.objective:
            raise ValueError(f"{decision.action} requires an objective")
        if decision.action == "SIMULATE" and decision.simulation is None:
            raise ValueError("SIMULATE requires a read-only simulation specification")

    def _exit_consistency_feedback(self, state: CognitiveState, decision: CognitiveDecision, tasks_executed: int) -> str | None:
        """Ask for one evidence-grounded reconsideration before an inconsistent exit."""
        if decision.action not in {"WAIT", "COMPLETE"}:
            return None
        ready = [task for task in state.tasks if task.status == "READY" and self._task_executable(state, task)]
        if ready and tasks_executed < self.policy.max_tasks_per_cycle:
            task = ready[0]
            return (
                f"종료 판단을 재검토하세요. 실행 가능한 미완료 업무가 있습니다: task_id={task.task_id}, "
                f"목표={task.objective}, capability={task.capability}. 이미 수행된 근거는 없습니다. "
                "종료가 적절하다면 업무를 지금 실행하지 않는 구체적 비즈니스 사유를 rationale에 적고 WAIT를 선택하세요. "
                "실행이 필요하면 task_id를 지정한 DELEGATE 또는 적절한 조치를 선택하세요."
            )
        if decision.action == "COMPLETE" and decision.goal_id:
            remaining = [task for task in state.tasks if task.goal_id == decision.goal_id and task.status not in {"COMPLETED", "CANCELLED"}]
            if remaining:
                return "해당 목표에는 완료되지 않은 업무가 있습니다. 완료 근거를 다시 확인하고, 목표를 완료하지 않거나 진행 중인 업무를 명시적으로 처리하세요."
        return None

    def _apply_decision(
        self, state: CognitiveState, decision: CognitiveDecision, inventory: list[dict[str, Any]],
        tasks_executed_in_cycle: int,
    ) -> tuple[str, bool]:
        if decision.action == "WAIT":
            return "추가 확인 가치가 낮아 이번 분석을 종료합니다.", False
        if decision.action == "REQUEST_APPROVAL":
            state.lifecycle_status = LifecycleStatus.WAITING
            state.remember_observation("Approval is required before the proposed external side effect.")
            return "담당자 승인이 필요한 사안으로 기록했으며, 외부 변경은 수행하지 않았습니다.", False
        if decision.action == "SIMULATE":
            spec = decision.simulation
            assert spec is not None
            task = self._ensure_portfolio_task(state, decision, "simulate_csv_scenario")
            return self._execute_handoff(state, task, decision, "simulate_csv_scenario"), True
        if decision.action in {"CREATE_GOAL", "REVISE_GOAL"}:
            goal = self._ensure_goal(state, decision)
            if decision.action == "REVISE_GOAL":
                goal.status, goal.updated_at = "ACTIVE", utc_now()
                return f"기존 개선 목표를 최신 근거에 맞춰 조정했습니다: {goal.title}", False
            return f"지속적으로 관리할 개선 목표를 등록했습니다: {goal.title}", False
        if decision.action == "CREATE_TASK":
            portfolio_task = self._ensure_portfolio_task(state, decision, self._preferred_csv_capability(decision))
            portfolio_task.status, portfolio_task.updated_at = "READY", utc_now()
            legacy_task = CognitiveTask(objective=decision.objective or portfolio_task.objective, required_capabilities=decision.required_capabilities)
            state.pending_tasks.append(legacy_task)
            return f"분석 업무를 준비 상태로 등록했습니다: {portfolio_task.title}. 다음 판단에서 실행 또는 보류 사유를 결정합니다.", False
        if decision.action in {"DELEGATE", "EXPLORE", "INVESTIGATE", "VALIDATE"}:
            existing = {task.objective for task in [*state.pending_tasks, *state.completed_tasks]}
            if decision.action != "DELEGATE" and decision.objective in existing:
                return "동일한 분석 과제가 이미 등록되어 중복 실행하지 않습니다.", False
            task = CognitiveTask(objective=decision.objective or "", required_capabilities=decision.required_capabilities)
            if decision.action != "DELEGATE":
                state.pending_tasks.append(task)
            if tasks_executed_in_cycle < self.policy.max_tasks_per_cycle:
                state.lifecycle_status = LifecycleStatus.INVESTIGATING
                task.status = "completed"
                portfolio_task = self._task_for_decision(state, decision)
                if not self._task_executable(state, portfolio_task):
                    portfolio_task.status, portfolio_task.updated_at = "BLOCKED", utc_now()
                    return f"업무를 실행하지 못했습니다. 의존성 또는 사용 가능한 분석 역량을 확인해야 합니다: {portfolio_task.title}", False
                task.result_summary = self._execute_handoff(state, portfolio_task, decision, portfolio_task.capability or "profile_tabular_snapshot")
                if task in state.pending_tasks:
                    state.pending_tasks.remove(task)
                state.completed_tasks.append(task)
                state.remember_observation(task.result_summary)
                return task.result_summary, True
            return "후속 분석 업무를 등록했습니다. 이번 실행에서는 안전 한도에 따라 추가 실행을 보류하며, 다음 실행에서 저장된 업무를 이어서 판단합니다.", False
        if decision.action == "COMPLETE":
            if decision.goal_id:
                goal = next((item for item in state.goals if item.goal_id == decision.goal_id), None)
                if goal:
                    if any(task.goal_id == goal.goal_id and task.status not in {"COMPLETED", "CANCELLED"} for task in state.tasks):
                        return "목표 완료 근거가 충분하지 않습니다. 미완료 업무는 유지했으며 다음 판단에서 재검토합니다.", False
                    goal.status, goal.updated_at = "COMPLETED", utc_now()
            return "현재 목표의 검토를 완료했으며, 추가 실행은 생성하지 않았습니다.", False
        return "분석 결과를 재검토했으며, 새 작업은 등록하지 않았습니다.", False

    @staticmethod
    def _preferred_csv_capability(decision: CognitiveDecision) -> str:
        valid = LocalCSVCapabilityAdapter.supported_capabilities
        return next((item for item in decision.required_capabilities if item in valid), "profile_tabular_snapshot")

    def _ensure_goal(self, state: CognitiveState, decision: CognitiveDecision) -> Goal:
        if decision.goal_id:
            existing = next((item for item in state.goals if item.goal_id == decision.goal_id), None)
            if existing:
                return existing
        details = decision.goal or {}
        title = str(details.get("title") or decision.objective or "운영 개선 기회 검토")
        goal = Goal(
            title=title, description=str(details.get("description") or decision.objective or title),
            expected_outcome=str(details.get("expected_outcome") or decision.expected_value or "업무상 개선 가능성 판단"),
            priority=int(details.get("priority", 3)), status="ACTIVE",
        )
        state.goals.append(goal)
        if goal.title not in state.active_goals:
            state.active_goals.append(goal.title)
        decision.goal_id = goal.goal_id
        return goal

    def _ensure_portfolio_task(self, state: CognitiveState, decision: CognitiveDecision, capability: str) -> Task:
        if decision.task_id:
            existing = next((item for item in state.tasks if item.task_id == decision.task_id), None)
            if existing:
                return existing
        goal = self._ensure_goal(state, decision)
        details = decision.task or {}
        objective = str(details.get("objective") or decision.objective or "등록 데이터의 운영상 근거를 확인합니다.")
        task = Task(
            goal_id=goal.goal_id, title=str(details.get("title") or objective), objective=objective,
            capability=str(details.get("capability") or capability), dependencies=list(details.get("dependencies") or []),
            expected_output=details.get("expected_output"), status="READY",
        )
        state.tasks.append(task)
        decision.task_id = task.task_id
        return task

    def _task_for_decision(self, state: CognitiveState, decision: CognitiveDecision) -> Task:
        if decision.task_id:
            task = next((item for item in state.tasks if item.task_id == decision.task_id), None)
            if task:
                return task
        # Older/compact decisions may omit task_id.  If there is exactly one
        # executable ready item, dispatching it is an unambiguous portfolio
        # reference rather than an action-routing heuristic.
        ready = [item for item in state.tasks if item.status == "READY" and self._task_executable(state, item)]
        if len(ready) == 1:
            decision.task_id, decision.goal_id = ready[0].task_id, ready[0].goal_id
            return ready[0]
        return self._ensure_portfolio_task(state, decision, self._preferred_csv_capability(decision))

    @staticmethod
    def _task_executable(state: CognitiveState, task: Task) -> bool:
        if task.status not in {"PROPOSED", "READY", "WAITING", "FAILED"}:
            return False
        if task.capability not in LocalCSVCapabilityAdapter.supported_capabilities:
            return False
        by_id = {item.task_id: item for item in state.tasks}
        return all(by_id.get(dependency) and by_id[dependency].status == "COMPLETED" for dependency in task.dependencies)

    @staticmethod
    def _handoff_id(state: CognitiveState, task_id: str | None) -> str | None:
        task = next((item for item in state.tasks if item.task_id == task_id), None)
        result = task.result if task else None
        return str(result.get("handoff_id")) if isinstance(result, dict) and result.get("handoff_id") else None

    def _execute_handoff(self, state: CognitiveState, task: Task, decision: CognitiveDecision, capability: str) -> str:
        task.status, task.updated_at = "RUNNING", utc_now()
        context: dict[str, Any] = {"dataset_ids": [item for item in decision.required_capabilities if item.startswith(("sap_", "mock_"))]}
        if decision.simulation:
            context["simulation"] = decision.simulation.model_dump(mode="json")
        request = HandoffRequest(task_id=task.task_id, goal_id=task.goal_id, capability=capability, objective=task.objective, context=context, constraints={"read_only": True}, idempotency_key=task.idempotency_key)
        result = self.csv_adapter.execute(request)
        task.result = result.model_dump(mode="json")
        task.status, task.updated_at = result.status, utc_now()
        if result.status == "COMPLETED":
            for evidence in result.evidence:
                state.remember_observation(evidence)
            return f"{task.title}을(를) 위한 Capability Handoff 분석을 완료했습니다. " + (result.evidence[0] if result.evidence else "확인 가능한 결과를 기록했습니다.")
        return "Capability Handoff 분석이 완료되지 않았습니다: " + (result.error or "알 수 없는 오류")

    @staticmethod
    def _inspect_inventory(state: CognitiveState, inventory: list[dict[str, Any]], requested: list[str]) -> str:
        selected = [
            item for item in inventory
            if not requested
            or item.get("id") in requested
            or set(item.get("capabilities", [])) & set(requested)
        ]
        dataset_ids = {str(item["id"]) for item in selected if item.get("kind") == "dataset"}
        analyses = analyze_csv_datasets(dataset_ids) if dataset_ids else []
        if analyses:
            for analysis in analyses:
                for observation in analysis["observations"]:
                    state.remember_observation(observation)
            return "출고 데이터 현황 점검을 완료했습니다. " + " ".join(
                observation for analysis in analyses for observation in analysis["observations"]
            )
        agents = sum(item.get("kind") == "agent" for item in selected)
        tools = sum(item.get("kind") == "tool" for item in selected)
        return f"활용 가능한 분석 역량을 정리했습니다. Agent {agents}개, 읽기 전용 분석 도구 {tools}개를 확인했습니다."
