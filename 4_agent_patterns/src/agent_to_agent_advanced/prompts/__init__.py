"""TOML-backed prompt resources for the F&B A2A example."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - retained for older notebooks
    import tomli as tomllib


_PROMPT_DIRECTORY = Path(__file__).parent


def _resources() -> dict[str, Any]:
    resources: dict[str, Any] = {}
    for path in sorted(_PROMPT_DIRECTORY.glob("*.toml")):
        with path.open("rb") as handle:
            resources.update(tomllib.load(handle))
    return resources


def get_prompt(name: str) -> str:
    """Return a named prompt resource using dotted TOML section syntax."""
    value: Any = _resources()
    for part in name.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(f"Prompt resource를 찾을 수 없습니다: {name}")
        value = value[part]
    if not isinstance(value, str):
        raise TypeError(f"Prompt resource는 문자열이어야 합니다: {name}")
    return value


def get_optional_prompt(name: str) -> str | None:
    """Return a prompt resource when it exists without masking invalid content."""
    try:
        return get_prompt(name)
    except KeyError:
        return None


def render_prompt(name: str, /, **values: Any) -> str:
    """Render a prompt resource with explicit runtime values only."""
    # Older notebook cells and prompt-inspection tests may render an A2A prompt
    # outside a chat session.  An absent transcript is the empty transcript.
    values.setdefault("conversation_history", "[]")
    return get_prompt(name).format(**values)
