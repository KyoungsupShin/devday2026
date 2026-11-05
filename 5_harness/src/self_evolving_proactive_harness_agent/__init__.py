"""Self-evolving proactive harness cognitive core.

The package is intentionally independent from the reactive Joule orchestration
flow.  It can inspect its registered capabilities, persist a compact cognitive
state, and run one bounded cognitive cycle at a time.
"""

from .capabilities import discover_capabilities
from .datasets import analyze_csv_datasets, discover_csv_datasets
from .meta_agent import MetaCognitiveAgent
from .handoff import HandoffRequest, HandoffResult, LocalCSVCapabilityAdapter
from .models import CognitiveDecision, CognitiveState, Goal, LifecycleStatus, ReactTurn, Task
from .repository import JsonCognitiveRepository
from .runtime import CognitiveCore, RuntimePolicy
from .notebook import create_default_core, create_notebook_ui, launch_notebook_ui

__all__ = [
    "CognitiveCore",
    "CognitiveDecision",
    "CognitiveState",
    "Goal",
    "Task",
    "HandoffRequest",
    "HandoffResult",
    "LocalCSVCapabilityAdapter",
    "JsonCognitiveRepository",
    "LifecycleStatus",
    "MetaCognitiveAgent",
    "ReactTurn",
    "RuntimePolicy",
    "discover_capabilities",
    "discover_csv_datasets",
    "analyze_csv_datasets",
    "create_default_core",
    "create_notebook_ui",
    "launch_notebook_ui",
]
