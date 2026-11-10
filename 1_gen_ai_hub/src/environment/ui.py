"""Local-only Gradio environment checker used by the first Hands-on notebook."""
from __future__ import annotations

import os
from html import escape
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .lesson_support.ai_core import list_running_deployments
from .lesson_support.config import REPOSITORY_ROOT, load_settings
from .lesson_support.grounding_repository import list_documents


ENV_PATH = REPOSITORY_ROOT / ".env"


@dataclass(frozen=True)
class EnvironmentField:
    key: str
    label: str
    required: bool = True


@dataclass(frozen=True)
class EnvironmentCard:
    name: str
    title: str
    optional: bool
    fields: tuple[EnvironmentField, ...]


CARDS = (
    EnvironmentCard(
        name="AI CORE",
        title="AI Core와 모델",
        optional=False,
        fields=(
            EnvironmentField("AICORE_BASE_URL", "AI Core base URL"),
            EnvironmentField("AICORE_AUTH_URL", "Auth URL"),
            EnvironmentField("AICORE_CLIENT_ID", "Client ID"),
            EnvironmentField("AICORE_CLIENT_SECRET", "Client secret"),
            EnvironmentField("AICORE_RESOURCE_GROUP", "Resource group"),
            EnvironmentField("AICORE_ORCHESTRATION_DEPLOYMENT_URL", "Orchestration deployment URL", False),
            EnvironmentField("LLM_MODEL", "LLM model"),
            EnvironmentField("LLM_SEED", "LLM seed"),
            EnvironmentField("AICORE_LLM_DEPLOYMENT_ID", "LLM deployment ID", False),
            EnvironmentField("EMBED_MODEL", "Embedding model"),
            EnvironmentField("RERANK_MODEL", "Rerank model"),
        ),
    ),
    EnvironmentCard(
        name="OBJECT Store",
        title="SAP BTP Object Storage",
        optional=False,
        fields=(
            EnvironmentField("OBJECT_STORAGE_ENDPOINT", "S3 endpoint"),
            EnvironmentField("OBJECT_STORAGE_ACCESS_KEY_ID", "Access key ID"),
            EnvironmentField("OBJECT_STORAGE_SECRET_ACCESS_KEY", "Secret access key"),
            EnvironmentField("OBJECT_STORAGE_BUCKET", "Bucket"),
            EnvironmentField("OBJECT_STORAGE_REGION", "Region", False),
            EnvironmentField("OBJECT_STORAGE_PREFIX", "Object prefix", False),
        ),
    ),
    EnvironmentCard(
        name="Grounding",
        title="Vector Grounding",
        optional=False,
        fields=(EnvironmentField("GROUNDING_REPOSITORY_ID", "Grounding repository ID"),),
    ),
)
CARD_BY_NAME = {card.name: card for card in CARDS}
ENVIRONMENT_KEYS = tuple(field.key for card in CARDS for field in card.fields)

