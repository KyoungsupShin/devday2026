"""Runnable, dependency-free delegation and A2A handoff example for Harness.

The transport is deliberately in-memory: it makes the routing, message envelope,
and role boundaries inspectable in a notebook without invoking an external model
or changing any business system.  Replacing ``InMemoryA2ABus`` with a remote
transport must preserve the same envelope contract.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable
from uuid import uuid4


@dataclass(frozen=True)
class A2AMessage:
    """The minimal envelope every agent receives and emits."""

    message_id: str
    correlation_id: str
    sender: str
    recipient: str
    message_type: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


AgentHandler = Callable[[A2AMessage], list[A2AMessage]]


class InMemoryA2ABus:
    """Small message bus that dispatches messages between registered agents."""

    def __init__(self) -> None:
        self._handlers: dict[str, AgentHandler] = {}
        self.trace: list[dict[str, Any]] = []

    def register(self, agent_name: str, handler: AgentHandler) -> None:
        self._handlers[agent_name] = handler

    def deliver(self, message: A2AMessage) -> None:
        """Deliver a message and recursively deliver its declared replies."""
        handler = self._handlers.get(message.recipient)
        if handler is None:
            raise ValueError(f"등록되지 않은 A2A recipient: {message.recipient}")
        self.trace.append({"event": "delivered", "message": message.to_dict()})
        for reply in handler(message):
            if reply.sender != message.recipient:
                raise ValueError("A2A reply sender는 현재 recipient와 같아야 합니다.")
            if reply.correlation_id != message.correlation_id:
                raise ValueError("A2A reply의 correlation_id가 일치하지 않습니다.")
            self.deliver(reply)


def _message(
    *, correlation_id: str, sender: str, recipient: str, message_type: str, payload: dict[str, Any]
) -> A2AMessage:
    return A2AMessage(
        message_id=str(uuid4()),
        correlation_id=correlation_id,
        sender=sender,
        recipient=recipient,
        message_type=message_type,
        payload=payload,
    )


def _researcher(message: A2AMessage) -> list[A2AMessage]:
    if message.message_type != "delegated_task":
        raise ValueError("researcher는 delegated_task만 처리합니다.")

    # Safe, deterministic stand-in for a read-only business lookup.
    inventory = [
        {"sku": "SKU-A", "available": 8, "reorder_point": 20},
        {"sku": "SKU-B", "available": 42, "reorder_point": 15},
    ]
    candidates = [item for item in inventory if item["available"] < item["reorder_point"]]
    evidence = {
        "request": message.payload["request"],
        "source": "local_read_only_inventory_fixture",
        "facts": candidates,
        "limitations": "교육용 fixture이며 실제 발주나 외부 쓰기는 수행하지 않았습니다.",
    }
    return [
        _message(
            correlation_id=message.correlation_id,
            sender="researcher",
            recipient="analyst_writer",
            message_type="evidence_packet",
            payload=evidence,
        )
    ]


def _analyst_writer(message: A2AMessage) -> list[A2AMessage]:
    if message.message_type != "evidence_packet":
        raise ValueError("analyst_writer는 researcher의 evidence_packet만 처리합니다.")
    facts = message.payload["facts"]
    skus = ", ".join(item["sku"] for item in facts) or "없음"
    report = {
        "summary": f"읽기 전용 재고 근거상 발주 검토 대상은 {len(facts)}건({skus})입니다.",
        "evidence_source": message.payload["source"],
        "limitations": message.payload["limitations"],
    }
    return [
        _message(
            correlation_id=message.correlation_id,
            sender="analyst_writer",
            recipient="user",
            message_type="final_report",
            payload=report,
        )
    ]


def _user_inbox(messages: list[A2AMessage]) -> AgentHandler:
    def receive(message: A2AMessage) -> list[A2AMessage]:
        if message.message_type != "final_report":
            raise ValueError("user inbox는 final_report만 수신합니다.")
        messages.append(message)
        return []

    return receive


def run_delegation_a2a(request: str) -> dict[str, Any]:
    """Delegate one request and return the report plus a verifiable delivery trace."""
    if not request or not request.strip():
        raise ValueError("요청을 입력하세요.")

    correlation_id = str(uuid4())
    delivered_to_user: list[A2AMessage] = []
    bus = InMemoryA2ABus()
    bus.register("researcher", _researcher)
    bus.register("analyst_writer", _analyst_writer)
    bus.register("user", _user_inbox(delivered_to_user))

    task = _message(
        correlation_id=correlation_id,
        sender="orchestrator",
        recipient="researcher",
        message_type="delegated_task",
        payload={"request": request.strip(), "access": "read_only"},
    )
    bus.deliver(task)

    if len(delivered_to_user) != 1:
        raise RuntimeError("A2A 실행이 최종 report 하나로 완료되지 않았습니다.")
    trace = bus.trace
    hops = [(item["message"]["sender"], item["message"]["recipient"]) for item in trace]
    expected_hops = [("orchestrator", "researcher"), ("researcher", "analyst_writer"), ("analyst_writer", "user")]
    if hops != expected_hops:
        raise RuntimeError(f"예상하지 못한 A2A 경로: {hops}")

    return {
        "report": delivered_to_user[0].payload,
        "trace": trace,
        "verification": {
            "passed": True,
            "expected_hops": expected_hops,
            "actual_hops": hops,
            "same_correlation_id": len({item["message"]["correlation_id"] for item in trace}) == 1,
            "no_external_write": True,
        },
    }
