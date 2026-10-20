"""Human-approved Outlook mail handoff for the F&B A2A lesson.

The LLM can prepare a request for human review, but never receives a tool that
sends mail.  A person must review the draft in the UI and explicitly invoke
``send_outlook_mail`` before the EAI bridge can perform the external write.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import requests
from lab_common.config import Settings

HUMAN_APPROVAL_TOOL_NAME = "request_human_email_approval"
_MAX_SUBJECT_LENGTH = 180
_MAX_BODY_LENGTH = 12_000
_MAX_RECIPIENTS = 20


class OutlookMailError(RuntimeError):
    """A safe, user-facing failure while using the EAI Graph-mail bridge."""


def human_approval_tool() -> dict[str, Any]:
    """Describe a draft-only HITL Tool available to Orchestration.

    This is deliberately not a send-mail Tool.  The model cannot provide an
    email address or trigger an external write; it can only explain the human
    decision needed and prepare Korean draft text for the reviewer.
    """
    return {
        "type": "function",
        "function": {
            "name": HUMAN_APPROVAL_TOOL_NAME,
            "description": (
                "Create a human-review email draft when the accumulated evidence "
                "shows that a person must make, submit, or approve a bounded "
                "external decision. This only creates a pending draft. It never "
                "sends email and must not be used to infer an approver or address."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient_role": {
                        "type": "string",
                        "description": (
                            "The business role that should review the decision; "
                            "do not invent a person's name or email address."
                        ),
                    },
                    "subject": {
                        "type": "string",
                        "description": "A concise Korean email subject for the human reviewer.",
                    },
                    "body": {
                        "type": "string",
                        "description": (
                            "A concise Korean draft with confirmed evidence, its "
                            "scope, and exactly what human decision is requested."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this decision belongs to a human, grounded in the record.",
                    },
                    "chat_summary": {
                        "type": "string",
                        "description": (
                            "One concise Korean operations-chat update. Do not expose Tool or Agent names, "
                            "API/A2A terms, raw field names, machine status tokens, CSV/snapshot wording, "
                            "or implementation details."
                        ),
                    },
                },
                "required": [
                    "recipient_role",
                    "subject",
                    "body",
                    "reason",
                    "chat_summary",
                ],
                "additionalProperties": False,
            },
        },
    }


def create_human_approval_draft(arguments: Mapping[str, Any]) -> dict[str, str]:
    """Validate and normalize an LLM-proposed draft without sending it."""
    values: dict[str, str] = {}
    for field in ("recipient_role", "subject", "body", "reason"):
        raw = arguments.get(field)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"Human approval Tool에는 {field} 문자열이 필요합니다.")
        values[field] = raw.strip()
    summary = arguments.get("chat_summary")
    values["chat_summary"] = summary.strip() if isinstance(summary, str) else ""
    if len(values["subject"]) > _MAX_SUBJECT_LENGTH:
        raise ValueError("승인 요청 메일 제목이 너무 깁니다.")
    if len(values["body"]) > _MAX_BODY_LENGTH:
        raise ValueError("승인 요청 메일 본문이 너무 깁니다.")
    return {
        "approval_id": f"approval-{uuid4()}",
        "state": "pending_human_approval",
        **values,
    }


def _configured_endpoint() -> str:
    endpoint = os.getenv("OUTLOOK_GRAPH_SEND_ENDPOINT", "").strip()
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OutlookMailError(
            "Outlook 메일 연동 주소가 설정되지 않았습니다. OUTLOOK_GRAPH_SEND_ENDPOINT를 확인하세요."
        )
    return endpoint


def _recipients(value: str) -> list[str]:
    recipients = [
        item.strip() for item in value.replace(",", ";").split(";") if item.strip()
    ]
    if not recipients:
        raise OutlookMailError("수신자 이메일 주소를 하나 이상 입력하세요.")
    if len(recipients) > _MAX_RECIPIENTS:
        raise OutlookMailError("한 번에 보낼 수신자는 최대 20명입니다.")
    if any(
        "@" not in item or item.startswith("@") or item.endswith("@")
        for item in recipients
    ):
        raise OutlookMailError("수신자 이메일 주소 형식을 확인하세요.")
    return recipients


def send_outlook_mail(
    settings: Settings,
    draft: Mapping[str, Any],
    *,
    recipients: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """Send one explicitly human-approved message through the EAI Graph bridge."""
    if not settings.allow_write_tools:
        raise OutlookMailError(
            "외부 발송이 비활성화되어 있습니다. 명시적으로 ALLOW_WRITE_TOOLS=true를 설정한 뒤 다시 승인하세요."
        )
    approval_id = draft.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        raise OutlookMailError("유효한 사람 승인 초안이 없습니다.")
    normalized_subject = subject.strip()
    normalized_body = body.strip()
    if not normalized_subject or len(normalized_subject) > _MAX_SUBJECT_LENGTH:
        raise OutlookMailError("메일 제목을 1~180자로 입력하세요.")
    if not normalized_body or len(normalized_body) > _MAX_BODY_LENGTH:
        raise OutlookMailError("메일 본문을 1~12,000자로 입력하세요.")
    token = os.getenv("A2A_GRAPH_MAIL_SERVICE_TOKEN", "").strip()
    if not token:
        raise OutlookMailError(
            "EAI 메일 서비스 인증값이 설정되지 않았습니다. A2A_GRAPH_MAIL_SERVICE_TOKEN을 확인하세요."
        )

    try:
        response = requests.post(
            _configured_endpoint(),
            json={
                "approvalId": approval_id,
                "toRecipients": _recipients(recipients),
                "subject": normalized_subject,
                "body": normalized_body,
            },
            headers={"X-A2A-Graph-Mail-Token": token},
            timeout=float(os.getenv("OUTLOOK_GRAPH_SEND_TIMEOUT_SECONDS", "30")),
        )
    except (requests.RequestException, ValueError) as error:
        raise OutlookMailError("Outlook 메일 서비스에 연결하지 못했습니다.") from error

    if response.status_code not in {200, 201, 202}:
        raise OutlookMailError(_safe_eai_error(response))
    try:
        payload = response.json()
    except ValueError as error:
        raise OutlookMailError(
            "Outlook 메일 서비스가 올바른 응답을 반환하지 않았습니다."
        ) from error
    if not isinstance(payload, dict) or payload.get("state") != "sent":
        raise OutlookMailError("Outlook 메일 발송 결과를 확인할 수 없습니다.")
    return {
        "state": "sent",
        "approval_id": approval_id,
        "provider": "Microsoft Graph",
        "message_id": str(payload.get("messageId") or ""),
        "recipient_count": len(_recipients(recipients)),
    }


def _safe_eai_error(response: requests.Response) -> str:
    """Turn EAI failures into an actionable message without exposing secrets."""
    detail = "Outlook 메일 서비스가 발송을 거부했습니다."
    try:
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("error"), str):
            detail = payload["error"].strip() or detail
    except ValueError:
        pass
    return f"{detail} (HTTP {response.status_code})"
