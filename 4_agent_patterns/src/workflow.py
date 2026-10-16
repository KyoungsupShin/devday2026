"""Food-product launch workflow with streamed, dependency-aware agent results."""
from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from queue import Empty, Queue
from typing import Any

from lab_common.config import Settings, load_settings
from lab_common.models import TraceEvent

from .food_agents import FOOD_AGENT_BY_ID, run_food_agent
from .routing import FAST_ROUTE_CANDIDATES, decide


def _append_trace(trace: list[TraceEvent], event: str, payload: dict[str, Any]) -> dict[str, Any]:
    item = TraceEvent(len(trace) + 1, event, payload)
    trace.append(item)
    return item.as_dict()


def _agent_context(request: str, results: dict[str, dict[str, str]], dependencies: tuple[str, ...]) -> str:
    if not dependencies:
        return request
    upstream = "\n\n".join(
        f"[{results[agent_id]['agent_label']} 결과]\n{results[agent_id]['answer']}"
        for agent_id in dependencies
    )
    return f"{request}\n\n아래 선행 Agent 결과를 근거로 사용하세요. 충돌하거나 누락된 정보는 가정으로 표시하세요.\n{upstream}"


FOOD_AGENT_DEPENDENCIES = {
    "work-planning": (),
    "food-rnd": ("work-planning",),
    "marketing": ("work-planning",),
    "procurement": ("work-planning", "food-rnd"),
    "quality-assurance": ("work-planning", "food-rnd"),
    "finance": ("work-planning", "food-rnd", "procurement"),
}


def _run_food_pipeline(
    request: str,
    results: dict[str, dict[str, str]],
    settings: Settings,
    trace: list[TraceEvent],
) -> Iterator[dict[str, Any]]:
    """Execute the dependency DAG and forward each parallel Agent's LLM text deltas."""
    pending = list(FOOD_AGENT_DEPENDENCIES)
    futures: dict[Any, str] = {}
    deltas: Queue[tuple[str, str]] = Queue()

    def run_agent_with_stream(agent_id: str, context: str) -> dict[str, str]:
        return run_food_agent(
            agent_id,
            context,
            settings,
            on_delta=lambda text: deltas.put((agent_id, text)),
        )

    def drain_deltas() -> Iterator[dict[str, Any]]:
        while True:
            try:
                agent_id, text = deltas.get_nowait()
            except Empty:
                return
            yield {"type": "agent_delta", "agent_id": agent_id, "delta": text}

    with ThreadPoolExecutor(max_workers=3) as executor:
        while pending or futures:
            ready = [
                agent_id
                for agent_id in pending
                if all(dependency in results for dependency in FOOD_AGENT_DEPENDENCIES[agent_id])
            ]
            for agent_id in ready:
                pending.remove(agent_id)
                agent = FOOD_AGENT_BY_ID[agent_id]
                context = _agent_context(request, results, FOOD_AGENT_DEPENDENCIES[agent_id])
                futures[executor.submit(run_agent_with_stream, agent_id, context)] = agent_id
                yield {
                    "type": "agent_started",
                    "trace_event": _append_trace(trace, "agent_started", {"agent_id": agent_id, "label": agent.label}),
                }
            if not futures:
                raise RuntimeError("Food Agent 의존성을 만족하는 실행 경로를 찾지 못했습니다.")
            completed, _ = wait(futures, timeout=0.05, return_when=FIRST_COMPLETED)
            yield from drain_deltas()
            for future in completed:
                agent_id = futures.pop(future)
                result = future.result()
                results[agent_id] = result
                yield from drain_deltas()
                yield {
                    "type": "agent_completed",
                    "agent_result": result,
                    "trace_event": _append_trace(
                        trace,
                        "agent_completed",
                        {
                            "agent_id": agent_id,
                            "label": result["agent_label"],
                            "status": "completed",
                            # This is intentionally only the local, read-only Tool
                            # Calling audit data.  It lets presentation adapters show
                            # how a completed specialist reached its response without
                            # exposing a second, standalone tool-loop runtime.
                            "tool_calls": result.get("tool_calls", []),
                        },
                    ),
                }


def run_workflow_stream(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
) -> Iterator[dict[str, Any]]:
    """Stream route and each food-agent result as soon as it is available.

    Work requests run this dependency graph:
    Work Planning Agents (Orchestrator) → [Food R&D, Marketing] →
    [Procurement, Quality Assurance] → Finance.
    """
    active_settings = settings or load_settings()
    trace: list[TraceEvent] = []
    fast = decide(request, FAST_ROUTE_CANDIDATES, active_settings, min_margin=min_margin)
    yield {
        "type": "route",
        "trace_event": _append_trace(
            trace,
            "fast_route",
            {
                "selected": fast.selected,
                "scores": fast.scores,
                "margin": fast.margin,
                "engine": fast.engine,
                "low_confidence": fast.fallback,
            },
        ),
    }
    if fast.selected == "chat":
        yield {
            "type": "complete",
            "result": {
                "route": "chat",
                "specialist": None,
                "result": "대화형 요청입니다.",
                "trace": [item.as_dict() for item in trace],
            },
        }
        return

    results: dict[str, dict[str, str]] = {}
    yield from _run_food_pipeline(request, results, active_settings, trace)
    yield {
        "type": "complete",
        "result": {
            "route": "work",
            "specialist": "food-product-launch-team",
            "result": results["finance"]["answer"],
            "agent_results": results,
            "trace": [item.as_dict() for item in trace],
        },
    }


def run_workflow(
    request: str,
    settings: Settings | None = None,
    min_margin: float = 0.0,
) -> dict[str, Any]:
    """Compatibility entry point that collects the streamed workflow result."""
    for event in run_workflow_stream(request, settings, min_margin):
        if event["type"] == "complete":
            return event["result"]
    raise RuntimeError("Workflow가 최종 결과를 반환하지 않았습니다.")
