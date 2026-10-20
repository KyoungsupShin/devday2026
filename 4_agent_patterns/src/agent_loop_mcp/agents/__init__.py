"""Agent registry and execution services for the independent agent loop."""

from .registry import (
    FOOD_AGENT_BY_ID,
    FOOD_AGENT_DEFINITIONS,
    REVISION_AGENT_IDS,
    SPECIALIST_AGENT_IDS,
    SYNTHESIS_AGENT_ID,
    FoodAgentDefinition,
)

__all__ = [
    "FOOD_AGENT_BY_ID",
    "FOOD_AGENT_DEFINITIONS",
    "REVISION_AGENT_IDS",
    "SPECIALIST_AGENT_IDS",
    "SYNTHESIS_AGENT_ID",
    "FoodAgentDefinition",
]
