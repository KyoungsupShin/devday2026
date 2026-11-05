"""Prompt loading for the Meta Cognitive Agent."""

from __future__ import annotations

import tomllib
from pathlib import Path

_PATH = Path(__file__).with_name("meta_cognitive.toml")


def get_prompt(name: str) -> str:
    with _PATH.open("rb") as handle:
        value = tomllib.load(handle)
    prompt = value.get(name)
    if not isinstance(prompt, str):
        raise KeyError(f"Prompt not found: {name}")
    return prompt
