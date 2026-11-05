"""Gradio UI adapter for the 02 Grounding notebook."""
from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any

from .lesson_support.config import load_settings, save_grounding_repository_id
from .lesson_support.grounding_repository import delete_document, list_documents, upload_text_document

from .lab_core import run_vector_grounded_query_with_trace
from .object_storage import ObjectStorageConfig, upload_markdown_to_object_storage_and_grounding


_UI_CSS = """
.document-card { padding: 12px; margin: 8px 0; border: 1px solid #d7e3f4; border-radius: 10px; background: #f8fbff; }
.document-card strong, .document-card small, .document-card span { display: block; }
.document-card strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #174ea6; }
.document-card small { margin-top: 5px; color: #5f6368; }
.document-card span { margin-top: 7px; font-size: .82em; color: #1a73e8; }
.document-empty { color: #5f6368; font-size: .92em; }
"""

_DEFAULT_SOP_QUESTION = "현장 작업자의 설비 부품 구매 요청은 어떤 순서로 검토해야 하나요?"


def _document_id(document: dict[str, Any]) -> str:
    value = document.get("id") or document.get("documentId")
    if value:
        return str(value)
    for item in document.get("metadata", []):
        if item.get("key") == "id" and item.get("value"):
            return str(item["value"][0])
    return ""


def _repository_id_or_error(repository_id: str, default_repository_id: str) -> str:
    value = (repository_id or default_repository_id).strip()
    if not value:
        raise ValueError("Repository ID를 입력하거나 .env에 GROUNDING_REPOSITORY_ID를 설정하세요.")
    return value


def _document_stack(settings: Any, repository_id: str) -> tuple[str, list[str]]:
    cards: list[str] = []
    ids: list[str] = []
    for document in list_documents(settings, repository_id):
        doc_id = _document_id(document)
        if doc_id:
            ids.append(doc_id)
        metadata = " · ".join(
            f"{item.get('key')}: {', '.join(map(str, item.get('value', [])))}"
            for item in document.get("metadata", [])
        )
        chunk_count = len(document.get("chunks", []))
        cards.append(
            "<article class='document-card'><strong>" + html.escape(doc_id or "ID 없음") +
            "</strong><small>" + html.escape(metadata or "metadata 없음") +
            f"</small><span>{chunk_count} chunks</span></article>"
        )
    return "".join(cards) if cards else "<p class='document-empty'>업로드된 문서가 없습니다.</p>", ids


