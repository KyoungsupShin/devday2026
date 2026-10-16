#!/bin/sh
set -eu

# Codex sends a Responses API shell tool. LiteLLM normally drops it while
# converting Responses requests to Chat Completions, but SAP AI Core accepts
# standard function tools. Convert only that tool shape before the request is
# forwarded; no provider response or streaming internals are modified.
TARGET="/app/.venv/lib/python3.13/site-packages/litellm/responses/litellm_completion_transformation/transformation.py"

python - "$TARGET" <<'PY'
import sys
from pathlib import Path

target = Path(sys.argv[1])
text = target.read_text()
marker = "Codex shell tool compatibility patch"
if marker in text:
    print(f"{marker} already applied")
    raise SystemExit(0)

anchor = '''            else:
                _tool_type = tool.get("type")
                if _tool_type in ("computer_use", "image_generation", "shell"):
'''
replacement = '''            elif tool.get("type") == "shell":
                # Codex Responses API shell tools have no native Chat Completions
                # representation. SAP AI Core accepts function tools, so retain
                # the command contract as a regular function named exec_command.
                parameters = tool.get("parameters")
                if not isinstance(parameters, Mapping) or not parameters:
                    parameters = {
                        "type": "object",
                        "properties": {"cmd": {"type": "string"}},
                        "required": ["cmd"],
                    }
                elif "type" not in parameters:
                    parameters = {**dict(parameters), "type": "object"}
                chat_completion_tools.append(
                    cast(
                        ChatCompletionToolParam,
                        {
                            "type": "function",
                            "function": {
                                "name": str(tool.get("name") or "exec_command"),
                                "description": str(tool.get("description") or "Run a shell command."),
                                "parameters": dict(parameters),
                                "strict": bool(tool.get("strict", False)),
                            },
                        },
                    )
                )
            else:
                _tool_type = tool.get("type")
                if _tool_type in ("computer_use", "image_generation", "shell"):
'''

if anchor not in text:
    raise SystemExit("LiteLLM Responses tool transform anchor not found")
target.write_text(text.replace(anchor, replacement, 1))
print(f"{marker} applied")
PY

# LiteLLM's current image can emit a Pydantic MockValSer during SAP streaming.
# Fall back to plain JSON-compatible values only for that known serializer bug.
UTILS_TARGET="/app/.venv/lib/python3.13/site-packages/litellm/types/utils.py"
python - "$UTILS_TARGET" <<'PY'
import sys
from pathlib import Path

target = Path(sys.argv[1])
text = target.read_text()
marker = "Codex SAP stream serializer fallback"
if marker in text:
    print(f"{marker} already applied")
    raise SystemExit(0)

original = """        return super().model_dump(**kwargs)"""
replacement = """        # Codex SAP stream serializer fallback
        try:
            return super().model_dump(**kwargs)
        except TypeError as error:
            if "MockValSer" not in str(error) and "SchemaSerializer" not in str(error):
                raise

            def safe_value(value):
                if isinstance(value, (str, int, float, bool)) or value is None:
                    return value
                if isinstance(value, (list, tuple)):
                    return [safe_value(item) for item in value]
                if isinstance(value, dict):
                    return {str(key): safe_value(item) for key, item in value.items() if item is not None}
                if hasattr(value, "model_dump"):
                    try:
                        return value.model_dump(**kwargs)
                    except Exception:
                        pass
                if hasattr(value, "__dict__"):
                    return {str(key): safe_value(item) for key, item in vars(value).items() if item is not None}
                return str(value)

            return safe_value(vars(self))"""

if original not in text:
    raise SystemExit("LiteLLM model_dump anchor not found")
target.write_text(text.replace(original, replacement, 1))
print(f"{marker} applied")
PY

