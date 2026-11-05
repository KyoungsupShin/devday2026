"""Small transport models intentionally independent from any agent framework."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Candidate:
    id: str
    label: str
    description: str


@dataclass(frozen=True)
class RankedCandidate:
    candidate: Candidate
    score: float


@dataclass(frozen=True)
class RouteDecision:
    selected: str
    scores: dict[str, float]
    margin: float
    engine: str
    fallback: bool = False


@dataclass(frozen=True)
class TraceEvent:
    step: int
    event: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

