#!/usr/bin/env python3
"""validateschema.py — structural validator for a v0 aeval test case file.

Usage:
    python3 skills/agent-evaluation/scripts/validateschema.py <path-to-testcase.yaml>

Exit 0  -> valid.
Exit 1  -> invalid; prints one note per line to stderr (path: expected, got).
Exit 2  -> could not run (file missing, YAML parse error, bad usage).

This is the executable mirror of the "Test cases" section of references/schemas.md.
schemas.md is the source of truth; this enforces its mechanical rules, tightened with
what the frozen real v0 JSON schema makes precise. Never loosen a rule to resolve a
divergence -- fix the script to match schemas.md.

Depends only on PyYAML (pyyaml), which is available in the runtime. No npm, no network.
The 000_pre_setup / zzz_post_teardown templates are static and NOT validated here.
"""

import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("cannot run: PyYAML (pyyaml) is not available\n")
    sys.exit(2)


def _load_dimensions():
    """Load the dimension registry (skills/agent-evaluation/dimensions.json).

    This is the single source of truth for the dimension vocabulary and the
    id-category -> tag mapping; the sets below are derived from it so the manifest
    and this script can never drift. See EVAL_GENERATION_REFRAME_IDEAS.md.
    """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dimensions.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        sys.stderr.write("cannot run: dimensions.json not found at {}\n".format(path))
        sys.exit(2)
    except ValueError as e:
        sys.stderr.write("cannot run: dimensions.json is not valid JSON -- {}\n".format(e))
        sys.exit(2)
    dims = data.get("dimensions", []) if isinstance(data, dict) else []
    if not dims:
        sys.stderr.write("cannot run: dimensions.json has no 'dimensions'\n")
        sys.exit(2)
    return dims


_DIMENSIONS = _load_dimensions()

DIMENSION_TAGS = {d["tag"] for d in _DIMENSIONS}

# id-category token (PascalCase) -> the dimension tag it must match.
CATEGORY_TO_TAG = {d["category"]: d["tag"] for d in _DIMENSIONS}

# id-category token -> the registry dimension key (what the enabled-set gate checks).
CATEGORY_TO_KEY = {d["category"]: d["key"] for d in _DIMENSIONS}

ID_TAG_RE = re.compile(r"^[a-zA-Z0-9_]+$")

notes = []


def fail(at, msg):
    notes.append("{}: {}".format(at, msg))


def is_mapping(v):
    return isinstance(v, dict)


def is_int(v):
    # bool is a subclass of int in Python; max_turns must be a real integer.
    return isinstance(v, int) and not isinstance(v, bool)


def reject_unknown_keys(obj, allowed, at):
    for k in obj.keys():
        if k not in allowed:
            fail(at, 'unknown key "{}" (not permitted by the v0 test-case schema)'.format(k))


def check_value_or_check(obj, at):
    if not is_mapping(obj):
        fail(at, "expected an object with exactly one of value|check")
        return
    reject_unknown_keys(obj, {"value", "check"}, at)
    has_value = "value" in obj and obj["value"] is not None
    has_check = "check" in obj and obj["check"] is not None
    if has_value and has_check:
        fail(at, "has both value and check -- supply exactly one")
    if not has_value and not has_check:
        fail(at, "has neither value nor check -- supply exactly one")
    if has_check and not isinstance(obj["check"], str):
        fail(at + ".check", "must be a string")


def check_check_list(lst, at):
    if not isinstance(lst, list):
        fail(at, "must be a list")
        return 0
    for i, item in enumerate(lst):
        p = "{}[{}]".format(at, i)
        if not is_mapping(item):
            fail(p, "must be an object { check: string }")
            continue
        reject_unknown_keys(item, {"check"}, p)
        if not isinstance(item.get("check"), str):
            fail(p + ".check", "must be a string")
    return len(lst)


