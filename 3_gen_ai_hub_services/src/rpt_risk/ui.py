"""Thin Gradio adapter for the SAP RPT risk lab."""
from __future__ import annotations

from typing import Any

from lab_common.config import load_settings

from .lab_core import (
    FEATURE_COLUMNS,
    PREDICTION_TABLE_COLUMNS,
    explain_rpt_risk_case,
    export_rpt_risk_results,
    inspect_risk_dataset,
    predict_rpt_risk_case,
    preview_risk_dataset,
    run_rpt_risk_evaluation,
    run_rpt_permutation_importance,
)

_PREDICTION_TABLE_CSS = """
#rpt-prediction-table table th:nth-child(16),
#rpt-prediction-table table td:nth-child(16),
#rpt-prediction-table [role='columnheader']:nth-child(16),
#rpt-prediction-table [role='gridcell']:nth-child(16) {
    background: #fff3cd !important;
    color: #6b4e00 !important;
    font-weight: 700 !important;
}
#rpt-prediction-table table th:nth-child(17),
#rpt-prediction-table table td:nth-child(17),
#rpt-prediction-table [role='columnheader']:nth-child(17),
#rpt-prediction-table [role='gridcell']:nth-child(17) {
    background: #fffaf0 !important;
}
"""


def build_rpt_risk_ui() -> Any:
    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError("gradio가 없습니다. pip install -r requirements.txt를 실행하세요.") from error

    def inspect() -> dict[str, Any]:
        return inspect_risk_dataset()

    def table_values(rows: list[dict[str, Any]]) -> list[list[Any]]:
        return [[row.get(column, "—") for column in PREDICTION_TABLE_COLUMNS] for row in rows]

    def evaluate() -> tuple[dict[str, Any], list[list[Any]], dict[str, Any]]:
        outcome = run_rpt_risk_evaluation(load_settings())
        result = {key: value for key, value in outcome.items() if key != "prediction_table"}
        return result, table_values(outcome["prediction_table"]), outcome

    def save_evaluation(outcome: dict[str, Any] | None) -> tuple[str, str | None]:
        if not outcome:
            return "먼저 80/20 Holdout 평가를 실행하세요.", None
        exported = export_rpt_risk_results(outcome)
        return f"저장 완료: {exported['row_count']}건 · {exported['path']}", exported["path"]

    def predict(*values: Any) -> dict[str, Any]:
        return predict_rpt_risk_case(dict(zip(FEATURE_COLUMNS, values, strict=True)), load_settings())

    def importance() -> dict[str, Any]:
        return run_rpt_permutation_importance(load_settings())

    def sensitivity(feature: str, *values: Any) -> dict[str, Any]:
        case = dict(zip(FEATURE_COLUMNS, values, strict=True))
        return explain_rpt_risk_case(case, feature, load_settings())

    preview = preview_risk_dataset()
    initial_rows = [{**row, "rpt_prediction": "대기", "rpt_confidence": "—"} for row in preview["rows"]]
    with gr.Blocks(css=_PREDICTION_TABLE_CSS, title="SAP RPT 신용위험 분류") as app:
        evaluation_state = gr.State(value=None)
        gr.Markdown(
            "# SAP RPT 신용위험 분류\n"
            "교육용 데이터의 읽기 전용 RPT 예측입니다. 자동 승인·거절, 학습 실행, deployment 변경은 수행하지 않습니다."
        )
        with gr.Row():
            inspect_button = gr.Button("데이터 상태 확인")
            evaluate_button = gr.Button("80/20 Holdout 평가 실행", variant="primary")
        with gr.Accordion("평가 결과 및 근거", open=False):
            result = gr.JSON(label="평가 결과 및 근거")
        prediction_table = gr.Dataframe(
            value=table_values(initial_rows),
            headers=PREDICTION_TABLE_COLUMNS,
            datatype=["str"] * len(PREDICTION_TABLE_COLUMNS),
            interactive=False,
            elem_id="rpt-prediction-table",
            label=f"교육용 원본 데이터 및 RPT 예측 ({preview['displayed_rows']} / {preview['total_rows']}행 미리보기)",
        )
        gr.Markdown("평가 전에는 rpt_prediction이 대기 상태입니다. Holdout 평가 뒤에는 표가 824건의 holdout 행으로 바뀌며 risk_label(실제값), rpt_prediction(예측값), rpt_confidence가 함께 표시됩니다. 원본 customer ID와 감사 속성은 SAP BTP에 전송하지 않습니다.")
        with gr.Row():
            save_button = gr.Button("평가 결과 CSV 저장")
            save_status = gr.Textbox(label="CSV 저장 상태", interactive=False)
        saved_csv = gr.File(label="저장된 평가 결과 CSV", interactive=False)
        with gr.Accordion("단건 가명 고객 예측 (사람 검토용)", open=False):
            inputs = []
            with gr.Row():
                for column in FEATURE_COLUMNS:
                    inputs.append(gr.Textbox(label=column, placeholder="값 입력"))
            predict_button = gr.Button("단건 RPT 예측")
            prediction = gr.JSON(label="단건 예측")
        with gr.Accordion("Feature 영향 분석 (선택 실행)", open=False):
            gr.Markdown(
                "전역 분석은 feature를 하나씩 섞어 성능 하락을 측정합니다. 현재 데이터에서는 24회의 읽기 전용 RPT 요청이 발생할 수 있습니다. "
                "단건 sensitivity는 선택한 feature 하나를 대표값으로 바꿔 baseline과 비교하며 2회 요청합니다. 두 결과 모두 내부 모델의 인과적 설명이 아닙니다."
            )
            importance_button = gr.Button("전역 Permutation Importance 실행")
            with gr.Accordion("전역 중요도 결과", open=False):
                importance_result = gr.JSON(label="Permutation importance")
            sensitivity_feature = gr.Dropdown(
                choices=list(FEATURE_COLUMNS), value="credit_score", label="단건 sensitivity feature"
            )
            sensitivity_button = gr.Button("단건 Counterfactual Sensitivity 실행")
            with gr.Accordion("단건 sensitivity 결과", open=False):
                sensitivity_result = gr.JSON(label="Counterfactual sensitivity")
        inspect_button.click(inspect, outputs=result)
        evaluate_button.click(evaluate, outputs=[result, prediction_table, evaluation_state])
        save_button.click(save_evaluation, inputs=evaluation_state, outputs=[save_status, saved_csv])
        predict_button.click(predict, inputs=inputs, outputs=prediction)
        importance_button.click(importance, outputs=importance_result)
        sensitivity_button.click(sensitivity, inputs=[sensitivity_feature, *inputs], outputs=sensitivity_result)
    return app
