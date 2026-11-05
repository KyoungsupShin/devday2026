#!/usr/bin/env python3
"""
parse-trace.py  Extract the mechanical facts a fix operation needs from evidence JSON.

Deterministic owns the facts; the LLM owns the reasoning. This script never diagnoses —
it reports traceStatus, tool-call outcomes, whether a final answer exists, and the Gate-C
`gradeable` signal, so the fix operation starts from facts instead of a hand-read of a large
JSON structure.

Inputs (all JSON — the backend's machine contract):
  <traces.json>     one getRunTraces-shaped run bundle (run + failedScenarios[] inline, each a
                    full scenario trace with conversation.turns) — the `get_traces` payload
  <scenario.json>   one getScenarioTrace-shaped trace (has conversation.turns)
  -                 read a single payload from stdin (inline getScenarioTrace)

Usage:
    python3 scripts/parse-trace.py <traces.json | scenario.json | ->

Exit codes:
    0  parsed, output written to stdout
    1  could not parse (invalid JSON / unexpected shape)
    2  could not run (missing argument, file/dir not found, other OS error)
"""

import json
import os
import sys


def _str(v):
    return "" if v is None else str(v)


def _tool_result_outcome(turn):
    """Outcome of a tool_result turn: ('success'|'failure'|'empty', detail)."""
    status = _str(turn.get("status")).strip().lower()
    error = _str(turn.get("error")).strip()
    if status == "failure" or error:
        return "failure", error or status or "failure"
    if not _str(turn.get("toolResult")).strip():
        return "empty", ""
    return "success", ""


def _analyse(turns):
    """Facts about one conversation's turns. Keyed on the real `kind` taxonomy."""
    calls = 0
    results = []          # (turn_num, outcome, detail, toolName)
    assistant_turns = 0
    final_num = None

    for i, turn in enumerate(turns):
        kind = _str(turn.get("kind")).strip().lower()
        if kind == "tool_call":
            calls += 1
        elif kind == "tool_result":
            outcome, detail = _tool_result_outcome(turn)
            results.append((i + 1, outcome, detail, _str(turn.get("toolName"))))
        elif kind == "assistant":
            if _str(turn.get("content")).strip():
                assistant_turns += 1
                final_num = i + 1

    # A tool_call with no matching tool_result is an unterminated call — a likely task-layer
    # hang (the AgentTimeoutError class), a distinct and strong no-output signal.
    orphan_calls = calls - len(results)

    return {
        "total": len(turns),
        "calls": calls,
        "results": results,
        "assistant_turns": assistant_turns,
        "orphan_calls": orphan_calls,
        "final_num": final_num,
    }


def _fmt_results(results):
    if not results:
        return "none"
    parts = []
    for num, outcome, detail, tool in results:
        s = f"turn {num}: {outcome}"
        if detail:
            s += f" ({detail})"
        if tool:
            s += f" [{tool}]"
        parts.append(s)
    return "  ".join(parts)


def _gradeable(trace_status, a):
    """The Gate-C signal. Distinguishes 'no runtime evidence' from 'agent produced no gradeable
    output' — the first is weak evidence, the second is the Gate-C agent-bug trigger."""
    if trace_status != "AVAILABLE":
        return f"n/a — trace {trace_status} (no runtime evidence)"
    reasons = []
    bad = [r for r in a["results"] if r[1] != "success"]
    for num, outcome, _detail, _tool in bad:
        reasons.append(
            f"tool result {'failed' if outcome == 'failure' else 'empty'} at turn {num}"
        )
    if a["orphan_calls"] > 0:
        reasons.append(f"{a['orphan_calls']} tool call(s) had no result (possible hang)")
    if a["final_num"] is None:
        reasons.append("no final agent output")
    return "YES" if not reasons else "NO — " + "; ".join(reasons)


