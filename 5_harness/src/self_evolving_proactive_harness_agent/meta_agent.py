"""LLM-backed Meta Cognitive Agent implementation."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from lab_common.config import Settings
from lab_common.llm import chat_text

from .models import CognitiveDecision, CognitiveState, utc_now
from .prompts import get_prompt


_HANGUL = re.compile(r"[가-힣]")


class MetaCognitiveAgent:
    """Ask an LLM for a schema-validated autonomous decision."""

    def __init__(self, settings: Settings | None = None, *, responder: Callable[[list[dict[str, str]]], str] | None = None, max_retries: int = 1) -> None:
        self.settings, self.responder, self.max_retries = settings, responder, max_retries

    def decide(self, state: CognitiveState, inventory: list[dict[str, Any]], *, feedback: str | None = None) -> CognitiveDecision:
        if self.responder is None and self.settings is None:
            raise RuntimeError("AI Core 설정이 없어 Meta Cognitive Agent 판단을 실행할 수 없습니다.")
        # Give the LLM relevant working memory, rather than every historic run.
        # Durable records remain in the repository and are restored next cycle.
        memory = state.model_dump(mode="json")
        memory["recent_observations"] = state.recent_observations[-8:]
        memory["reflection_history"] = [item.model_dump(mode="json") for item in state.reflection_history[-5:]]
        memory["goals"] = [item.model_dump(mode="json") for item in state.goals if item.status in {"PROPOSED", "ACTIVE", "PAUSED"}][-6:]
        memory["tasks"] = [item.model_dump(mode="json") for item in state.tasks if item.status not in {"COMPLETED", "CANCELLED"}][-8:]
        payload = {
            "state": memory, "capabilities": inventory,
            "schema": {
                "action": "EXPLORE|INVESTIGATE|VALIDATE|SIMULATE|CREATE_GOAL|CREATE_TASK|DELEGATE|REFLECT|REVISE_GOAL|WAIT|COMPLETE|REQUEST_APPROVAL",
                "objective": "string|null", "rationale": "string",
                "expected_value": "string|null", "confidence": "0..1|null",
                "required_capabilities": ["registered capability id"],
                "analysis_plan": ["Korean, concrete read-only analysis step"],
                "simulation": {"dataset_id": "registered dataset id", "baseline_column": "approved numeric column", "scenario_column": "approved numeric column", "group_by": "approved category column|null", "scenario_description": "Korean business scenario"},
                "discovered_problems": ["Korean business problem statement"],
                "hypotheses": ["Korean hypothesis requiring validation"],
                "next_wakeup_at": "ISO 8601 datetime|null",
                "goal_id": "existing goal id|null", "task_id": "existing task id|null",
                "goal": {"title": "Korean title", "description": "Korean scope", "expected_outcome": "Korean outcome", "priority": "1..5"},
                "task": {"title": "Korean title", "objective": "Korean objective", "capability": "registered capability id|null", "dependencies": ["task id"], "expected_output": "Korean result"},
            },
        }
        messages = [{"role": "system", "content": get_prompt("system")}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        if feedback:
            messages.append({"role": "user", "content": feedback})
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                raw = self.responder(messages) if self.responder else chat_text(self.settings, messages)
                decision = CognitiveDecision.model_validate(self._json_object(raw))
                self._validate_display_language(decision)
                return decision
            except Exception as error:  # Invalid model output is repaired once with explicit feedback.
                last_error = error
                messages.append({"role": "user", "content": f"형식 검증에 실패했습니다: {error}. 한국어 비즈니스 표현을 유지하며 수정된 JSON 객체만 반환하세요."})
        raise ValueError(f"Meta Cognitive Agent 의사결정을 검증하지 못했습니다: {last_error}")

    @staticmethod
    def _json_object(raw: str) -> dict[str, Any]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        value = json.loads(cleaned)
        if not isinstance(value, dict):
            raise TypeError("Decision must be a JSON object")
        return value

    @staticmethod
    def _validate_display_language(decision: CognitiveDecision) -> None:
        """Keep persisted business-facing decision text consistently Korean."""
        fields = [
            decision.rationale, decision.objective, decision.expected_value,
            *decision.analysis_plan, *decision.discovered_problems, *decision.hypotheses,
        ]
        visible_text = [field for field in fields if isinstance(field, str) and field.strip()]
        if any(not _HANGUL.search(field) for field in visible_text):
            raise ValueError(
                "의사결정 근거, 목표, 기대 효과, 문제 정의, 가설은 현업 사용자가 이해할 수 있는 한국어로 작성해야 합니다."
            )

