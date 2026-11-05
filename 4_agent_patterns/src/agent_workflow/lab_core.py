"""Small public workflow API for ``01_agent_workflow.ipynb``."""
from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import Any

from .lesson_support.llm import chat_text
from .lesson_support.config import Settings, load_settings
from .lesson_support.models import TraceEvent

from .agents.registry import FOOD_AGENT_BY_ID
from .food_agents import plan_work_agents, run_food_agent
from .prompts import get_prompt
from .routing import FAST_ROUTE_CANDIDATES, decide

CLARIFICATION_REQUIRED_PROMPT = get_prompt("clarification_required")


def inspect_route(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
) -> dict[str, Any]:
    """Return the Cohere Rerank route without starting an Agent."""
    decision = decide(request, FAST_ROUTE_CANDIDATES, settings or load_settings(), min_margin=min_margin)
    return {
        "selected": decision.selected,
        "scores": decision.scores,
        "margin": decision.margin,
        "engine": decision.engine,
        "low_confidence": decision.fallback,
    }


def _append_trace(trace: list[TraceEvent], event: str, payload: dict[str, Any]) -> dict[str, Any]:
    item = TraceEvent(len(trace) + 1, event, payload)
    trace.append(item)
    return item.as_dict()


def _agent_request(
    request: str,
    brief: str,
    stage_objective: str,
    results: dict[str, dict[str, str]],
) -> str:
    prior_answers = "\n\n".join(
        f"[{result['agent_label']} 결과]\n{result['answer']}"
        for result in results.values()
    )
    sections = [
        f"[사용자 요청]\n{request}",
        f"[공통 브리프]\n{brief}",
        f"[현재 단계 목표]\n{stage_objective}",
    ]
    if prior_answers:
        sections.append(f"[선행 Agent 결과]\n{prior_answers}")
    return "\n\n".join(sections)


def _run_stage_agent(
    agent_id: str,
    request: str,
    brief: str,
    objective: str,
    prior_results: dict[str, dict[str, str]],
    settings: Settings,
    events: Queue[tuple[str, str, Any]],
) -> None:
    """Run one blocking specialist call and relay its stream to the main generator."""

    def on_delta(delta: str) -> None:
        events.put(("agent_delta", agent_id, delta))

    try:
        result = run_food_agent(
            agent_id,
            _agent_request(request, brief, objective, prior_results),
            settings,
            on_delta=on_delta,
        )
    except Exception as error:  # noqa: BLE001 - relay any SDK failure to the main stream
        events.put(("agent_error", agent_id, error))
    else:
        events.put(("agent_completed", agent_id, result))


