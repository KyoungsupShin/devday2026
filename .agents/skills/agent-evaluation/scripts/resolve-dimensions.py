#!/usr/bin/env python3
"""resolve-dimensions.py — deterministically resolve the enabled dimension set for a run.

Usage:
    python3 skills/agent-evaluation/scripts/resolve-dimensions.py [FLAGS] [--out <path>]

Reads the dimension registry (skills/agent-evaluation/dimensions.json) and emits the set of
dimension keys the generator is permitted to produce for THIS run, as {"enabled": [...]}.
The generator supplies run-context flags (its own semantic judgments about the agent); this
script applies the gates deterministically so a disabled dimension can never slip through:

    enabled = aicore_supported AND (requires_ground_truth ? grounding_present : true) AND applies_when

aicore_supported is a hard gate: a dimension with aicore_supported=false (safety, stability,
performance, uiux today) is NEVER enabled, whatever flags are passed. That is the point — the
model cannot talk a forbidden category back on.

Context flags (all default off; presence turns them on):
    --grounding-present        customer-seeded grounding has been access-verified
    --qualifying-metrics       at least one business metric carries a committed target
    --stateful                 the agent carries conversation state across turns
    --summarizes               the agent produces summaries
    --has-retrieval            the agent uses document grounding / RAG
    --grounding-forbidden-ops  the grounding data declares a forbidden operation
    --orchestrator             the agent is a routing orchestrator

Writes {"enabled":[...]} to --out (default: stdout). A one-line resolution summary goes to
stderr. Zero dependencies beyond the stdlib. Exit 0 on success, 2 on bad input.
"""
import json
import os
import sys

FLAG_NAMES = {
    "--grounding-present": "grounding_present",
    "--qualifying-metrics": "qualifying_metrics",
    "--stateful": "stateful",
    "--summarizes": "summarizes",
    "--has-retrieval": "has_retrieval",
    "--grounding-forbidden-ops": "grounding_forbidden_ops",
    "--orchestrator": "orchestrator",
}

USAGE = (
    "usage: resolve-dimensions.py "
    "[--grounding-present] [--qualifying-metrics] [--stateful] [--summarizes] "
    "[--has-retrieval] [--grounding-forbidden-ops] [--orchestrator] [--out <path>]\n"
)


def die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def load_dimensions():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dimensions.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        die("cannot run: dimensions.json not found at {}".format(path))
    except ValueError as e:
        die("cannot run: dimensions.json is not valid JSON -- {}".format(e))
    dims = data.get("dimensions", []) if isinstance(data, dict) else []
    if not dims:
        die("cannot run: dimensions.json has no 'dimensions'")
    return dims


def main():
    flags = {v: False for v in FLAG_NAMES.values()}
    out = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a in FLAG_NAMES:
            flags[FLAG_NAMES[a]] = True
            i += 1
        elif a == "--out":
            if i + 1 >= len(args):
                die(USAGE)
            out = args[i + 1]
            i += 2
        else:
            die(USAGE)

    applies = {
        "always": True,
        "qualifying_metric_present": flags["qualifying_metrics"],
        "agent_stateful": flags["stateful"],
        "agent_summarizes": flags["summarizes"],
        "agent_has_retrieval": flags["has_retrieval"],
        "grounding_declares_forbidden_ops": flags["grounding_forbidden_ops"],
        "architecture_orchestrator": flags["orchestrator"],
    }

    enabled, off = [], []
    for d in load_dimensions():
        key = d["key"]
        if not d.get("aicore_supported", False):
            off.append((key, "aicore_supported=false"))
            continue
        if d.get("requires_ground_truth", False) and not flags["grounding_present"]:
            off.append((key, "needs grounding"))
            continue
        aw = d.get("applies_when", "always")
        if not applies.get(aw, False):
            off.append((key, "applies_when={} not met".format(aw)))
            continue
        enabled.append(key)

    payload = {"enabled": enabled}
    text = json.dumps(payload, indent=2) + "\n"
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        sys.stderr.write("wrote enabled set to {}\n".format(out))
    else:
        sys.stdout.write(text)

    sys.stderr.write("enabled: {}\n".format(", ".join(enabled) if enabled else "(none)"))
    sys.stderr.write("off: {}\n".format(", ".join("{} ({})".format(k, r) for k, r in off)))


if __name__ == "__main__":
    main()
