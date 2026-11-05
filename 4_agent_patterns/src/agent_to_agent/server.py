"""FastAPI factories that expose each F&B team as an A2A Agent server."""

from __future__ import annotations

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from fastapi import FastAPI
from .lesson_support.config import Settings

from .catalog import (
    AGENT_CATALOG,
    EXECUTION_BOUNDARY,
    MESSAGE_MODES,
    PROTOCOL_VERSION,
)
from .executor import FnbTeamExecutor


def _agent_spec(agent_id: str) -> dict[str, object]:
    try:
        return next(item for item in AGENT_CATALOG if item["agent_id"] == agent_id)
    except StopIteration as error:
        raise ValueError(f"알 수 없는 F&B A2A Agent: {agent_id}") from error


def build_agent_card(agent_id: str, base_url: str) -> AgentCard:
    """Build the public Card without exposing private prompts or runtime state."""
    spec = _agent_spec(agent_id)
    skill = AgentSkill(
        id=str(spec["skill_id"]),
        name=str(spec["agent_label"]),
        description=(
            f"{spec['description']} Internal delegation is selected by the team LLM at runtime."
        ),
        tags=list(spec["tags"]),
        examples=list(spec["examples"]),
        input_modes=list(MESSAGE_MODES),
        output_modes=list(MESSAGE_MODES),
    )
    return AgentCard(
        name=str(spec["agent_label"]),
        description=str(spec["description"]) + " " + EXECUTION_BOUNDARY,
        version=PROTOCOL_VERSION,
        default_input_modes=list(MESSAGE_MODES),
        default_output_modes=list(MESSAGE_MODES),
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=base_url.rstrip("/"),
                protocol_version=PROTOCOL_VERSION,
            )
        ],
        skills=[skill],
    )


def create_a2a_app(
    agent_id: str, base_url: str, settings: Settings | None = None
) -> FastAPI:
    card = build_agent_card(agent_id, base_url)
    handler = DefaultRequestHandler(
        agent_executor=FnbTeamExecutor(agent_id, settings),
        task_store=InMemoryTaskStore(),
        agent_card=card,
        validate_input_modes=True,
    )
    app = FastAPI(title=card.name, version=PROTOCOL_VERSION)
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/"),
    )
    return app
