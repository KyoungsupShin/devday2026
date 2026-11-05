"""Independent Agent loop and Tool Calling runtime for ``02_agent_loop_mcp.ipynb``."""
from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from queue import Empty, Queue
from typing import Any

from .lesson_support.config import Settings, load_settings
from .lesson_support.models import TraceEvent

from .agents.registry import FOOD_AGENT_BY_ID, SYNTHESIS_AGENT_ID
from .context import (
    build_observed_request,
    observe_conversation_context,
)
from .food_agents import (
    evaluate_workflow_execution,
    list_food_agents,
    plan_work_agents,
    run_food_agent,
)
from .prompts import get_prompt
from .routing import FAST_ROUTE_CANDIDATES, decide

MAX_EVALUATION_LOOPS = 3
CLARIFICATION_REQUIRED_PROMPT = get_prompt("clarification_required")


def inspect_route(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
) -> dict[str, Any]:
    """Return only the Cohere route decision; never start an Agent.

    This is useful when comparing request phrasing in a lab without paying for
    planning, specialist, or observation LLM calls. It deliberately routes only
    the current request, so it cannot be biased by a raw prior transcript.
    """
    active_settings = settings or load_settings()
    decision = decide(request, FAST_ROUTE_CANDIDATES, active_settings, min_margin=min_margin)
    return {
        "selected": decision.selected,
        "scores": decision.scores,
        "margin": decision.margin,
        "engine": decision.engine,
        "low_confidence": decision.fallback,
        "review_required": decision.fallback,
    }


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


def _append_synthesis_stage(domain_plan: dict[str, Any]) -> dict[str, Any]:
    """Append the fixed terminal Agent that combines all selected expertise."""
    if domain_plan.get("final_agent_id") == SYNTHESIS_AGENT_ID:
        return domain_plan
    plan = deepcopy(domain_plan)
    plan["domain_final_agent_id"] = plan["final_agent_id"]
    plan["stages"].append(
        {
            "agent_ids": [SYNTHESIS_AGENT_ID],
            "objective": "선행 전문 Agent 결과를 종합해 현재 사용자 요청에 대한 최종 답변을 작성합니다.",
        }
    )
    plan["final_agent_id"] = SYNTHESIS_AGENT_ID
    return plan