def check_structured_message(msg, at):
    # v0 StructuredMessage: { parts: (TextPart|DataPart)[] }, minItems 1, no custom_headers (v1).
    reject_unknown_keys(msg, {"parts"}, at)
    parts = msg.get("parts")
    if not isinstance(parts, list) or len(parts) < 1:
        fail(at + ".parts", "must be a non-empty list")
        return
    for i, part in enumerate(parts):
        p = "{}.parts[{}]".format(at, i)
        if not is_mapping(part):
            fail(p, "must be an object with exactly one of text|data")
            continue
        has_text = "text" in part
        has_data = "data" in part
        reject_unknown_keys(part, {"text", "data"}, p)
        if has_text and has_data:
            fail(p, "has both text and data -- a part carries exactly one")
        if not has_text and not has_data:
            fail(p, "has neither text nor data")
        if has_text and not isinstance(part["text"], str):
            fail(p + ".text", "must be a string")
        if has_data and not is_mapping(part["data"]):
            fail(p + ".data", "must be an object")


def check_tool_validations(tv, at):
    if not is_mapping(tv):
        fail(at, "must be an object")
        return
    # v0 ToolValidations has exactly one field: expected_tool_calls. No condition (v1),
    # no forbidden_tool_calls (schemas.md: do not write it; strict v0 rejects it).
    reject_unknown_keys(tv, {"expected_tool_calls"}, at)
    calls = tv.get("expected_tool_calls")
    if not isinstance(calls, list) or len(calls) < 1:
        fail(at + ".expected_tool_calls",
             "must be a non-empty list (omit tool_validations entirely if there is nothing to assert)")
        return
    for i, call in enumerate(calls):
        p = "{}.expected_tool_calls[{}]".format(at, i)
        if not is_mapping(call):
            fail(p, "must be an object")
            continue
        reject_unknown_keys(call, {"tool", "parameters", "output"}, p)
        if not isinstance(call.get("tool"), str) or not call.get("tool"):
            fail(p + ".tool", "required string")
        if "parameters" in call and call["parameters"] is not None:
            if not is_mapping(call["parameters"]):
                fail(p + ".parameters", "must be a map of name -> { value|check }")
            else:
                for name, spec in call["parameters"].items():
                    check_value_or_check(spec, "{}.parameters.{}".format(p, name))
        if "output" in call and call["output"] is not None:
            check_value_or_check(call["output"], p + ".output")


def check_step(step, at):
    if not is_mapping(step):
        fail(at, "must be an object")
        return
    # schemas.md: exactly one dynamic_conversation step. fixed_message is valid v0 but
    # this skill never emits it.
    reject_unknown_keys(step, {
        "type", "user_agent", "max_turns",
        "agent_response_validations", "rule_compliance_validations", "tool_validations",
    }, at)

    if step.get("type") != "dynamic_conversation":
        fail(at + ".type",
             'must be present and equal "dynamic_conversation" (got {!r})'.format(step.get("type")))

    # user_agent
    ua = step.get("user_agent")
    if not is_mapping(ua):
        fail(at + ".user_agent", "required object { task_summary, initial_message? }")
    else:
        reject_unknown_keys(ua, {"task_summary", "initial_message"}, at + ".user_agent")
        if not isinstance(ua.get("task_summary"), str) or not ua.get("task_summary"):
            fail(at + ".user_agent.task_summary", "required non-empty string")
        im = ua.get("initial_message")
        if im is not None:
            if isinstance(im, str):
                pass
            elif is_mapping(im):
                check_structured_message(im, at + ".user_agent.initial_message")
            else:
                fail(at + ".user_agent.initial_message", "must be a string or a { parts: [...] } object")

    # max_turns
    mt = step.get("max_turns")
    if not is_int(mt) or mt < 1 or mt > 15:
        fail(at + ".max_turns", "required integer 1-15 (got {!r})".format(mt))

    # agent_response_validations -- skill requires >= 1
    if "agent_response_validations" not in step:
        fail(at + ".agent_response_validations", "required by this skill -- at least one { check } entry")
    else:
        n = check_check_list(step["agent_response_validations"], at + ".agent_response_validations")
        if n == 0:
            fail(at + ".agent_response_validations", "must have at least one { check } entry")

    # rule_compliance_validations -- optional; omit when empty rather than []
    if "rule_compliance_validations" in step:
        n = check_check_list(step["rule_compliance_validations"], at + ".rule_compliance_validations")
        if n == 0:
            fail(at + ".rule_compliance_validations", "omit entirely when empty rather than writing an empty list")

    # tool_validations -- optional
    if "tool_validations" in step and step["tool_validations"] is not None:
        check_tool_validations(step["tool_validations"], at + ".tool_validations")


