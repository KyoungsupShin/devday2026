"""A small, runtime-only Harness² lab for the F&B A2A notebook.

The module never edits prompt resources, Team cards, Tool permissions, or local
data. It proposes bounded orchestration supplements, probes them through the
existing public handoff API, and leaves final adoption to a human reviewer.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .lesson_support.llm import chat_text
from .lesson_support.config import Settings, load_settings

from .orchestration import MAX_HARNESS_ADDENDUM_CHARS
from .prompts import get_prompt, render_prompt

Runner = Callable[..., dict[str, Any]]
_VARIANT_IDS = ("baseline", "candidate_1", "candidate_2", "composed")
_FORBIDDEN_ADDENDUM_TERMS = (
    "agent card", "a2a", "tool", "json", "permission", "human approval",
    "external write", "시스템 프롬프트", "도구 권한", "a2a 계약", "json 형식",
    "사람 승인", "외부 쓰기",
)


def _json_object(raw: str, *, stage: str) -> dict[str, Any]:
    cleaned = str(raw or "").strip()
    fence = chr(96) * 3
    if cleaned.startswith(fence):
        cleaned = cleaned.split("\n", 1)[1].rsplit(fence, 1)[0].strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError(f"{stage} 응답이 유효한 JSON 객체가 아닙니다.") from error
    if not isinstance(value, dict):
        raise TypeError(f"{stage} 응답은 JSON 객체여야 합니다.")
    return value


def validate_addendum(value: Any) -> str:
    """Validate the only editable surface of this educational experiment."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("하네스 보조 지침은 비어 있지 않은 문자열이어야 합니다.")
    addendum = value.strip()
    if len(addendum) > MAX_HARNESS_ADDENDUM_CHARS:
        raise ValueError(f"하네스 보조 지침은 {MAX_HARNESS_ADDENDUM_CHARS}자 이하여야 합니다.")
    normalized = addendum.lower()
    forbidden = [term for term in _FORBIDDEN_ADDENDUM_TERMS if term in normalized]
    if forbidden:
        raise ValueError(
            "하네스 보조 지침은 Team/Tool/A2A/JSON/승인 경계를 다룰 수 없습니다: "
            + ", ".join(forbidden)
        )
    return addendum