_STATUS_CSS = """
.environment-status { display: grid; gap: 7px; margin-top: 10px; }
.environment-status__item { align-items: center; background: #f8f9fa; border-radius: 8px; display: grid; gap: 7px; grid-template-columns: 10px minmax(0, 1fr) auto; padding: 7px 9px; }
.environment-status__light { border-radius: 50%; height: 10px; width: 10px; }
.environment-status__light--ready { background: #34a853; box-shadow: 0 0 0 3px #e6f4ea; }
.environment-status__light--optional { background: #f9ab00; box-shadow: 0 0 0 3px #fef7e0; }
.environment-status__light--error { background: #ea4335; box-shadow: 0 0 0 3px #fce8e6; }
.environment-status__name { color: #202124; font-size: .86em; font-weight: 700; }
.environment-status__message { color: #5f6368; font-size: .78em; text-align: right; }
.environment-card { background: transparent !important; border: 0 !important; box-shadow: none !important; gap: 14px !important; padding: 0 !important; }
.environment-card-title { margin: 0 0 2px !important; }
.environment-card-title h3 { color: #202124; font-size: 1.15rem; font-weight: 650; margin: 0 !important; }
.environment-card-footer { align-items: center !important; background: transparent !important; border-top: 1px solid #e8eaed; gap: 8px !important; margin: 8px 0 0; padding-top: 12px; }
.environment-card-footer button { border-radius: 6px !important; box-shadow: none !important; font-size: .9rem !important; min-height: 36px; }
.environment-check-button button { background: #fff !important; border: 1px solid #dadce0 !important; color: #3c4043 !important; }
.environment-save-button button { background: #202124 !important; border: 1px solid #202124 !important; color: #fff !important; }
.environment-save-button button:disabled { background: #f1f3f4 !important; border-color: #f1f3f4 !important; color: #9aa0a6 !important; }
.environment-card-status { color: #5f6368; font-size: .9rem; margin: 0 !important; padding: 0 !important; }
.environment-card-status p { margin: 0 !important; }
@media (max-width: 640px) {
  .environment-card-footer { align-items: stretch !important; flex-direction: column !important; }
  .environment-card-footer > * { width: 100% !important; }
}
"""


def _gradio():
    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError("Gradio가 없습니다. python3 -m pip install --user -r requirements.txt 를 실행하세요.") from error
    return gr


def _light_theme(gr):
    base = gr.themes.Base(primary_hue=gr.themes.colors.blue)
    values = base.to_dict()["theme"]
    return base.set(**{f"{name}_dark": value for name, value in values.items() if not name.endswith("_dark") and f"{name}_dark" in values})


def read_environment_values(env_file: Path = ENV_PATH) -> dict[str, str]:
    """Read managed values from an env file without printing any secret."""
    if not env_file.is_file():
        return {key: "" for key in ENVIRONMENT_KEYS}
    try:
        from dotenv import dotenv_values

        parsed = dotenv_values(env_file)
    except ImportError:
        parsed: dict[str, str] = {}
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                parsed[key.strip().removeprefix("export ")] = value.strip().strip("'\"")
    return {key: str(parsed.get(key) or "").strip() for key in ENVIRONMENT_KEYS}


def _missing_required(card: EnvironmentCard, values: Mapping[str, str]) -> list[str]:
    return [field.key for field in card.fields if field.required and not values.get(field.key, "").strip()]


def validate_card(card: EnvironmentCard, values: Mapping[str, str], *, env_exists: bool = True) -> dict[str, Any]:
    """Return a display-safe setup result for a single configuration card."""
    if not env_exists:
        return {"state": "error", "message": "루트 .env 파일을 찾을 수 없습니다.", "missing": []}

    populated = [field.key for field in card.fields if values.get(field.key, "").strip()]
    if card.optional and not populated:
        return {"state": "optional", "message": "선택", "missing": []}

    missing = _missing_required(card, values)
    errors: list[str] = []
    if missing:
        errors.append("누락: " + ", ".join(missing))

    if errors:
        return {"state": "error", "message": "; ".join(errors), "missing": missing}
    return {"state": "ready", "message": "설정됨", "missing": []}


def environment_status(values: Mapping[str, str], *, env_exists: bool = True) -> dict[str, dict[str, Any]]:
    return {card.name: validate_card(card, values, env_exists=env_exists) for card in CARDS}


def render_environment_summary(statuses: Mapping[str, Mapping[str, Any]]) -> str:
    return "<div class='environment-status'>" + "".join(
        "<div class='environment-status__item'>"
        f"<span class='environment-status__light environment-status__light--{escape(str(result['state']))}'></span>"
        f"<span class='environment-status__name'>{escape(name)}</span>"
        f"<span class='environment-status__message'>{escape(str(result['message']))}</span>"
        "</div>"
        for name, result in statuses.items()
    ) + "</div>"