def validate(doc, stem, enabled=None):
    if not is_mapping(doc):
        fail("<root>", "must be a mapping")
        return

    # Top level: closed set id/description/tags/test_steps (schemas.md). schema_version and
    # custom_headers are valid v0 but outside schemas.md's set -> rejected.
    reject_unknown_keys(doc, {"id", "description", "tags", "test_steps"}, "<root>")

    # id
    doc_id = doc.get("id")
    if not isinstance(doc_id, str) or not ID_TAG_RE.match(doc_id):
        fail("id", "required string matching ^[a-zA-Z0-9_]+$ (hyphens rejected)")
    elif stem is not None and doc_id != stem:
        fail("id", 'must equal the filename stem "{}" (got "{}")'.format(stem, doc_id))

    # tags -- schema allows null, but this skill always sets >= 1 dimension tag
    tags = doc.get("tags")
    if not isinstance(tags, list) or len(tags) == 0:
        fail("tags", "required by this skill -- a non-empty list with at least one dimension tag")
    else:
        for i, t in enumerate(tags):
            if not isinstance(t, str) or not ID_TAG_RE.match(t):
                fail("tags[{}]".format(i), "must be a string matching ^[a-zA-Z0-9_]+$ (got {!r})".format(t))
        if not any(t in DIMENSION_TAGS for t in tags if isinstance(t, str)):
            fail("tags", "must include at least one dimension tag from the fixed set")

    # id-category token -> dimension tag must be present somewhere in tags
    if isinstance(doc_id, str):
        parts = doc_id.split("_")
        if len(parts) >= 2:
            category = parts[1]
            expect_tag = CATEGORY_TO_TAG.get(category)
            if expect_tag and isinstance(tags, list) and expect_tag not in tags:
                fail("tags", 'category "{}" requires dimension tag "{}" to be present'.format(
                    category, expect_tag))
            # Enabled-set gate (only when an enabled set was supplied via --enabled).
            # Gate on the id Category token -> registry key, so BusinessOutcome gates
            # independently of Correctness despite sharing the correctness tag.
            if enabled is not None:
                key = CATEGORY_TO_KEY.get(category)
                if key is not None and key not in enabled:
                    fail("id", 'dimension "{}" (id category "{}") is disabled for this run '
                               "-- it is not in the enabled set".format(key, category))

    # test_steps -- exactly one
    steps = doc.get("test_steps")
    if not isinstance(steps, list):
        fail("test_steps", "required list")
    elif len(steps) != 1:
        fail("test_steps", "must contain exactly one step (got {})".format(len(steps)))
    else:
        check_step(steps[0], "test_steps[0]")


def _load_enabled(path):
    """Load the resolved enabled-dimension set written by the generator.

    Accepts either a bare JSON list of dimension keys, or {"enabled": [...]}.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        sys.stderr.write("cannot read enabled set {}: {}\n".format(path, e))
        sys.exit(2)
    except ValueError as e:
        sys.stderr.write("enabled set {} is not valid JSON -- {}\n".format(path, e))
        sys.exit(2)
    if isinstance(data, dict):
        data = data.get("enabled", [])
    if not isinstance(data, list):
        sys.stderr.write("enabled set {} must be a JSON list or {{\"enabled\": [...]}}\n".format(path))
        sys.exit(2)
    return set(data)


USAGE = "usage: validateschema.py <path-to-testcase.yaml> [--enabled <enabled-dimensions.json>]\n"


def main():
    args = sys.argv[1:]
    path = None
    enabled = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--enabled":
            if i + 1 >= len(args):
                sys.stderr.write(USAGE)
                sys.exit(2)
            enabled = _load_enabled(args[i + 1])
            i += 2
            continue
        if path is None:
            path = a
            i += 1
            continue
        sys.stderr.write(USAGE)
        sys.exit(2)
    if path is None:
        sys.stderr.write(USAGE)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        sys.stderr.write("cannot read {}: {}\n".format(path, e))
        sys.exit(2)

    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        sys.stderr.write("{}: YAML parse error -- {}\n".format(path, e))
        sys.exit(2)

    stem = re.sub(r"\.ya?ml$", "", os.path.basename(path), flags=re.IGNORECASE)
    validate(doc, stem, enabled)

    if not notes:
        sys.exit(0)
    for n in notes:
        sys.stderr.write(n + "\n")
    sys.exit(1)


if __name__ == "__main__":
    main()
