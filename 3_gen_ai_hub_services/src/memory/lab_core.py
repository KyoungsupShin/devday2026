"""Core workflow for ``04_memory_chatbot.ipynb``."""
from __future__ import annotations

from typing import Any

from lab_common.config import Settings
from src.orchestration.lab_core import build_orchestration_service


class MemoryChatbot:
    """Stateful orchestration conversation with explicit, resettable history."""

    def __init__(self, settings: Settings, service: Any | None = None):
        self.settings = settings
        self.service = service or build_orchestration_service(
            settings, system_prompt="You are a helpful chatbot assistant.", max_tokens=500
        )
        self.history: list[Any] = []

    def chat(self, message: str) -> str:
        cleaned = message.strip()
        if not cleaned:
            raise ValueError("메시지를 입력하세요.")
        response = self.service.run(placeholder_values={"user_query": cleaned}, history=self.history)
        answer = response.final_result.choices[0].message
        self.history = list(response.intermediate_results.templating)
        self.history.append(answer)
        return str(answer.content)

    def reset(self) -> None:
        self.history = []