def card_visibility(selected_card: str) -> tuple[bool, ...]:
    """Return visible state for the cards in sidebar order."""
    return tuple(card.name == selected_card for card in CARDS)


def _write_env(updates: Mapping[str, str], env_file: Path = ENV_PATH) -> list[str]:
    """Update nonblank managed values while preserving comments and unrelated keys."""
    if not env_file.is_file():
        raise FileNotFoundError("루트 .env 파일을 찾을 수 없습니다.")
    selected = {key: str(value).strip() for key, value in updates.items() if key in ENVIRONMENT_KEYS and str(value).strip()}
    if not selected:
        return []
    pending = dict(selected)
    rewritten: list[str] = []
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        rewritten.append(f"{key}={pending.pop(key)}" if key in pending else line)
    if pending:
        if rewritten and rewritten[-1]:
            rewritten.append("")
        rewritten.extend(f"{key}={value}" for key, value in pending.items())
    env_file.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    os.environ.update(selected)
    return list(selected)


def _activate(values: Mapping[str, str]) -> None:
    os.environ.update({key: value for key, value in values.items() if value})


def save_environment_values(values: Mapping[str, str], env_file: Path = ENV_PATH) -> str:
    try:
        saved = _write_env(values, env_file)
    except FileNotFoundError as error:
        return f"저장 실패: {error}"
    if not saved:
        return "저장할 값 없음"
    refreshed = read_environment_values(env_file)
    return "저장됨\n\n" + render_environment_summary(environment_status(refreshed, env_exists=True))


def _probe_ai_core() -> str:
    deployments = list_running_deployments(load_settings())
    return f"RUNNING deployment {len(deployments)}개"


def _probe_object_store() -> str:
    try:
        import boto3
    except ImportError as error:
        raise RuntimeError("boto3가 없습니다. requirements.txt를 설치하세요.") from error
    endpoint = os.environ["OBJECT_STORAGE_ENDPOINT"].strip()
    if "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    options: dict[str, Any] = {
        "service_name": "s3",
        "endpoint_url": endpoint,
        "aws_access_key_id": os.environ["OBJECT_STORAGE_ACCESS_KEY_ID"],
        "aws_secret_access_key": os.environ["OBJECT_STORAGE_SECRET_ACCESS_KEY"],
    }
    if os.getenv("OBJECT_STORAGE_REGION", "").strip():
        options["region_name"] = os.environ["OBJECT_STORAGE_REGION"]
    boto3.client(**options).head_bucket(Bucket=os.environ["OBJECT_STORAGE_BUCKET"])
    return "bucket 접근 확인"


def _probe_grounding() -> str:
    documents = list_documents(load_settings(), os.environ["GROUNDING_REPOSITORY_ID"])
    return f"문서 {len(documents)}개"


def run_card_check(
    card_name: str,
    values: Mapping[str, str],
    *,
    env_exists: bool = True,
    probes: Mapping[str, Callable[[], str]] | None = None,
) -> str:
    """Run the safe check for one selected configuration card."""
    _activate(values)
    card = CARD_BY_NAME[card_name]
    result = validate_card(card, values, env_exists=env_exists)
    if result["state"] == "error":
        return f"❌ {result['message']}"
    if result["state"] == "optional":
        return f"⚪ {result['message']}"
    checks = {
        "AI CORE": _probe_ai_core,
        "OBJECT Store": _probe_object_store,
        "Grounding": _probe_grounding,
    }
    checks.update(probes or {})
    try:
        return "✅ " + checks[card_name]()
    except Exception as error:  # Do not surface driver or credential details.
        return f"❌ 연결 확인 실패: {type(error).__name__}"


def run_environment_checks(
    values: Mapping[str, str],
    *,
    env_exists: bool = True,
    probes: Mapping[str, Callable[[], str]] | None = None,
) -> dict[str, str]:
    """Run only the approved, read-only checks and return display-safe results."""
    return {
        card.name: run_card_check(card.name, values, env_exists=env_exists, probes=probes)
        for card in CARDS
    }


