"""Local-only Gradio UI for the AI Core environment notebook."""
from __future__ import annotations

import os
from typing import Any

from lab_common.ai_core import list_running_deployments
from lab_common.config import REPOSITORY_ROOT, Settings, load_settings


ENV_PATH = REPOSITORY_ROOT / ".env"


def _gradio():
    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError("Gradio가 없습니다. python3 -m pip install --user -r requirements.txt 를 실행하세요.") from error
    return gr


def _masked(value: str) -> str:
    return "configured" if value else "missing"


def settings_summary(settings: Settings | None = None) -> str:
    settings = settings or load_settings()
    return (
        f"AI Core URL: {'configured' if settings.base_url else 'missing'}\n"
        f"Auth URL: {'configured' if settings.auth_url else 'missing'}\n"
        f"Client ID: {_masked(settings.client_id)}\n"
        f"Client secret: {_masked(settings.client_secret)}\n"
        f"Resource group: {settings.resource_group}\n"
        f"LLM model: {settings.llm_model}\n"
        f"Embedding model: {os.getenv('EMBED_MODEL', 'not set')}"
    )


def _write_env(updates: dict[str, str]) -> None:
    """Update only supplied values, preserving comments and unrelated configuration."""
    original = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    lines = original.splitlines()
    remaining = dict(updates)
    rewritten: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in remaining:
            rewritten.append(f"{key}={remaining.pop(key)}")
        else:
            rewritten.append(line)
    if remaining:
        if rewritten and rewritten[-1]:
            rewritten.append("")
        rewritten.extend(f"{key}={value}" for key, value in remaining.items())
    ENV_PATH.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def save_settings(
    base_url: str, auth_url: str, client_id: str, client_secret: str,
    resource_group: str, llm_model: str, embed_model: str,
) -> str:
    """Persist nonblank form fields and make them active in this kernel."""
    fields = {
        "AICORE_BASE_URL": base_url.strip(),
        "AICORE_AUTH_URL": auth_url.strip(),
        "AICORE_CLIENT_ID": client_id.strip(),
        "AICORE_CLIENT_SECRET": client_secret.strip(),
        "AICORE_RESOURCE_GROUP": resource_group.strip(),
        "LLM_MODEL": llm_model.strip(),
        "EMBED_MODEL": embed_model.strip(),
    }
    updates = {key: value for key, value in fields.items() if value}
    if not updates:
        return "저장할 값이 없습니다. 빈 입력은 기존 .env 값을 유지합니다."
    _write_env(updates)
    os.environ.update(updates)
    return "저장했습니다. 비밀값은 표시하지 않습니다.\n\n" + settings_summary(load_settings())


def deployment_summary() -> str:
    try:
        deployments = list_running_deployments(load_settings())
    except Exception as error:
        return f"연결 확인 실패: {type(error).__name__}: {error}"
    if not deployments:
        return "RUNNING deployment가 없습니다."

    def model_name(deployment: dict[str, Any]) -> str:
        return str(
            deployment.get("details", {})
            .get("resources", {})
            .get("backend_details", {})
            .get("model", {})
            .get("name", "")
        )

    return "\n".join(
        f"- {model_name(item) or '(model name unavailable)'} | "
        f"{item.get('scenarioId', 'unknown')} | {item.get('status')}"
        for item in deployments
    )


def build_configuration_ui():
    """Create a local-only AI Core configuration and deployment-check UI."""
    gr = _gradio()
    current = load_settings()
    with gr.Blocks(fill_width=True) as app:
        gr.Markdown(
            "### AI Core 설정 UI\n"
            "빈 입력은 기존 `.env` 값을 유지합니다. client secret은 화면에 다시 표시하지 않습니다."
        )
        with gr.Row():
            with gr.Column():
                base_url = gr.Textbox(label="AI Core base URL", value=current.base_url)
                auth_url = gr.Textbox(label="Auth URL", value=current.auth_url)
                client_id = gr.Textbox(label="Client ID", value=current.client_id)
                client_secret = gr.Textbox(label="Client secret (blank keeps existing)", type="password")
            with gr.Column():
                resource_group = gr.Textbox(label="Resource group", value=current.resource_group)
                llm_model = gr.Textbox(label="LLM model", value=current.llm_model)
                embed_model = gr.Textbox(label="Embedding model", value=os.getenv("EMBED_MODEL", ""))
                save = gr.Button("Save local settings", variant="primary")
                check = gr.Button("Check RUNNING deployments")
        status = gr.Textbox(label="Configuration status", value=settings_summary(current), lines=8)
        deployments = gr.Textbox(label="Deployment status", lines=8)
        save.click(
            save_settings,
            inputs=[base_url, auth_url, client_id, client_secret, resource_group, llm_model, embed_model],
            outputs=status,
        )
        check.click(deployment_summary, outputs=deployments)
    return app
