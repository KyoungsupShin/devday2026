"""Core workflow for ``01_agent_workflow.ipynb``."""
from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from queue import Empty, Queue
import re
from typing import Any

from lab_common.config import Settings, load_settings
from lab_common.models import TraceEvent

from .food_agents import FOOD_AGENT_BY_ID, evaluate_workflow_execution, plan_work_agents, run_food_agent
from .routing import FAST_ROUTE_CANDIDATES, decide


MAX_EVALUATION_LOOPS = 3


def build_contextual_request(
    request: str,
    conversation_history: list[dict[str, Any]] | None = None,
    marketing_html_draft: str | None = None,
) -> str:
    """Attach recent *plain-text* turns so a follow-up is not treated in isolation.

    This only supplies conversational context to the semantic route/orchestrator; it
    never selects an Agent or changes the execution plan deterministically.
    """
    turns: list[str] = []
    for item in (conversation_history or [])[-6:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        speaker = "사용자" if role == "user" else "AI"
        turns.append(f"{speaker}: {content.strip()}")
    sections: list[str] = []
    if turns:
        sections.append(
            "[최근 대화 맥락 — 현재 요청을 해석하기 위한 참고이며, 이전 답변을 그대로 반복하지 마세요]\n"
            + "\n".join(turns)
        )
    if isinstance(marketing_html_draft, str) and marketing_html_draft.strip():
        # Generated images can be several megabytes. The revision Agent needs the
        # HTML structure, not the data URL; retain a clear placeholder instead.
        safe_draft = re.sub(
            r"data:image/[^;\s]+;base64,[A-Za-z0-9+/=]+",
            "[이전 생성 이미지 asset]",
            marketing_html_draft.strip(),
        )
        sections.append("[현재 Marketing HTML 초안 — 현재 요청이 이 프로모션 HTML 생성·수정일 때만 원본으로 사용]\n" + safe_draft)
    if not sections:
        return request
    return "\n\n".join(sections) + f"\n\n[현재 사용자 요청]\n{request}"


def _append_trace(trace: list[TraceEvent], event: str, payload: dict[str, Any]) -> dict[str, Any]:
    item = TraceEvent(len(trace) + 1, event, payload)
    trace.append(item)
    return item.as_dict()


def _agent_context(
    request: str,
    brief: str,
    results: dict[str, dict[str, Any]],
    upstream_ids: list[str],
    stage_objective: str,
) -> str:
    upstream = "\n\n".join(
        f"[{results[agent_id]['agent_label']} 결과]\n{results[agent_id]['answer']}"
        for agent_id in upstream_ids
    )
    return (
        f"{request}\n\n[Orchestrator 공통 브리프]\n{brief}\n\n"
        f"[현재 실행 단계 목표]\n{stage_objective}"
        + (f"\n\n아래 선행 Agent 결과를 근거로 사용하세요. 충돌하거나 누락된 정보는 가정으로 표시하세요.\n{upstream}" if upstream else "")
    )


def _completed_event(trace: list[TraceEvent], result: dict[str, Any]) -> dict[str, Any]:
    return _append_trace(
        trace,
        "agent_completed",
        {
            "agent_id": result["agent_id"],
            "label": result["agent_label"],
            "status": "completed",
            "tool_calls": result.get("tool_calls", []),
        },
    )


def _run_food_pipeline(
    request: str,
    results: dict[str, dict[str, Any]],
    settings: Settings,
    trace: list[TraceEvent],
) -> Iterator[dict[str, Any]]:
    """Execute only the stages selected by the Orchestrator LLM."""
    orchestrator = FOOD_AGENT_BY_ID["work-planning"]
    yield {
        "type": "agent_started",
        "trace_event": _append_trace(trace, "agent_started", {"agent_id": orchestrator.id, "label": orchestrator.label}),
    }
    plan = plan_work_agents(request, settings)
    planning_result = {
        "agent_id": orchestrator.id,
        "agent_label": orchestrator.label,
        "answer": plan["brief"],
        "tool_calls": [],
    }
    results[orchestrator.id] = planning_result
    yield {
        "type": "agent_completed",
        "agent_result": planning_result,
        "trace_event": _completed_event(trace, planning_result),
    }
    selected_ids = [agent_id for stage in plan["stages"] for agent_id in stage["agent_ids"]]
    yield {
        "type": "orchestration_plan",
        "plan": plan,
        "trace_event": _append_trace(
            trace,
            "orchestration_plan",
            {"stages": plan["stages"], "final_agent_id": plan["final_agent_id"], "selected_agent_ids": selected_ids},
        ),
    }

    deltas: Queue[tuple[str, str]] = Queue()

    def run_agent_with_stream(agent_id: str, context: str) -> dict[str, Any]:
        return run_food_agent(agent_id, context, settings, on_delta=lambda text: deltas.put((agent_id, text)))

    def drain_deltas() -> Iterator[dict[str, Any]]:
        while True:
            try:
                agent_id, text = deltas.get_nowait()
            except Empty:
                return
            yield {"type": "agent_delta", "agent_id": agent_id, "delta": text}

    completed_specialists: list[str] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        for stage in plan["stages"]:
            futures: dict[Any, str] = {}
            for agent_id in stage["agent_ids"]:
                context = _agent_context(request, plan["brief"], results, completed_specialists, stage["objective"])
                futures[executor.submit(run_agent_with_stream, agent_id, context)] = agent_id
                agent = FOOD_AGENT_BY_ID[agent_id]
                yield {
                    "type": "agent_started",
                    "trace_event": _append_trace(trace, "agent_started", {"agent_id": agent.id, "label": agent.label}),
                }
            while futures:
                completed, _ = wait(futures, timeout=0.05, return_when=FIRST_COMPLETED)
                yield from drain_deltas()
                for future in completed:
                    agent_id = futures.pop(future)
                    result = future.result()
                    results[agent_id] = result
                    completed_specialists.append(agent_id)
                    yield from drain_deltas()
                    yield {
                        "type": "agent_completed",
                        "agent_result": result,
                        "trace_event": _completed_event(trace, result),
                    }
    return plan


def _run_revision_stages(
    request: str,
    plan: dict[str, Any],
    revision_stages: list[dict[str, Any]],
    results: dict[str, dict[str, Any]],
    settings: Settings,
    trace: list[TraceEvent],
) -> Iterator[dict[str, Any]]:
    """Re-run only the LLM-selected stages requested by Evaluation Middleware."""
    deltas: Queue[tuple[str, str]] = Queue()

    def run_agent_with_stream(agent_id: str, context: str) -> dict[str, Any]:
        return run_food_agent(agent_id, context, settings, on_delta=lambda text: deltas.put((agent_id, text)))

    def drain_deltas() -> Iterator[dict[str, Any]]:
        while True:
            try:
                agent_id, text = deltas.get_nowait()
            except Empty:
                return
            yield {"type": "agent_delta", "agent_id": agent_id, "delta": text}

    completed_specialists = [agent_id for agent_id in results if agent_id != "work-planning"]
    with ThreadPoolExecutor(max_workers=3) as executor:
        for stage in revision_stages:
            futures: dict[Any, str] = {}
            for agent_id in stage["agent_ids"]:
                context = _agent_context(request, plan["brief"], results, completed_specialists, stage["objective"])
                futures[executor.submit(run_agent_with_stream, agent_id, context)] = agent_id
                agent = FOOD_AGENT_BY_ID[agent_id]
                yield {
                    "type": "agent_started",
                    "trace_event": _append_trace(trace, "agent_started", {"agent_id": agent.id, "label": agent.label, "rework": True}),
                }
            while futures:
                completed, _ = wait(futures, timeout=0.05, return_when=FIRST_COMPLETED)
                yield from drain_deltas()
                for future in completed:
                    agent_id = futures.pop(future)
                    result = future.result()
                    results[agent_id] = result
                    if agent_id not in completed_specialists:
                        completed_specialists.append(agent_id)
                    yield from drain_deltas()
                    yield {
                        "type": "agent_completed",
                        "agent_result": result,
                        "trace_event": _completed_event(trace, result),
                    }


def run_workflow_stream(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
    conversation_history: list[dict[str, Any]] | None = None,
    marketing_html_draft: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Stream Chat/Work routing and an LLM-selected Work execution plan."""
    active_settings = settings or load_settings()
    contextual_request = build_contextual_request(request, conversation_history, marketing_html_draft)
    trace: list[TraceEvent] = []
    fast = decide(contextual_request, FAST_ROUTE_CANDIDATES, active_settings, min_margin=min_margin)
    yield {
        "type": "route",
        "trace_event": _append_trace(trace, "fast_route", {"selected": fast.selected, "scores": fast.scores, "margin": fast.margin, "engine": fast.engine, "low_confidence": fast.fallback}),
    }
    if fast.selected == "chat":
        yield {
            "type": "complete",
            "result": {"route": "chat", "specialist": None, "result": "대화형 요청입니다.", "trace": [item.as_dict() for item in trace]},
        }
        return

    results: dict[str, dict[str, Any]] = {}
    pipeline = _run_food_pipeline(contextual_request, results, active_settings, trace)
    plan: dict[str, Any] | None = None
    while True:
        try:
            event = next(pipeline)
        except StopIteration as stop:
            plan = stop.value
            break
        yield event
    if plan is None:
        raise RuntimeError("Orchestration Agent가 실행 계획을 반환하지 않았습니다.")
    final_agent_id = plan["final_agent_id"]
    evaluations: list[dict[str, Any]] = []
    evaluation_passed = False
    evaluation_limit_reached = False
    for loop_number in range(1, MAX_EVALUATION_LOOPS + 1):
        yield {
            "type": "evaluation_started",
            "trace_event": _append_trace(
                trace,
                "evaluation_started",
                {"loop": loop_number, "max_loops": MAX_EVALUATION_LOOPS, "label": "Evaluation Middleware"},
            ),
        }
        review = evaluate_workflow_execution(contextual_request, plan, results, active_settings)
        evaluation = {"loop": loop_number, **review}
        evaluations.append(evaluation)
        yield {
            "type": "evaluation_completed",
            "evaluation": evaluation,
            "trace_event": _append_trace(
                trace,
                "evaluation_completed",
                {
                    "loop": loop_number,
                    "max_loops": MAX_EVALUATION_LOOPS,
                    "verdict": review["verdict"],
                    "reason": review["reason"],
                    "revision_stages": review["revision_stages"],
                    "label": "Evaluation Middleware",
                },
            ),
        }
        if review["verdict"] == "pass":
            evaluation_passed = True
            break
        if loop_number == MAX_EVALUATION_LOOPS:
            evaluation_limit_reached = True
            yield {
                "type": "evaluation_limit_reached",
                "trace_event": _append_trace(
                    trace,
                    "evaluation_limit_reached",
                    {"loop": loop_number, "max_loops": MAX_EVALUATION_LOOPS, "label": "Evaluation Middleware"},
                ),
            }
            break
        yield {
            "type": "revision_started",
            "trace_event": _append_trace(
                trace,
                "revision_started",
                {
                    "loop": loop_number,
                    "max_loops": MAX_EVALUATION_LOOPS,
                    "label": "Evaluation Middleware",
                    "reason": review["reason"],
                    "stages": review["revision_stages"],
                },
            ),
        }
        yield from _run_revision_stages(
            contextual_request,
            plan,
            review["revision_stages"],
            results,
            active_settings,
            trace,
        )
    yield {
        "type": "complete",
        "result": {
            "route": "work",
            "specialist": "llm-orchestrated-food-team",
            "final_agent_id": final_agent_id,
            "result": results[final_agent_id]["answer"],
            "agent_results": results,
            "orchestration_plan": plan,
            "evaluation": {
                "max_loops": MAX_EVALUATION_LOOPS,
                "passed": evaluation_passed,
                "limit_reached": evaluation_limit_reached,
                "reviews": evaluations,
            },
            "trace": [item.as_dict() for item in trace],
        },
    }


def run_workflow(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
    conversation_history: list[dict[str, Any]] | None = None,
    marketing_html_draft: str | None = None,
) -> dict[str, Any]:
    """Collect the streamed LLM-orchestrated workflow result."""
    for event in run_workflow_stream(request, settings, min_margin, conversation_history, marketing_html_draft):
        if event["type"] == "complete":
            return event["result"]
    raise RuntimeError("Workflow가 최종 결과를 반환하지 않았습니다.")