def _variant(value: Any, *, stage: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TypeError(f"{stage} 후보는 객체여야 합니다.")
    title, addendum, rationale = value.get("title"), value.get("addendum"), value.get("rationale")
    if not all(isinstance(item, str) and item.strip() for item in (title, addendum, rationale)):
        raise ValueError(f"{stage} 후보에는 title, addendum, rationale 문자열이 필요합니다.")
    return {
        "title": title.strip()[:120],
        "addendum": validate_addendum(addendum),
        "rationale": rationale.strip()[:600],
    }


def _team_summary(record: Any) -> str:
    if not isinstance(record, dict):
        return ""
    artifact = record.get("artifact")
    payload = artifact.get("payload") if isinstance(artifact, dict) else None
    synthesis = payload.get("team_synthesis") if isinstance(payload, dict) else None
    if isinstance(synthesis, dict) and isinstance(synthesis.get("summary"), str):
        return synthesis["summary"].strip()
    return ""


def summarise_result(result: dict[str, Any]) -> dict[str, Any]:
    """Create a comparable view without exposing a candidate instruction."""
    artifacts = result.get("artifacts") if isinstance(result, dict) else []
    artifacts = artifacts if isinstance(artifacts, list) else []
    termination = result.get("termination") if isinstance(result, dict) else {}
    termination = termination if isinstance(termination, dict) else {}
    decision = termination.get("decision")
    decision = decision if isinstance(decision, dict) else {}
    update = decision.get("requester_update")
    update = update if isinstance(update, dict) else {}
    summaries = [_team_summary(record) for record in artifacts]
    return {
        "team_order": [
            str(record.get("producer")) for record in artifacts
            if isinstance(record, dict) and isinstance(record.get("producer"), str)
        ],
        "artifact_count": len(artifacts),
        "termination_state": str(termination.get("state") or "unknown"),
        "awaiting_human_approval": bool(result.get("human_approvals")),
        "requester_update": {
            key: str(update[key]) for key in ("status", "summary", "next_action")
            if isinstance(update.get(key), str)
        },
        "evidence_summaries": [summary for summary in summaries if summary][:3],
    }


def evaluate_comparison(comparison: dict[str, Any]) -> dict[str, Any]:
    """Score observable handoff-flow signals without judging business correctness.

    This intentionally avoids treating a shorter Team sequence as inherently
    better.  It makes the demo's comparison repeatable while leaving the
    business decision and candidate selection to a human reviewer.
    """
    value = comparison if isinstance(comparison, dict) else {}
    team_order = [
        str(team) for team in value.get("team_order", [])
        if isinstance(team, str) and team
    ]
    update = value.get("requester_update", {})
    update = update if isinstance(update, dict) else {}
    evidence = [
        str(item) for item in value.get("evidence_summaries", [])
        if isinstance(item, str) and item.strip()
    ]
    completed = value.get("termination_state") == "completed"
    update_fields = sum(
        1
        for field in ("status", "summary", "next_action")
        if isinstance(update.get(field), str) and update[field].strip()
    )
    unique_teams = len(set(team_order))
    no_duplicate_team = bool(team_order) and unique_teams == len(team_order)
    score = (
        (25 if completed else 0)
        + update_fields * 10
        + min(len(evidence), 3) * 10
        + (15 if no_duplicate_team else 0)
    )
    return {
        "score": score,
        "completed": completed,
        "team_count": len(team_order),
        "unique_team_count": unique_teams,
        "duplicate_team_calls": max(0, len(team_order) - unique_teams),
        "evidence_count": min(len(evidence), 3),
        "requester_update_fields": update_fields,
    }


def record_live_verification(
    experiment: dict[str, Any], result: dict[str, Any], request: str
) -> dict[str, Any]:
    """Attach the next normal-chat run as a baseline comparison.

    Only an identical request is comparable; otherwise the dashboard explains
    why it cannot claim an improvement.
    """
    trials = experiment.get("trials") if isinstance(experiment, dict) else None
    baseline = trials.get("baseline") if isinstance(trials, dict) else None
    baseline_comparison = baseline.get("comparison") if isinstance(baseline, dict) else None
    if not isinstance(baseline_comparison, dict):
        raise ValueError("기준 실행 결과가 없어 적용 후 흐름을 비교할 수 없습니다.")
    baseline_metrics = evaluate_comparison(baseline_comparison)
    applied_metrics = evaluate_comparison(summarise_result(result))
    comparable = str(experiment.get("request", "")).strip() == request.strip()
    delta = applied_metrics["score"] - baseline_metrics["score"]
    state = (
        "not_comparable"
        if not comparable
        else "improved" if delta > 0 else "unchanged" if delta == 0 else "regressed"
    )
    verification = {
        "state": state,
        "baseline": baseline_metrics,
        "applied": applied_metrics,
        "delta": delta,
    }
    experiment["verification"] = verification
    return verification

# Trace-guided Harness Labs.
HARNESS_COMPONENTS = (
    "grounding_document", "agent_prompt", "guardrail",
    "system_prompt", "subagent", "tool", "skill",
)
COMPONENT_LABELS = {
    "grounding_document": "Grounding 문서", "agent_prompt": "Agent Prompt",
    "guardrail": "Guardrail", "system_prompt": "System Prompt",
    "subagent": "Sub-agent", "tool": "Tool 사용 지침", "skill": "Skill",
}
_FORBIDDEN_REVISION_TERMS = (
    "ignore previous", "bypass", "disable guardrail", "secret", "api key",
    "password", "external write", "권한 우회", "가드레일 해제", "비밀값",
    "환경 변수", "외부 쓰기",
)
_LIBRARY_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "harness_labs" / "revision_library.json"
_HARNESS_DOMAINS = {
    "hana-sql": "SAP HANA schema, read-only SQL, or query-result review",
    "procurement": "purchasing, supplier, inventory, supply, or delivery review",
    "manufacturing": "production planning, material intake, manufacturing, or line-operation review",
    "finance": "budget, cost center, profitability, pricing, or exchange-rate review",
    "fnb-general": "a cross-functional or general F&B request not covered above",
}


def _library_path(path: str | Path | None = None) -> Path:
    return Path(path or os.getenv("HARNESS_LABS_LIBRARY_PATH") or _LIBRARY_PATH)


def _safe_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def classify_request_domain(request: str, settings: Settings | None = None) -> str:
    """Let the LLM classify a request for Harness revision selection.

    The returned value is restricted to a fixed, non-authoritative revision
    namespace.  Python validates that namespace but never infers it from
    request keywords.
    """
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Harness 분류에는 비어 있지 않은 요청이 필요합니다.")
    raw = chat_text(
        settings or load_settings(),
        [
            {"role": "system", "content": get_prompt("harness.domain_selector_system")},
            {
                "role": "user",
                "content": render_prompt(
                    "harness.domain_selector_user",
                    request=request.strip(),
                    domains=json.dumps(_HARNESS_DOMAINS, ensure_ascii=False),
                ),
            },
        ],
    )
    value = _json_object(raw, stage="Harness domain selector")
    domain = value.get("domain")
    if not isinstance(domain, str) or domain not in _HARNESS_DOMAINS:
        raise ValueError("Harness domain selector가 허용된 domain을 반환하지 않았습니다.")
    return domain


def trace_summary(
    result: dict[str, Any], chat_log: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Bound and redact the completed trace used by the proposal editor."""
    grounding = result.get("grounding", {}) if isinstance(result, dict) else {}
    searches = grounding.get("searches", []) if isinstance(grounding, dict) else []
    middleware = result.get("middleware", []) if isinstance(result, dict) else []
    artifacts = result.get("artifacts", []) if isinstance(result, dict) else []
    termination = result.get("termination", {}) if isinstance(result, dict) else {}
    team_order = summarise_result(result).get("team_order", [])
    team_counts = {team: team_order.count(team) for team in set(team_order)}
    field_messages = [
        _safe_text(message.get("text"), 240)
        for message in (chat_log or [])
        if isinstance(message, dict) and message.get("kind") == "field"
    ]
    repeated_inputs = sorted({
        message for message in field_messages if message and field_messages.count(message) > 1
    })
    initial_task: dict[str, Any] = {}
    if isinstance(artifacts, list) and artifacts and isinstance(artifacts[0], dict):
        first_decision = artifacts[0].get("orchestration")
        first_plan = first_decision.get("task_plan") if isinstance(first_decision, dict) else {}
        if isinstance(first_decision, dict) and isinstance(first_plan, dict):
            initial_task = {
                "purpose": _safe_text(first_decision.get("purpose"), 280),
                "summary": _safe_text(first_plan.get("summary"), 400),
                "grounding_basis": _safe_text(first_plan.get("grounding_basis"), 400),
                "planned_tasks": [
                    _safe_text(item, 240)
                    for item in first_plan.get("planned_tasks", [])
                    if _safe_text(item, 240)
                ][:3],
            }
    grounding_outcomes: list[dict[str, Any]] = []
    for item in searches[:8] if isinstance(searches, list) else []:
        if not isinstance(item, dict):
            continue
        search_result = item.get("result")
        search_result = search_result if isinstance(search_result, dict) else {}
        evidence = _safe_text(search_result.get("evidence"), 600)
        grounding_outcomes.append({
            "query": _safe_text(item.get("query"), 240),
            "state": _safe_text(search_result.get("state"), 80),
            "document_count": len(search_result.get("document_ids", []))
            if isinstance(search_result.get("document_ids"), list) else 0,
            "evidence_present": bool(evidence),
            "no_relevant_evidence": "관련 근거를 찾지 못했습니다" in evidence,
        })
    artifact_summaries: list[dict[str, str]] = []
    for record in artifacts[:8] if isinstance(artifacts, list) else []:
        if not isinstance(record, dict):
            continue
        artifact = record.get("artifact")
        payload = artifact.get("payload", {}) if isinstance(artifact, dict) else {}
        synthesis = payload.get("team_synthesis", {}) if isinstance(payload, dict) else {}
        sql_generation = payload.get("sql_generation", {}) if isinstance(payload, dict) else {}
        artifact_summaries.append({
            "producer": _safe_text(record.get("producer"), 100),
            "team_summary": _safe_text(synthesis.get("summary") if isinstance(synthesis, dict) else "", 600),
            "sql_explanation": _safe_text(sql_generation.get("explanation") if isinstance(sql_generation, dict) else "", 600),
            "missing_inputs": _safe_text(", ".join(str(item) for item in sql_generation.get("missing_inputs", [])) if isinstance(sql_generation, dict) and isinstance(sql_generation.get("missing_inputs"), list) else "", 400),
        })
    return {
        "context_id": _safe_text(result.get("context_id"), 80),
        "summary": summarise_result(result),
        "observation_count": len(result.get("observations", [])) if isinstance(result.get("observations", []), list) else 0,
        "grounding_queries": [_safe_text(item.get("query"), 240) for item in searches[:8] if isinstance(item, dict)],
        "grounding_outcomes": grounding_outcomes,
        "initial_task": initial_task,
        "middleware_events": [_safe_text(item.get("name"), 80) for item in middleware[:20] if isinstance(item, dict)],
        "artifact_summaries": artifact_summaries,
        "team_counts": team_counts,
        "duplicate_teams": sorted(
            team for team, count in team_counts.items() if count > 1
        ),
        "user_input_count": len(field_messages),
        "repeated_user_inputs": repeated_inputs[:5],
        "termination_reason": _safe_text(
            termination.get("decision", {}).get("reason") if isinstance(termination, dict) and isinstance(termination.get("decision"), dict) else "",
            600,
        ),
    }


def _validated_changes(value: Any, stage: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 3:
        raise ValueError(f"{stage} changes는 1~3개여야 합니다.")
    changes: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise TypeError(f"{stage} change는 객체여야 합니다.")
        component = _safe_text(item.get("component"), 80)
        target = _safe_text(item.get("target"), 120) or "runtime"
        instruction = _safe_text(item.get("instruction"), 900)
        if component not in HARNESS_COMPONENTS or not instruction:
            raise ValueError(f"{stage} change의 component 또는 instruction이 유효하지 않습니다.")
        normalized_instruction = instruction.lower()
        forbidden = [
            term for term in _FORBIDDEN_REVISION_TERMS
            if term in normalized_instruction
        ]
        # Proposal text commonly repeats a safety boundary (for example,
        # "do not disable guardrails" or "외부 쓰기 금지 유지"). That is
        # strengthening/preservation, not a relaxation. Runtime overlays remain
        # bounded regardless; reject a forbidden capability only when it is not
        # explicitly negated or retained by the candidate instruction.
        preserves_boundary = any(
            phrase in normalized_instruction
            for phrase in (
                "do not", "must not", "never", "prohibit", "forbid",
                "금지", "차단", "방지", "유지", "강화", "하지 않",
                "허용하지", "제한",
            )
        )
        if forbidden and not preserves_boundary:
            raise ValueError(f"{stage} change가 안전 경계를 완화합니다.")
        changes.append({"component": component, "target": target, "instruction": instruction})
    return changes


def _proposal_impact(value: Any, changes: list[dict[str, str]]) -> dict[str, Any]:
    """Normalise decision metadata without letting the model lower build risk."""
    raw = value.get("impact") if isinstance(value, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    components = {change["component"] for change in changes}
    # A Grounding revision is a bounded retrieval-focus overlay.  It is sent to
    # the next live repository search without changing the source document or
    # rebuilding the application.
    implementation_components = {"skill", "subagent", "tool"}
    requires_build = bool(raw.get("build_required")) or bool(components & implementation_components)
    return {
        "expected_benefit": _safe_text(raw.get("expected_benefit"), 280)
        or "실행 로그에서 확인된 누락 또는 반복을 줄입니다.",
        "mandatory_controls": _safe_text(raw.get("mandatory_controls"), 280)
        or "기존 승인, 읽기 전용 경계 및 필수 검증을 유지합니다.",
        "build_required": requires_build,
    }


def _proposal_option(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Harness option은 객체여야 합니다.")
    title = _safe_text(value.get("title"), 120)
    rationale = _safe_text(value.get("rationale"), 600)
    evidence = [_safe_text(item, 240) for item in value.get("evidence", []) if _safe_text(item, 240)] if isinstance(value.get("evidence"), list) else []
    if not title or not rationale or not evidence:
        raise ValueError("Harness option에는 title, rationale, evidence가 필요합니다.")
    changes = _validated_changes(value.get("changes"), title)
    return {
        "option_id": f"option_{index}", "title": title, "rationale": rationale,
        "evidence": evidence[:3], "recommended": bool(value.get("recommended")),
        "changes": changes, "impact": _proposal_impact(value, changes),
    }


def analyse_trace(
    request: str,
    result: dict[str, Any],
    settings: Settings | None = None,
    chat_log: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Propose from one real trace. This function deliberately never probes."""
    if not isinstance(request, str) or not request.strip() or not isinstance(result, dict):
        raise ValueError("완료된 A2A 요청과 실행 결과가 필요합니다.")
    trace = trace_summary(result, chat_log)
    domain = classify_request_domain(request, settings)
    raw = chat_text(settings or load_settings(), [
        {"role": "system", "content": get_prompt("harness.trace_editor_system")},
        {"role": "user", "content": render_prompt("harness.trace_editor_user", request=request.strip(), domain=domain, trace=json.dumps(trace, ensure_ascii=False))},
    ])
    value = _json_object(raw, stage="Harness trace editor")
    decision, rationale = _safe_text(value.get("decision"), 40), _safe_text(value.get("rationale"), 600)
    evidence = [_safe_text(item, 240) for item in value.get("evidence", []) if _safe_text(item, 240)] if isinstance(value.get("evidence"), list) else []
    if decision not in {"propose", "no_change", "insufficient_evidence"} or not rationale:
        raise ValueError("Harness trace editor의 decision 또는 rationale이 유효하지 않습니다.")
    if decision != "propose":
        return {"trace_id": trace["context_id"] or str(uuid4()), "request": request.strip(), "domain": domain, "decision": decision, "rationale": rationale, "evidence": evidence[:4], "options": [], "trace": trace}
    raw_options = value.get("options")
    if not isinstance(raw_options, list) or not 2 <= len(raw_options) <= 4:
        raise ValueError("개선 제안은 2~4개 option이 필요합니다.")
    options = [_proposal_option(item, index + 1) for index, item in enumerate(raw_options)]
    recommended = [option for option in options if option["recommended"]]
    if len(recommended) != 1:
        for option in options:
            option["recommended"] = False
        options[0]["recommended"] = True
    options.sort(key=lambda item: not item["recommended"])
    for index, option in enumerate(options, start=1):
        option["option_id"] = f"option_{index}"
    return {"trace_id": trace["context_id"] or str(uuid4()), "request": request.strip(), "domain": domain, "decision": decision, "rationale": rationale, "evidence": evidence[:4], "options": options, "trace": trace}


def load_revision_library(path: str | Path | None = None) -> dict[str, Any]:
    source = _library_path(path)
    if not source.exists():
        return {"schema_version": 1, "revisions": [], "active_by_domain": {}}
    try:
        library = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Harness Labs revision library를 읽을 수 없습니다.") from error
    if not isinstance(library, dict) or not isinstance(library.get("revisions"), list) or not isinstance(library.get("active_by_domain"), dict):
        raise RuntimeError("Harness Labs revision library 형식이 유효하지 않습니다.")
    return library


def _save_library(library: dict[str, Any], path: str | Path | None = None) -> None:
    target = _library_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(library, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def overlay_text(changes: list[dict[str, str]]) -> str:
    lines = ["Runtime Harness revision (human-approved):"]
    lines.extend(f"[{COMPONENT_LABELS[change['component']]} · {change['target']}] {change['instruction']}" for change in changes)
    return "\n".join(lines)


def grounding_overlay_text(changes: list[dict[str, str]]) -> str:
    """Return only human-approved Grounding guidance for the live search.

    This is deliberately not a document mutation: the repository stays
    unchanged and the overlay is recorded in the revision library.
    """
    lines = [
        f"[{change['target']}] {change['instruction']}"
        for change in changes
        if change.get("component") == "grounding_document"
    ]
    return "\n".join(lines)[:MAX_HARNESS_ADDENDUM_CHARS]


def apply_human_selection(analysis: dict[str, Any], option_id: str, comment: str = "", *, path: str | Path | None = None) -> dict[str, Any]:
    if not isinstance(analysis, dict) or analysis.get("decision") != "propose":
        raise ValueError("채택할 수 있는 Harness 개선안이 없습니다.")
    option = next((item for item in analysis.get("options", []) if isinstance(item, dict) and item.get("option_id") == option_id), None)
    if option is None:
        raise ValueError("선택한 Harness 개선안을 찾을 수 없습니다.")
    clean_comment = _safe_text(comment, 600)
    if any(term in clean_comment.lower() for term in _FORBIDDEN_REVISION_TERMS):
        raise ValueError("Comment가 안전 경계를 완화합니다.")
    changes = [dict(change) for change in option["changes"]]
    if clean_comment:
        changes.append({"component": "system_prompt", "target": "human-review", "instruction": f"Human reviewer comment: {clean_comment}"})
    library, domain = load_revision_library(path), str(analysis["domain"])
    parent_id = library["active_by_domain"].get(domain)
    impact = _proposal_impact(option, changes)
    revision = {
        "revision_id": str(uuid4()), "domain": domain, "parent_revision_id": parent_id,
        "trace_id": _safe_text(analysis.get("trace_id"), 100), "request": _safe_text(analysis.get("request"), 600),
        "title": option["title"], "recommended": bool(option.get("recommended")), "rationale": option["rationale"],
        "evidence": option["evidence"], "changes": changes, "comment": clean_comment,
        "impact": impact, "build_required": impact["build_required"],
        "build_status": "pending" if impact["build_required"] else "runtime_ready",
        "status": "active", "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    for prior in library["revisions"]:
        if isinstance(prior, dict) and prior.get("revision_id") == parent_id:
            prior["status"] = "superseded"
    library["revisions"].append(revision)
    library["active_by_domain"][domain] = revision["revision_id"]
    _save_library(library, path)
    return {
        **revision,
        "overlay": overlay_text(changes),
        "grounding_overlay": grounding_overlay_text(changes),
    }


def build_revision_artifact(
    revision: dict[str, Any], *, directory: str | Path | None = None
) -> Path:
    """Stage a reviewable build manifest; never build or deploy automatically."""
    if not isinstance(revision, dict) or not isinstance(revision.get("revision_id"), str):
        raise ValueError("Build artifact에는 저장된 Harness revision이 필요합니다.")
    root = Path(directory) if directory is not None else _library_path().parent / "builds"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{revision['revision_id']}.json"
    manifest = {
        "schema_version": 1,
        "revision_id": revision["revision_id"],
        "domain": revision.get("domain"),
        "title": revision.get("title"),
        "changes": revision.get("changes", []),
        "impact": revision.get("impact", {}),
        "deployment_status": "staged",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def active_runtime_overlays_for_request(
    request: str,
    settings: Settings | None = None,
    *,
    path: str | Path | None = None,
) -> tuple[str, str]:
    """Return orchestration and Grounding overlays from one active revision."""
    library = load_revision_library(path)
    if not library["active_by_domain"]:
        return "", ""
    domain = classify_request_domain(request, settings)
    active_id = library["active_by_domain"].get(domain)
    revision = next((item for item in library["revisions"] if isinstance(item, dict) and item.get("revision_id") == active_id), None)
    if not isinstance(revision, dict) or revision.get("status") != "active" or not isinstance(revision.get("changes"), list):
        return "", ""
    changes = revision["changes"]
    return overlay_text(changes), grounding_overlay_text(changes)


def active_overlay_for_request(
    request: str,
    settings: Settings | None = None,
    *,
    path: str | Path | None = None,
) -> str:
    """Return an active orchestration overlay after domain classification."""
    return active_runtime_overlays_for_request(request, settings, path=path)[0]


def rollback_active_revision(domain: str, *, path: str | Path | None = None) -> dict[str, Any]:
    library, active_id = load_revision_library(path), None
    active_id = library["active_by_domain"].get(domain)
    revision = next((item for item in library["revisions"] if isinstance(item, dict) and item.get("revision_id") == active_id), None)
    if not isinstance(revision, dict):
        raise ValueError("롤백할 활성 Harness revision이 없습니다.")
    revision["status"] = "rolled_back"
    parent = revision.get("parent_revision_id")
    if isinstance(parent, str):
        library["active_by_domain"][domain] = parent
        for item in library["revisions"]:
            if isinstance(item, dict) and item.get("revision_id") == parent:
                item["status"] = "active"
    else:
        library["active_by_domain"].pop(domain, None)
    _save_library(library, path)
    return revision

