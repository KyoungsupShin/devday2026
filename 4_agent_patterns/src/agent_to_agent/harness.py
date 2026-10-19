"""A small, runtime-only Harness² lab for the F&B A2A notebook.

The module never edits prompt resources, Team cards, Tool permissions, or local
data. It proposes bounded orchestration supplements, probes them through the
existing public handoff API, and leaves final adoption to a human reviewer.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from typing import Any

from lab_common.ai_core import chat_text
from lab_common.config import Settings, load_settings

from .catalog import DEFAULT_REQUEST
from .orchestration import MAX_HARNESS_ADDENDUM_CHARS, run_handoff
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


def propose_variants(request: str, baseline: dict[str, Any], settings: Settings) -> list[dict[str, str]]:
    """Ask the editor for exactly two constrained orchestration supplements."""
    raw = chat_text(settings, [
        {"role": "system", "content": get_prompt("harness.editor_system")},
        {"role": "user", "content": render_prompt(
            "harness.editor_user", request=request,
            baseline=json.dumps(summarise_result(baseline), ensure_ascii=False),
        )},
    ])
    value = _json_object(raw, stage="Harness editor")
    variants = value.get("variants")
    if not isinstance(variants, list) or len(variants) != 2:
        raise ValueError("Harness editor는 정확히 2개의 variants를 반환해야 합니다.")
    return [_variant(item, stage="Harness editor") for item in variants]


def compose_variant(request: str, probes: list[dict[str, Any]], settings: Settings) -> dict[str, str]:
    """Compose one supplement from observed probe summaries, not a score."""
    raw = chat_text(settings, [
        {"role": "system", "content": get_prompt("harness.composer_system")},
        {"role": "user", "content": render_prompt(
            "harness.composer_user", request=request,
            probes=json.dumps(probes, ensure_ascii=False),
        )},
    ])
    return _variant(_json_object(raw, stage="Harness composer"), stage="Harness composer")


def _trial(variant_id: str, *, result: dict[str, Any] | None = None,
           variant: dict[str, str] | None = None, error: Exception | None = None) -> dict[str, Any]:
    return {
        "variant_id": variant_id,
        "status": "ok" if result is not None else "failed",
        "result": result,
        "comparison": summarise_result(result) if result is not None else {},
        "variant": variant,
        "error": str(error)[:500] if error else "",
    }


def _run(runner: Runner, request: str, settings: Settings | None,
         agent_urls: dict[str, str] | None, addendum: str | None = None) -> dict[str, Any]:
    return runner(request, settings=settings, agent_urls=agent_urls, harness_addendum=addendum)


def _anonymous_rows(trials: dict[str, dict[str, Any]], randomizer: random.Random | None) -> tuple[list[dict[str, Any]], dict[str, str]]:
    visible = [variant_id for variant_id in _VARIANT_IDS if variant_id in trials]
    (randomizer or random.SystemRandom()).shuffle(visible)
    mapping = dict(zip([chr(ord("A") + index) for index in range(len(visible))], visible, strict=True))
    rows = [
        {"candidate_id": candidate_id, **trials[variant_id]["comparison"],
         "status": trials[variant_id]["status"], "error": trials[variant_id]["error"]}
        for candidate_id, variant_id in mapping.items()
    ]
    return rows, mapping


def run_harness_experiment(
    request: str = DEFAULT_REQUEST, *, baseline_result: dict[str, Any] | None = None,
    settings: Settings | None = None, agent_urls: dict[str, str] | None = None,
    runner: Runner | None = None, randomizer: random.Random | None = None,
) -> dict[str, Any]:
    """Run the baseline → two probes → compose learning loop.

    A supplied baseline is reused so the notebook performs four total A2A
    executions, including its visible baseline cell. Failed proposals are never
    passed to the executor and remain visible as failed comparison rows.
    """
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request는 비어 있지 않은 문자열이어야 합니다.")
    active_settings = settings or load_settings()
    execute, request = runner or run_handoff, request.strip()
    trials: dict[str, dict[str, Any]] = {}
    try:
        baseline = baseline_result or _run(execute, request, settings, agent_urls)
        trials["baseline"] = _trial("baseline", result=baseline)
    except Exception as error:  # noqa: BLE001 - keep a failed baseline visible to the learner.
        trials["baseline"] = _trial("baseline", error=error)
        rows, mapping = _anonymous_rows(trials, randomizer)
        return {"request": request, "trials": trials, "comparison": rows, "anonymous_map": mapping}
    try:
        variants = propose_variants(request, baseline, active_settings)
    except Exception as error:  # noqa: BLE001 - invalid editor output must not abort the comparison.
        for variant_id in ("candidate_1", "candidate_2", "composed"):
            trials[variant_id] = _trial(variant_id, error=error)
        rows, mapping = _anonymous_rows(trials, randomizer)
        return {"request": request, "trials": trials, "comparison": rows, "anonymous_map": mapping}
    probes: list[dict[str, Any]] = []
    for variant_id, variant in zip(("candidate_1", "candidate_2"), variants, strict=True):
        try:
            result = _run(execute, request, settings, agent_urls, variant["addendum"])
            trials[variant_id] = _trial(variant_id, result=result, variant=variant)
            probes.append({"candidate": variant_id, "outcome": trials[variant_id]["comparison"]})
        except Exception as error:  # noqa: BLE001 - a failed probe is a comparison outcome.
            trials[variant_id] = _trial(variant_id, variant=variant, error=error)
    try:
        composed = compose_variant(request, probes, active_settings)
        result = _run(execute, request, settings, agent_urls, composed["addendum"])
        trials["composed"] = _trial("composed", result=result, variant=composed)
    except Exception as error:  # noqa: BLE001 - preserve composer failures as a failed trial.
        trials["composed"] = _trial("composed", error=error)
    rows, mapping = _anonymous_rows(trials, randomizer)
    return {"request": request, "trials": trials, "comparison": rows, "anonymous_map": mapping}


def adopt_variant(experiment: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    """Record a human's session-only selection and reveal generated context."""
    mapping = experiment.get("anonymous_map") if isinstance(experiment, dict) else None
    trials = experiment.get("trials") if isinstance(experiment, dict) else None
    if not isinstance(mapping, dict) or not isinstance(trials, dict):
        raise TypeError("유효한 Harness² 실험 결과가 아닙니다.")
    chosen_id = str(candidate_id).strip().upper()
    variant_id = mapping.get(chosen_id)
    if not isinstance(variant_id, str) or variant_id not in trials:
        raise ValueError("비교표에 있는 후보 ID를 선택하세요.")
    trial = trials[variant_id]
    if trial.get("status") != "ok":
        raise ValueError("실패한 후보는 채택할 수 없습니다.")
    variant = trial.get("variant")
    adopted = {
        "candidate_id": chosen_id, "variant_id": variant_id,
        "active_harness": variant.get("addendum", "") if isinstance(variant, dict) else "",
        "title": variant.get("title", "기준 하네스") if isinstance(variant, dict) else "기준 하네스",
        "rationale": variant.get("rationale", "기준 실행을 유지합니다.") if isinstance(variant, dict) else "기준 실행을 유지합니다.",
    }
    experiment["adoption"] = adopted
    return adopted

