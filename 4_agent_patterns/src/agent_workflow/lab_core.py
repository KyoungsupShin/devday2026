"""Small public workflow API for ``01_agent_workflow.ipynb``."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from lab_common.ai_core import chat_text
from lab_common.config import Settings, load_settings
from lab_common.models import TraceEvent

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
        for agent_id in stage["agent_ids"]:
            agent = FOOD_AGENT_BY_ID[agent_id]
            yield {
                "type": "agent_started",
                "trace_event": _append_trace(trace, "agent_started", {"agent_id": agent.id, "label": agent.label}),
            }
            deltas: list[str] = []
            result = run_food_agent(
                agent_id,
                _agent_request(request, plan["brief"], stage["objective"], results),
                active_settings,
                on_delta=deltas.append,
            )
            for delta in deltas:
                yield {"type": "agent_delta", "agent_id": agent_id, "delta": delta}
            results[agent_id] = result
            yield {
                "type": "agent_completed",
                "agent_result": result,
                "trace_event": _append_trace(trace, "agent_completed", {"agent_id": agent.id, "label": agent.label}),
            }

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
    stream = iter(run_workflow_stream(request, settings, min_margin, conversation_history))
    for event in stream:
        if event["type"] == "orchestration_plan":
            yield {"step": "plan", "plan": event["plan"], "trace": event["trace_event"]}
        elif event["type"] == "route":
            yield {"step": "route", "decision": event["trace_event"]["payload"], "trace": event["trace_event"]}
        elif event["type"] == "agent_started":
            agent_events = [event]
            for agent_event in stream:
                agent_events.append(agent_event)
                if agent_event["type"] != "agent_completed":
                    continue
                result = agent_event["agent_result"]
                yield {
                    "step": "agent",
                    "agent_id": result["agent_id"],
                    "agent_label": result["agent_label"],
                    "answer": result["answer"],
                    "deltas": [item["delta"] for item in agent_events if item["type"] == "agent_delta"],
                    "trace": [item["trace_event"] for item in agent_events if "trace_event" in item],
                }
                break
        elif event["type"] == "complete":
            yield {"step": "complete", "result": event["result"]}