def build_configuration_ui():
    """Create the local-only, sidebar-driven environment checker."""
    gr = _gradio()
    values = read_environment_values()
    env_exists = ENV_PATH.is_file()
    _activate(values)
    initial_statuses = environment_status(values, env_exists=env_exists)

    with gr.Blocks(css=_STATUS_CSS, fill_width=True, title="Hands-on 환경 점검", theme=_light_theme(gr)) as app:
        with gr.Sidebar(open=True, width=290, position="left"):
            gr.Markdown("## 환경 설정")
            with gr.Column():
                navigation_buttons = [
                    gr.Button(card.name, variant="primary" if position == 0 else "secondary")
                    for position, card in enumerate(CARDS)
                ]
            overall_status = gr.HTML(render_environment_summary(initial_statuses))

        components: dict[str, Any] = {}
        card_groups: list[Any] = []
        card_statuses: list[Any] = []
        card_actions: list[tuple[EnvironmentCard, Any, Any, Any]] = []
        for position, card in enumerate(CARDS):
            with gr.Column(elem_classes="environment-card", visible=position == 0) as group:
                card_groups.append(group)
                gr.Markdown(f"### {card.title}", elem_classes="environment-card-title")
                for start in range(0, len(card.fields), 2):
                    with gr.Row():
                        for field in card.fields[start:start + 2]:
                            label = field.label if field.required else f"{field.label} (선택)"
                            components[field.key] = gr.Textbox(label=label, value=values[field.key])
                with gr.Row(equal_height=True, elem_classes="environment-card-footer"):
                    card_status = gr.Markdown(initial_statuses[card.name]["message"], elem_classes="environment-card-status")
                    check_button = gr.Button("환경 연결 확인", elem_classes="environment-check-button", min_width=150, scale=0)
                    save_button = gr.Button("로컬 .env 저장", elem_classes="environment-save-button", interactive=False, min_width=140, scale=0)
                card_statuses.append(card_status)
                card_actions.append((card, save_button, check_button, card_status))

        def show_card(selected: str):
            return [
                *[gr.update(visible=visible) for visible in card_visibility(selected)],
                *[gr.update(variant="primary" if card.name == selected else "secondary") for card in CARDS],
            ]

        def save_handler(card_name: str, keys: tuple[str, ...]):
            def save_card(*form_values: str):
                message = save_environment_values(dict(zip(keys, form_values, strict=True)))
                refreshed = read_environment_values()
                statuses = environment_status(refreshed, env_exists=ENV_PATH.is_file())
                card_message = message if message.startswith("저장 실패") or message == "저장할 값 없음" else statuses[card_name]["message"]
                return render_environment_summary(statuses), card_message
            return save_card

        def check_handler(card_name: str, keys: tuple[str, ...]):
            def check_card(*form_values: str):
                current_values = read_environment_values()
                current_values.update(dict(zip(keys, form_values, strict=True)))
                result = run_card_check(card_name, current_values, env_exists=ENV_PATH.is_file())
                return (
                    render_environment_summary(environment_status(current_values, env_exists=ENV_PATH.is_file())),
                    result,
                    gr.update(interactive=result.startswith("✅")),
                )
            return check_card

        for card, button in zip(CARDS, navigation_buttons, strict=True):
            button.click(
                lambda selected=card.name: show_card(selected),
                outputs=[*card_groups, *navigation_buttons],
            )
        for card, save_button, check_button, card_status in card_actions:
            keys = tuple(field.key for field in card.fields)
            inputs = [components[key] for key in keys]
            save_button.click(save_handler(card.name, keys), inputs=inputs, outputs=[overall_status, card_status])
            check_button.click(check_handler(card.name, keys), inputs=inputs, outputs=[overall_status, card_status, save_button])
            for component in inputs:
                component.change(lambda _: gr.update(interactive=False), inputs=component, outputs=save_button)
    return app
