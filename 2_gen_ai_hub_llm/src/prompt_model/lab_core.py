"""Core workflow for 01_prompt_and_model.ipynb."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Callable, Sequence

from lab_common.llm import chat_text, chat_text_stream
from lab_common.config import Settings

MAX_CHAT_HISTORY_MESSAGES = 12
MAX_CHAT_HISTORY_CHARACTERS = 12_000


def compare_prompts(
    question: str,
    settings: Settings,
    chat_caller: Callable[
        [Settings, list[dict[str, str]], str | None], str
    ] = chat_text,
) -> dict[str, str]:
    cleaned = question.strip()
    if not cleaned:
        raise ValueError("질문을 입력하세요.")
    baseline = chat_caller(settings, [{"role": "user", "content": cleaned}], None)
    constrained = chat_caller(
        settings,
        [
            {
                "role": "system",
                "content": "너는 교육 보조자다. 한국어로, 정확히 한 문장으로만 답한다.",
            },
            {"role": "user", "content": cleaned},
        ],
        None,
    )
    return {"question": cleaned, "baseline": baseline, "constrained": constrained}


def _chat_messages(
    message: str, history: Sequence[dict[str, str]] = (), system_prompt: str = ""
) -> tuple[str, list[dict[str, str]]]:
    cleaned = message.strip()
    if not cleaned:
        raise ValueError("질문을 입력하세요.")
    normalized: list[dict[str, str]] = []
    for item in history:
        role, content = item.get("role"), str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            raise ValueError(
                "대화 history에는 내용이 있는 user 또는 assistant 메시지만 넣을 수 있습니다."
            )
        normalized.append({"role": role, "content": content})
    retained: list[dict[str, str]] = []
    remaining = MAX_CHAT_HISTORY_CHARACTERS
    for item in reversed(normalized[-MAX_CHAT_HISTORY_MESSAGES:]):
        if len(item["content"]) <= remaining:
            retained.append(item)
            remaining -= len(item["content"])
    messages = (
        [{"role": "system", "content": system_prompt.strip()}]
        if system_prompt.strip()
        else []
    )
    messages.extend(reversed(retained))
    messages.append({"role": "user", "content": cleaned})
    return cleaned, messages


def run_chat(
    message: str,
    settings: Settings,
    history: Sequence[dict[str, str]] = (),
    system_prompt: str = "",
    model: str | None = None,
    chat_caller: Callable[
        [Settings, list[dict[str, str]], str | None], str
    ] = chat_text,
) -> dict[str, str]:
    cleaned, messages = _chat_messages(message, history, system_prompt)
    selected_model = model.strip() if model and model.strip() else settings.llm_model
    return {
        "message": cleaned,
        "model": selected_model,
        "reply": chat_caller(settings, messages, selected_model),
    }


def run_chat_stream(
    message: str,
    settings: Settings,
    history: Sequence[dict[str, str]] = (),
    system_prompt: str = "",
    model: str | None = None,
    chat_stream_caller: Callable[
        [Settings, list[dict[str, str]], str | None], Iterator[str]
    ] = chat_text_stream,
) -> Iterator[str]:
    _, messages = _chat_messages(message, history, system_prompt)
    selected_model = model.strip() if model and model.strip() else settings.llm_model
    yield from chat_stream_caller(settings, messages, selected_model)