def _run_food_pipeline(
    request: str,
    results: dict[str, dict[str, Any]],
    settings: Settings,
    trace: list[TraceEvent],
    *,
    sequential_agents: bool = False,
) -> Iterator[dict[str, Any]]:
    """Execute only the stages selected by the Orchestrator LLM.

    The normal runtime permits parallel Agent work inside a stage.  The
    educational stream can opt into sequential execution so a learner sees one
    complete Agent log before the next Agent begins.
    """
    orchestrator = FOOD_AGENT_BY_ID["work-planning"]
    yield {
        "type": "agent_started",
        "trace_event": _append_trace(trace, "agent_started", {"agent_id": orchestrator.id, "label": orchestrator.label}),
    }
    plan = _append_synthesis_stage(plan_work_agents(request, settings))
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
    if sequential_agents:
        for stage in plan["stages"]:
            for agent_id in stage["agent_ids"]:
                context = _agent_context(request, plan["brief"], results, completed_specialists, stage["objective"])
                agent = FOOD_AGENT_BY_ID[agent_id]
                yield {
                    "type": "agent_started",
                    "trace_event": _append_trace(trace, "agent_started", {"agent_id": agent.id, "label": agent.label}),
                }
                result = run_agent_with_stream(agent_id, context)
                results[agent_id] = result
                completed_specialists.append(agent_id)
                yield from drain_deltas()
                yield {
                    "type": "agent_completed",
                    "agent_result": result,
                    "trace_event": _completed_event(trace, result),
                }
        return plan

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
    *,
    sequential_agents: bool = False,
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
    if sequential_agents:
        for stage in revision_stages:
            for agent_id in stage["agent_ids"]:
                context = _agent_context(request, plan["brief"], results, completed_specialists, stage["objective"])
                agent = FOOD_AGENT_BY_ID[agent_id]
                yield {
                    "type": "agent_started",
                    "trace_event": _append_trace(trace, "agent_started", {"agent_id": agent.id, "label": agent.label, "rework": True}),
                }
                result = run_agent_with_stream(agent_id, context)
                results[agent_id] = result
                if agent_id not in completed_specialists:
                    completed_specialists.append(agent_id)
                yield from drain_deltas()
                yield {
                    "type": "agent_completed",
                    "agent_result": result,
                    "trace_event": _completed_event(trace, result),
                }
        return

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
    *,
    enable_evaluation: bool = False,
    sequential_agents: bool = False,
) -> Iterator[dict[str, Any]]:
    """Stream Chat/Work routing and an LLM-selected Work execution plan.

    The reusable runtime can stop after Synthesis or opt into the Evaluation
    Middleware. The 02 public entry point enables the bounded revision loop.
    """
    active_settings = settings or load_settings()
    trace: list[TraceEvent] = []
    observation = observe_conversation_context(
        request,
        conversation_history,
        marketing_html_draft,
        active_settings,
    )
    routing_request = request
    routing_uses_observation = observation["use_history"] and bool(observation["observation"])
    if routing_uses_observation:
        routing_request += f"\n\n[관련 대화 관찰]\n{observation['observation']}"
    contextual_request = build_observed_request(request, observation, marketing_html_draft)
    yield {
        "type": "conversation_observation",
        "observation": observation,
        "trace_event": _append_trace(
            trace,
            "conversation_observation",
            {
                "used_history": observation["use_history"],
                "routing_uses_observation": routing_uses_observation,
                "has_observation": bool(observation["observation"]),
                "external_data_needed": observation["external_data_needed"],
                "needs_work": observation.get("needs_work") is True,
            },
        ),
    }
    fast = decide(routing_request, FAST_ROUTE_CANDIDATES, active_settings, min_margin=min_margin)
    yield {
        "type": "route",
        "trace_event": _append_trace(trace, "fast_route", {"selected": fast.selected, "scores": fast.scores, "margin": fast.margin, "engine": fast.engine, "low_confidence": fast.fallback}),
    }
    if fast.fallback:
        yield {
            "type": "complete",
            "result": {
                "route": "clarify",
                "specialist": None,
                "result": CLARIFICATION_REQUIRED_PROMPT,
                "review_required": True,
                "route_decision": {
                    "selected": fast.selected,
                    "scores": fast.scores,
                    "margin": fast.margin,
                    "engine": fast.engine,
                    "low_confidence": True,
                },
                "conversation_observation": observation,
                "trace": [item.as_dict() for item in trace],
            },
        }
        return
    if fast.selected == "chat":
        yield {
            "type": "complete",
            "result": {
                "route": "chat",
                "specialist": None,
                "result": "대화형 요청입니다.",
                "conversation_observation": observation,
                "trace": [item.as_dict() for item in trace],
            },
        }
        return

    results: dict[str, dict[str, Any]] = {}
    pipeline = _run_food_pipeline(
        contextual_request,
        results,
        active_settings,
        trace,
        sequential_agents=sequential_agents,
    )
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
    if not enable_evaluation:
        yield {
            "type": "complete",
            "result": {
                "route": "work",
                "specialist": "llm-orchestrated-food-team",
                "final_agent_id": final_agent_id,
                "result": results[final_agent_id]["answer"],
                "agent_results": results,
                "orchestration_plan": plan,
                "evaluation": None,
                "review_required": False,
                "conversation_observation": observation,
                "trace": [item.as_dict() for item in trace],
            },
        }
        return

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
            sequential_agents=sequential_agents,
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
            "review_required": evaluation_limit_reached,
            "conversation_observation": observation,
            "trace": [item.as_dict() for item in trace],
        },
    }


def run_workflow(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
    conversation_history: list[dict[str, Any]] | None = None,
    marketing_html_draft: str | None = None,
    *,
    enable_evaluation: bool = False,
    sequential_agents: bool = False,
) -> dict[str, Any]:
    """Collect an LLM-orchestrated workflow result.

    Evaluation is opt-in so callers can use the core for a single Synthesis
    pass or for the bounded revision loop.
    """
    for event in run_workflow_stream(
        request,
        settings,
        min_margin,
        conversation_history,
        marketing_html_draft,
        enable_evaluation=enable_evaluation,
        sequential_agents=sequential_agents,
    ):
        if event["type"] == "complete":
            return event["result"]
    raise RuntimeError("Workflow가 최종 결과를 반환하지 않았습니다.")


