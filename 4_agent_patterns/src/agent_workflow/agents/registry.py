"""Static Agent definitions for the workflow."""
from __future__ import annotations

from dataclasses import dataclass

from ..prompts import agent_prompt


@dataclass(frozen=True)
class FoodAgentDefinition:
    id: str
    label: str
    description: str
    system_prompt: str


FOOD_AGENT_DEFINITIONS = (
    FoodAgentDefinition(
        "work-planning",
        "Work Planning Agents (Orchestrator)",
        "사용자 목표를 분석해 필요한 전문 Agent·병렬 실행 단계·최종 담당 Agent를 LLM 실행 계획으로 결정하고 작업을 조율합니다.",
        agent_prompt("work-planning"),
    ),
    FoodAgentDefinition(
        "food-rnd",
        "Food R&D Agent",
        "상품 요구사항을 바탕으로 레시피, 원재료 배합, 제조공정과 기술 위험을 설계합니다.",
        agent_prompt("food-rnd"),
    ),
    FoodAgentDefinition(
        "procurement",
        "Procurement Agent",
        "원재료 소요량·구매원가를 추정하고 공급업체 선정 기준과 공급망 위험을 제안합니다.",
        agent_prompt("procurement"),
    ),
    FoodAgentDefinition(
        "quality-assurance",
        "Quality Assurance Agent",
        "식품안전, 위생관리, 알레르기, HACCP 및 품질 위험을 평가합니다.",
        agent_prompt("quality-assurance"),
    ),
    FoodAgentDefinition(
        "marketing",
        "Marketing Agent",
        "브랜드 콘셉트, 상품명, 메시지, 판매 채널과 출시 전략을 수립합니다.",
        agent_prompt("marketing"),
    ),
    FoodAgentDefinition(
        "finance",
        "Finance Agent",
        "제조원가, 판매수익, 공헌이익, 손익분기점과 재무 위험을 분석합니다.",
        agent_prompt("finance"),
    ),
    FoodAgentDefinition(
        "synthesis",
        "Synthesis Agent",
        "선행 전문 Agent들의 결과를 비교·통합해 사용자에게 바로 전달할 최종 답변을 작성합니다.",
        agent_prompt("synthesis"),
    ),
)

FOOD_AGENT_BY_ID = {agent.id: agent for agent in FOOD_AGENT_DEFINITIONS}
EXECUTABLE_AGENT_IDS = tuple(
    agent.id for agent in FOOD_AGENT_DEFINITIONS if agent.id != "work-planning"
)
