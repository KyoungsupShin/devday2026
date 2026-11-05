#!/usr/bin/env python3
"""extract-tool-catalog.py — read mcp-mock.json and emit a redacted tool catalog.

Usage:
    python3 skills/agent-evaluation/scripts/extract-tool-catalog.py <mcp-mock.json> [--out <path>]

The generator needs three things from mcp-mock.json: tool NAMES (so expected_tool_calls can
name real tools), DESCRIPTIONS (to decide when a tool is called), and INPUT_SCHEMA (parameter
names + the realistic input identifiers the simulated user hands the agent). It does NOT need
the mock_response PAYLOAD VALUES — out-of-the-box every output assertion is "in kind" and under
grounding the real values come from the grounding file, never the mock. Yet feeding the raw
mock_response into the model's context is exactly what makes it pin invented values
(SUPPLIER-001, 45000.00) into test cases ~1-in-10 runs, despite the prose telling it not to.

This script removes the poison at the source: it reads mcp-mock.json and prints the same
catalog shape with every mock_response reduced to a TYPE SKELETON — field names and structure
preserved, every leaf value replaced by a <type> placeholder. The model keeps the real field
names (so an in-kind output check can say "carrying a supplier and a net order value") but can
never see, and so can never pin, an invented value.

Two consumers, two views: the aeval RUNTIME still reads the full mcp-mock.json (it needs the
payloads to return deterministic tool responses); the GENERATOR reads only this redacted view.

Writes the redacted catalog JSON to --out (default: stdout). A one-line summary goes to stderr.
Zero dependencies beyond the stdlib. Exit 0 on success, 2 on bad input.
"""
import json
import sys

USAGE = "usage: extract-tool-catalog.py <mcp-mock.json> [--out <path>]\n"


def die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def skeleton(value):
    """Reduce a mock_response value to field names + types, stripping all data.

    dict  -> same keys, each value recursively reduced
    list  -> at most one skeleton element (collapses N items to one shape)
    scalar-> a "<type>" placeholder, never the value itself
    """
    if isinstance(value, dict):
        return {k: skeleton(v) for k, v in value.items()}
    if isinstance(value, list):
        return [skeleton(value[0])] if value else []
    if isinstance(value, bool):
        return "<boolean>"
    if isinstance(value, int):
        return "<integer>"
    if isinstance(value, float):
        return "<number>"
    if value is None:
        return "<null>"
    return "<string>"


def main():
    args = sys.argv[1:]
    src = None
    out = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--out":
            if i + 1 >= len(args):
                die(USAGE)
            out = args[i + 1]
            i += 2
        elif a.startswith("--"):
            die(USAGE)
        elif src is None:
            src = a
            i += 1
        else:
            die(USAGE)
    if src is None:
        die(USAGE)

    try:
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        die("cannot read mcp-mock.json at {}".format(src))
    except ValueError as e:
        die("mcp-mock.json is not valid JSON -- {}".format(e))

    if not isinstance(data, dict) or not isinstance(data.get("servers"), dict):
        die("mcp-mock.json has no 'servers' object -- not the expected shape")

    n_tools = 0
    n_servers = 0
    n_redacted = 0
    for server in data["servers"].values():
        if not isinstance(server, dict):
            continue
        n_servers += 1
        tools = server.get("tools")
        if not isinstance(tools, dict):
            continue
        for tool in tools.values():
            if not isinstance(tool, dict):
                continue
            n_tools += 1
            if "mock_response" in tool:
                tool["mock_response"] = skeleton(tool["mock_response"])
                n_redacted += 1

    text = json.dumps(data, indent=2) + "\n"
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        sys.stderr.write("wrote redacted catalog to {}\n".format(out))
    else:
        sys.stdout.write(text)

    sys.stderr.write(
        "redacted {} tools across {} servers; stripped mock_response values "
        "on {} (kept field names + types)\n".format(n_tools, n_servers, n_redacted)
    )


if __name__ == "__main__":
    main()