def run_workflow_stream(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
    conversation_history: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    """Route with Cohere Rerank, then stream an LLM-authored work plan."""
    active_settings = settings or load_settings()
    trace: list[TraceEvent] = []
    route = decide(request, FAST_ROUTE_CANDIDATES, active_settings, min_margin=min_margin)
    yield {
        "type": "route",
        "trace_event": _append_trace(
            trace,
            "fast_route",
            {"selected": route.selected, "scores": route.scores, "margin": route.margin, "engine": route.engine, "low_confidence": route.fallback},
        ),
    }
    if route.fallback:
        yield {
            "type": "complete",
            "result": {
                "route": "clarify",
                "result": CLARIFICATION_REQUIRED_PROMPT,
                "trace": [item.as_dict() for item in trace],
            },
        }
        return
    if route.selected == "chat":
        messages = [{"role": "system", "content": get_prompt("chat_final_reply")}]
        messages.extend(
            {"role": item["role"], "content": item["content"]}
            for item in conversation_history or []
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str)
        )
        messages.append({"role": "user", "content": request})
        yield {
            "type": "complete",
            "result": {"route": "chat", "result": chat_text(active_settings, messages), "trace": [item.as_dict() for item in trace]},
        }
        return
    plan = plan_work_agents(request, active_settings, conversation_history)
    yield {
        "type": "orchestration_plan",
        "plan": plan,
        "trace_event": _append_trace(
            trace,
            "orchestration_plan",
            {"stages": plan["stages"], "final_agent_id": plan["final_agent_id"]},
        ),
    }

    results: dict[str, dict[str, str]] = {}
    for stage in plan["stages"]:
        stage_agent_ids = list(stage["agent_ids"])
        # A stage is the workflow's dependency boundary. Every Agent in it gets
        # the same immutable snapshot of prior-stage results, so no Agent waits
        # for a peer in the same stage. This lets independent specialists call
        # the blocking LLM SDK concurrently while retaining a synchronous
        # streaming API for the notebook and Gradio UI.
        prior_results = dict(results)
        stage_events: Queue[tuple[str, str, Any]] = Queue()
        stage_results: dict[str, dict[str, str]] = {}

        # Emit every start state before dispatching any work so the UI immediately
        # presents all independent specialists as running.
        for agent_id in stage_agent_ids:
            agent = FOOD_AGENT_BY_ID[agent_id]
            yield {
                "type": "agent_started",
                "trace_event": _append_trace(trace, "agent_started", {"agent_id": agent.id, "label": agent.label}),
            }

        failures: list[Exception] = []
        with ThreadPoolExecutor(
            max_workers=len(stage_agent_ids), thread_name_prefix="workflow-agent"
        ) as executor:
            for agent_id in stage_agent_ids:
                executor.submit(
                    _run_stage_agent,
                    agent_id,
                    request,
                    plan["brief"],
                    stage["objective"],
                    prior_results,
                    active_settings,
                    stage_events,
                )

            remaining = len(stage_agent_ids)
            while remaining:
                event_type, agent_id, payload = stage_events.get()
                if event_type == "agent_delta":
                    yield {"type": "agent_delta", "agent_id": agent_id, "delta": payload}
                    continue
                remaining -= 1
                if event_type == "agent_error":
                    failures.append(payload)
                    continue
                result = payload
                stage_results[agent_id] = result
                agent = FOOD_AGENT_BY_ID[agent_id]
                yield {
                    "type": "agent_completed",
                    "agent_result": result,
                    "trace_event": _append_trace(trace, "agent_completed", {"agent_id": agent.id, "label": agent.label}),
                }

        if failures:
            raise failures[0]
        # Keep downstream prompt ordering stable even though same-stage Agents
        # complete in nondeterministic order.
        for agent_id in stage_agent_ids:
            results[agent_id] = stage_results[agent_id]

    final_agent_id = plan["final_agent_id"]
    yield {
        "type": "complete",
        "result": {
            "route": "work",
            "final_agent_id": final_agent_id,
            "result": results[final_agent_id]["answer"],
            "agent_results": results,
            "orchestration_plan": plan,
            "trace": [item.as_dict() for item in trace],
        },
    }


def run_workflow(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the final result of an LLM-orchestrated workflow."""
    for event in run_workflow_stream(request, settings, min_margin, conversation_history):
        if event["type"] == "complete":
            return event["result"]
    raise RuntimeError("Workflow가 최종 결과를 반환하지 않았습니다.")


def run_workflow_steps(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
    conversation_history: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one plan or one completed Agent execution at a time for the notebook."""
    active_agents: dict[str, list[dict[str, Any]]] = {}
    for event in run_workflow_stream(request, settings, min_margin, conversation_history):
        if event["type"] == "orchestration_plan":
            yield {"step": "plan", "plan": event["plan"], "trace": event["trace_event"]}
        elif event["type"] == "route":
            yield {"step": "route", "decision": event["trace_event"]["payload"], "trace": event["trace_event"]}
        elif event["type"] == "agent_started":
            agent_id = event["trace_event"]["payload"]["agent_id"]
            active_agents[agent_id] = [event]
        elif event["type"] == "agent_delta":
            active_agents.setdefault(event["agent_id"], []).append(event)
        elif event["type"] == "agent_completed":
            result = event["agent_result"]
            agent_events = active_agents.pop(result["agent_id"], []) + [event]
            yield {
                "step": "agent",
                "agent_id": result["agent_id"],
                "agent_label": result["agent_label"],
                "answer": result["answer"],
                "deltas": [item["delta"] for item in agent_events if item["type"] == "agent_delta"],
                "trace": [item["trace_event"] for item in agent_events if "trace_event" in item],
            }
        elif event["type"] == "complete":
            yield {"step": "complete", "result": event["result"]}