def list_food_mcp_tools() -> list[dict[str, Any]]:
    """Expose this lesson's local, read-only Tool Calling contracts."""
    return [
        {
            "agent_id": agent["agent_id"],
            "agent_label": agent["agent_label"],
            "name": tool["name"],
            "type": tool["type"],
            "description": tool["description"],
            "write": False,
        }
        for agent in list_food_agents()
        for tool in agent["tools"]
    ]


def run_food_mcp_loop(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
) -> dict[str, Any]:
    """Run the local loop runtime and collect selected Tool Calling evidence."""
    outcome = run_workflow(
        request,
        settings,
        min_margin=min_margin,
        enable_evaluation=True,
    )
    selected_tools = [
        {"agent_id": agent_id, **call}
        for agent_id, result in outcome.get("agent_results", {}).items()
        for call in result.get("tool_calls", [])
    ]
    return {
        **outcome,
        "tool_calls": selected_tools,
        "execution_boundary": "local read-only Tool Calling inside the 02 Agent loop; no external write actions are available.",
    }


def run_food_mcp_loop_stream(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
    *,
    sequential_agents: bool = True,
) -> Iterator[dict[str, Any]]:
    """Yield the 02 loop events, optionally completing one Agent before the next.

    This public teaching API makes Agent-level starts, Tool Calling results, and
    evaluation revisions observable without copying runtime behavior into a
    notebook.  The default is deliberately sequential for readable lab logs.
    """
    for event in run_workflow_stream(
        request,
        settings,
        min_margin=min_margin,
        enable_evaluation=True,
        sequential_agents=sequential_agents,
    ):
        if event["type"] != "complete":
            yield event
            continue
        outcome = event["result"]
        selected_tools = [
            {"agent_id": agent_id, **call}
            for agent_id, result in outcome.get("agent_results", {}).items()
            for call in result.get("tool_calls", [])
        ]
        yield {
            **event,
            "result": {
                **outcome,
                "tool_calls": selected_tools,
                "execution_boundary": "local read-only Tool Calling inside the 02 Agent loop; no external write actions are available.",
            },
        }


def run_food_mcp_loop_steps(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
) -> Iterator[dict[str, Any]]:
    """Yield JSON-friendly teaching steps for the independent 02 Agent Loop.

    Each ``next()`` call advances one observable unit.  An Agent step contains
    its full sequential execution, including any local read-only Tool Calling
    evidence, so a notebook can pause between Agents and inspect its log.
    """
    event_stream = iter(
        run_food_mcp_loop_stream(
            request,
            settings,
            min_margin=min_margin,
            sequential_agents=True,
        )
    )
    for event in event_stream:
        event_type = event["type"]
        if event_type == "agent_started":
            agent_events = [event]
            for agent_event in event_stream:
                agent_events.append(agent_event)
                if agent_event["type"] != "agent_completed":
                    continue
                agent_result = agent_event["agent_result"]
                yield {
                    "step": "agent",
                    "agent_id": agent_result["agent_id"],
                    "agent_label": agent_result["agent_label"],
                    "rework": bool(event["trace_event"]["payload"].get("rework")),
                    "answer": agent_result["answer"],
                    "tool_calls": agent_result.get("tool_calls", []),
                    "deltas": [item["delta"] for item in agent_events if item["type"] == "agent_delta"],
                    "trace": [item["trace_event"] for item in agent_events if "trace_event" in item],
                }
                break
            else:
                raise RuntimeError("Agent 실행이 완료 이벤트 없이 끝났습니다.")
            continue
        if event_type == "conversation_observation":
            yield {"step": "observer", "observation": event["observation"], "trace": event["trace_event"]}
        elif event_type == "route":
            yield {"step": "route", "decision": event["trace_event"]["payload"], "trace": event["trace_event"]}
        elif event_type == "orchestration_plan":
            yield {"step": "plan", "plan": event["plan"], "trace": event["trace_event"]}
        elif event_type == "evaluation_started":
            yield {"step": "evaluation_started", "trace": event["trace_event"]}
        elif event_type == "evaluation_completed":
            yield {"step": "evaluation", "evaluation": event["evaluation"], "trace": event["trace_event"]}
        elif event_type == "revision_started":
            yield {"step": "revision", "trace": event["trace_event"]}
        elif event_type == "evaluation_limit_reached":
            yield {"step": "evaluation_limit", "trace": event["trace_event"]}
        elif event_type == "complete":
            yield {"step": "complete", "result": event["result"]}