def _scenario_block(name, trace_status, truncated, turns, indent=""):
    lines = [f"{indent}scenario      {name}"] if name is not None else []
    lines.append(f"{indent}traceStatus   {trace_status}")

    if turns is None:
        # No file / non-AVAILABLE: nothing to analyse, but say why plainly.
        lines.append(f"{indent}gradeable     {_gradeable(trace_status, None)}")
        return lines

    a = _analyse(turns)
    lines.append(f"{indent}truncated     {'true' if truncated else 'false'}")
    lines.append(
        f"{indent}turns         {a['total']} total — "
        f"{a['calls']} call / {len(a['results'])} result / {a['assistant_turns']} agent"
    )
    lines.append(f"{indent}tool_results  {_fmt_results(a['results'])}")
    lines.append(
        f"{indent}final_output  "
        + (f"present (turn {a['final_num']})" if a["final_num"] else "absent")
    )
    lines.append(f"{indent}gradeable     {_gradeable(trace_status, a)}")
    return lines


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _process_scenario(trace):
    turns = (trace.get("conversation") or {}).get("turns")
    name = (trace.get("scenario") or {}).get("name") or trace.get("conversationId") or "(unnamed)"
    trace_status = trace.get("traceStatus", "UNKNOWN")
    # AVAILABLE but turns somehow absent → treat as no turns.
    turns = turns if isinstance(turns, list) else None
    if trace_status == "AVAILABLE" and turns is None:
        turns = []
    return _scenario_block(name, trace_status, trace.get("truncated", False), turns)


def _process_run(manifest):
    """The whole run as returned INLINE by getRunTraces: run summary, passingScenarios, and
    failedScenarios[] where each entry is a full scenario trace (scenario, traceStatus,
    truncated, conversation.turns) — no sibling files, nothing to read off disk."""
    run = manifest.get("run") or {}
    failed = manifest.get("failedScenarios") or []
    passing = manifest.get("passingScenarios") or []

    header = []
    if manifest.get("executionId"):
        header.append(f"executionId   {manifest['executionId']}")
    if run.get("iterations") is not None:
        header.append(f"iterations    {run['iterations']}")
    header.append(f"passing       {len(passing)} scenario(s)")
    header.append(f"failing       {len(failed)} scenario(s)")

    avail = pend = unavail = trunc = 0
    blocks = []
    for s in failed:
        trace_status = s.get("traceStatus", "UNKNOWN")
        name = (s.get("scenario") or {}).get("name") or s.get("conversationId") or "(unnamed)"
        if trace_status == "AVAILABLE":
            avail += 1
        elif trace_status == "PENDING":
            pend += 1
        elif trace_status == "UNAVAILABLE":
            unavail += 1

        # Turns are inline on each failed scenario, but only meaningful for AVAILABLE. A
        # PENDING/UNAVAILABLE scenario carries no runtime evidence → pass None for the short
        # "traceStatus + gradeable" block, same as before.
        if trace_status == "AVAILABLE":
            turns = (s.get("conversation") or {}).get("turns")
            turns = turns if isinstance(turns, list) else []
        else:
            turns = None
        truncated = bool(s.get("truncated", False))
        if truncated:
            trunc += 1

        blocks.append("")
        blocks.extend(_scenario_block(name, trace_status, truncated, turns, indent="  "))

    qa = f"trace_qa      available {avail}  pending {pend}  unavailable {unavail}  truncated {trunc}"
    return header + ["", qa] + blocks


def main():
    if len(sys.argv) < 2:
        print("usage: parse-trace.py <traces.json | scenario.json | ->", file=sys.stderr)
        sys.exit(2)

    arg = sys.argv[1]

    try:
        if arg == "-":
            payload = json.load(sys.stdin)
        elif os.path.isfile(arg):
            payload = _load(arg)
        else:
            print(f"error: not found: {arg}", file=sys.stderr)
            sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        if isinstance(payload, dict) and "failedScenarios" in payload:
            lines = _process_run(payload)
        elif isinstance(payload, dict) and "conversation" in payload:
            lines = _process_scenario(payload)
        else:
            print("error: unrecognised payload — expected a run bundle or a scenario trace", file=sys.stderr)
            sys.exit(1)
    except (KeyError, TypeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n".join(lines))


if __name__ == "__main__":
    main()