def build_grounding_ui():
    """Build the local Custom Repository Grounding UI used by the notebook."""
    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError("Gradio가 없습니다. requirements.txt를 설치하세요.") from error

    manager_settings = load_settings()
    default_repository_id = os.getenv("GROUNDING_REPOSITORY_ID", "")

    def refresh_documents(repository_id: str):
        try:
            repo_id = _repository_id_or_error(repository_id, default_repository_id)
            stack, ids = _document_stack(manager_settings, repo_id)
            return f"{len(ids)}개 문서를 찾았습니다.", stack, gr.Dropdown(choices=ids, value=None)
        except Exception as error:
            return f"문서 목록 조회 실패: {type(error).__name__}: {error}", "", gr.Dropdown(choices=[], value=None)

    def save_repository(repository_id: str):
        try:
            repo_id = _repository_id_or_error(repository_id, default_repository_id)
            save_grounding_repository_id(repo_id)
            return repo_id, "Repository ID를 루트 .env에 저장했습니다."
        except Exception as error:
            return repository_id, f"저장 실패: {type(error).__name__}: {error}"

    def upload_directly(repository_id: str, file_path: str | None):
        try:
            if not file_path:
                raise ValueError("업로드할 .txt 또는 .md 파일을 선택하세요.")
            path = Path(file_path)
            if path.suffix.lower() not in {".txt", ".md"}:
                raise ValueError("현재는 UTF-8 .txt와 .md 파일만 지원합니다.")
            repo_id = _repository_id_or_error(repository_id, default_repository_id)
            upload_text_document(manager_settings, repo_id, filename=path.name, text=path.read_text(encoding="utf-8"))
            stack, ids = _document_stack(manager_settings, repo_id)
            return f"{path.name} 업로드를 요청했습니다. 인덱싱에는 잠시 시간이 걸릴 수 있습니다.", stack, gr.Dropdown(choices=ids, value=None)
        except Exception as error:
            return f"업로드 실패: {type(error).__name__}: {error}", "", gr.Dropdown()

    def upload_via_object_storage(repository_id: str, file_path: str | None, object_key: str):
        try:
            if not file_path:
                raise ValueError("업로드할 .md 파일을 선택하세요.")
            repo_id = _repository_id_or_error(repository_id, default_repository_id)
            result = upload_markdown_to_object_storage_and_grounding(
                manager_settings, repo_id, file_path=file_path, requested_key=object_key
            )
            stack, ids = _document_stack(manager_settings, repo_id)
            return (
                f"Object Storage s3://{result.bucket}/{result.object_key}에 저장하고 Grounding 인덱싱을 요청했습니다. "
                "인덱싱에는 잠시 시간이 걸릴 수 있습니다.", stack, gr.Dropdown(choices=ids, value=None)
            )
        except Exception as error:
            return f"Object Storage 업로드/인덱싱 실패: {type(error).__name__}: {error}", "", gr.Dropdown()

    def remove_document(repository_id: str, selected_document_id: str | None):
        try:
            repo_id = _repository_id_or_error(repository_id, default_repository_id)
            delete_document(manager_settings, repo_id, selected_document_id or "")
            stack, ids = _document_stack(manager_settings, repo_id)
            return f"{selected_document_id} Grounding 문서를 삭제했습니다. Object Storage 원본은 유지됩니다.", stack, gr.Dropdown(choices=ids, value=None)
        except Exception as error:
            return f"삭제 실패: {type(error).__name__}: {error}", "", gr.Dropdown()

    def run_grounding(repository_id: str, user_query: str) -> dict[str, Any]:
        try:
            repo_id = _repository_id_or_error(repository_id, default_repository_id)
            return run_vector_grounded_query_with_trace(
                user_query, load_settings(), repository_id=repo_id
            )
        except Exception as error:
            return {"error": f"Grounding 호출 실패: {type(error).__name__}: {error}"}

    storage = ObjectStorageConfig.from_environment()
    storage_status = (
        f"설정됨: bucket={storage.bucket}, prefix={storage.prefix or '/'}"
        if not storage.missing_fields() else
        "미설정: " + ", ".join(storage.missing_fields()) + " (.env 또는 VCAP_SERVICES를 설정하세요.)"
    )
    with gr.Blocks(css=_UI_CSS, title="Custom Repository Grounding") as app:
        with gr.Sidebar(open=False, width=280, position="left"):
            gr.Markdown("## Repository")
            repository_input = gr.Textbox(label="Repository ID", value=default_repository_id, placeholder="Grounding Management 카드의 UUID")
            with gr.Row():
                save_repository_button = gr.Button("`.env`에 저장", variant="primary")
                refresh_button = gr.Button("새로고침")
            repository_status = gr.Textbox(label="상태", lines=4, interactive=False)
            gr.Markdown("### Uploaded documents")
            document_list = gr.HTML("<p class='document-empty'>새로고침을 눌러 문서를 불러오세요.</p>")
        gr.Markdown("# Custom Repository Grounding")
        with gr.Tabs():
            with gr.Tab("Direct upload"):
                gr.Markdown(
                    "UTF-8 `.txt` 또는 `.md` SOP 문서를 vector repository에 직접 인덱싱합니다. "
                    "예제: `data/context/collaboration_sop.md`"
                )
                direct_file = gr.File(label="문서 파일", file_types=[".txt", ".md"], type="filepath")
                direct_button = gr.Button("문서 업로드", variant="primary")
            with gr.Tab("Object Storage → Grounding"):
                gr.Markdown(
                    "UTF-8 Markdown 원본을 SAP BTP Object Storage에 보관한 뒤, 같은 내용을 선택한 vector repository에 인덱싱합니다. "
                    "Object Storage 원본을 근거로 직접 검색하는 것이 아니라, 인덱싱된 text chunk가 Grounding에 사용됩니다."
                )
                gr.Textbox(label="Object Storage 설정", value=storage_status, interactive=False, lines=3)
                object_file = gr.File(label="Markdown 파일", file_types=[".md"], type="filepath")
                object_key = gr.Textbox(label="Object key (선택)", placeholder="비우면 OBJECT_STORAGE_PREFIX/파일명")
                object_button = gr.Button("Object Storage 저장 및 Grounding 포함", variant="primary")
            with gr.Tab("Ground"):
                gr.Markdown(
                    "업로드한 SOP 문서만 근거로 답합니다. 문서 밖의 승인·구매·시스템 변경은 결정하지 않습니다."
                )
                question = gr.Textbox(
                    label="SOP 질문", lines=3, value=_DEFAULT_SOP_QUESTION,
                    placeholder="SOP 절차 또는 역할에 관해 질문하세요.",
                )
                ask_button = gr.Button("Grounded answer 생성", variant="primary")
                answer = gr.JSON(label="Grounded answer and evidence", min_height=320)
            with gr.Tab("Delete"):
                gr.Markdown("Grounding 인덱스 삭제는 즉시 적용되며 되돌릴 수 없습니다. Object Storage 원본은 삭제하지 않습니다.")
                document_selector = gr.Dropdown(label="삭제할 document ID", choices=[])
                delete_button = gr.Button("선택 Grounding 문서 삭제", variant="stop")
        save_repository_button.click(save_repository, inputs=repository_input, outputs=[repository_input, repository_status])
        refresh_button.click(refresh_documents, inputs=repository_input, outputs=[repository_status, document_list, document_selector])
        direct_button.click(upload_directly, inputs=[repository_input, direct_file], outputs=[repository_status, document_list, document_selector])
        object_button.click(upload_via_object_storage, inputs=[repository_input, object_file, object_key], outputs=[repository_status, document_list, document_selector])
        delete_button.click(remove_document, inputs=[repository_input, document_selector], outputs=[repository_status, document_list, document_selector])
        ask_button.click(run_grounding, inputs=[repository_input, question], outputs=answer)
    return app
