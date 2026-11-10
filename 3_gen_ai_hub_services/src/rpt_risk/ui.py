"""Thin Gradio adapter for the SAP RPT risk lab."""
from __future__ import annotations

from typing import Any

from .lesson_support.config import load_settings

from .lab_core import (
    PREDICTION_TABLE_COLUMNS,
    list_saved_rpt_holdout_runs,
    load_saved_rpt_holdout_run,
    persist_rpt_holdout_snapshot,
    predict_saved_rpt_holdout_row,
    preview_risk_dataset,
    run_rpt_risk_evaluation,
    saved_rpt_holdout_scenarios,
)


def _light_theme(gr):
    base = gr.themes.Base(primary_hue=gr.themes.colors.blue)
    values = base.to_dict()["theme"]
    return base.set(**{f"{name}_dark": value for name, value in values.items() if not name.endswith("_dark") and f"{name}_dark" in values})

def _evaluation_figures(outcome: dict[str, Any]) -> tuple[Any, Any]:
    """Create the holdout metric and confusion-matrix charts for the UI."""
    try:
        import plotly.graph_objects as go
    except ImportError as error:
        raise RuntimeError("평가 차트 표시에 plotly가 필요합니다. requirements.txt를 다시 설치하세요.") from error

    metrics = outcome["metrics"]
    matrix = metrics["confusion_matrix"]
    true_negative = int(matrix["actual_0"]["predicted_0"])
    false_positive = int(matrix["actual_0"]["predicted_1"])
    false_negative = int(matrix["actual_1"]["predicted_0"])
    true_positive = int(matrix["actual_1"]["predicted_1"])
    total = true_positive + true_negative + false_positive + false_negative
    metric_labels = ["Accuracy", "Precision (label 1)", "Recall (label 1)", "F1 (label 1)"]
    accuracy = float(metrics["accuracy"])
    precision = float(metrics["precision_positive_1"])
    recall = float(metrics["recall_positive_1"])
    f1 = float(metrics["f1_positive_1"])
    metric_values = [
        accuracy * 100,
        precision * 100,
        recall * 100,
        f1 * 100,
    ]
    metric_tooltips = [
        (
            "<b>Accuracy (전체 정답률)</b><br>"
            "공식: (TP + TN) / (TP + TN + FP + FN)<br>"
            f"대입: ({true_positive} + {true_negative}) / {total}<br>"
            f"결과: {accuracy:.4f} = {accuracy * 100:.1f}%<br><br>"
            "<i>의미: 전체 사례 중 정답을 맞힌 비율입니다. label 0이 훨씬 많으면 실제보다 좋아 보일 수 있습니다.</i>"
        ),
        (
            "<b>Precision (label 1)</b><br>"
            "공식: TP / (TP + FP)<br>"
            f"대입: {true_positive} / ({true_positive} + {false_positive})<br>"
            f"결과: {precision:.4f} = {precision * 100:.1f}%<br><br>"
            "<i>의미: 1이라고 예측한 사례가 실제로도 1인 비율입니다. 낮으면 실제 0을 1로 잘못 판단하는 과도 탐지가 많습니다.</i>"
        ),
        (
            "<b>Recall (label 1)</b><br>"
            "공식: TP / (TP + FN)<br>"
            f"대입: {true_positive} / ({true_positive} + {false_negative})<br>"
            f"결과: {recall:.4f} = {recall * 100:.1f}%<br><br>"
            "<i>의미: 실제 1인 사례를 1로 찾아낸 비율입니다. 낮으면 실제 1 사례를 놓치는 경우가 많습니다.</i>"
        ),
        (
            "<b>F1 (label 1)</b><br>"
            "공식: 2 × Precision × Recall / (Precision + Recall)<br>"
            f"대입: 2 × {precision:.4f} × {recall:.4f} / ({precision:.4f} + {recall:.4f})<br>"
            f"결과: {f1:.4f} = {f1 * 100:.1f}%<br><br>"
            "<i>의미: 정밀도와 재현율의 균형 점수입니다. 1을 과하게 예측하는 문제와 실제 1을 놓치는 문제를 함께 확인합니다.</i>"
        ),
    ]
    metric_figure = go.Figure(
        go.Bar(
            x=metric_labels,
            y=metric_values,
            marker_color=["#1A73E8", "#34A853", "#FBBC04", "#9334E6"],
            text=[f"{value:.1f}%" for value in metric_values],
            textposition="outside",
            cliponaxis=False,
            customdata=metric_tooltips,
            hovertemplate="%{customdata}<extra></extra>",
        )
    )
    metric_figure.update_layout(
        title={"text": "Holdout 평가 성능 지표", "x": 0.02, "xanchor": "left"},
        template="plotly_white",
        height=360,
        margin={"l": 55, "r": 25, "t": 60, "b": 75},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F8FAFC",
        showlegend=False,
    )
    metric_figure.update_yaxes(title="점수 (%)", range=[0, 105], gridcolor="#EAECF0")
    metric_figure.update_xaxes(tickangle=-12)

    matrix_values = [
        [matrix["actual_0"]["predicted_0"], matrix["actual_0"]["predicted_1"]],
        [matrix["actual_1"]["predicted_0"], matrix["actual_1"]["predicted_1"]],
    ]
    confusion_figure = go.Figure(
        go.Heatmap(
            z=matrix_values,
            x=["예측 0", "예측 1"],
            y=["실제 0", "실제 1"],
            colorscale=[[0, "#E8F0FE"], [1, "#1A73E8"]],
            text=matrix_values,
            texttemplate="%{text}",
            textfont={"size": 18},
            hovertemplate="%{y} · %{x}: %{z}건<extra></extra>",
            colorbar={"title": "건수"},
        )
    )
    confusion_figure.update_layout(
        title={"text": "실제값과 RPT 예측 비교", "x": 0.02, "xanchor": "left"},
        template="plotly_white",
        height=360,
        margin={"l": 75, "r": 55, "t": 60, "b": 55},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F8FAFC",
    )
    confusion_figure.update_xaxes(side="bottom", title="RPT 예측값")
    confusion_figure.update_yaxes(title="실제 risk_label", autorange="reversed")
    return metric_figure, confusion_figure


def build_rpt_risk_ui() -> Any:
    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError("gradio가 없습니다. pip install -r requirements.txt를 실행하세요.") from error

    def table_values(rows: list[dict[str, Any]]) -> list[list[Any]]:
        return [[row.get(column, "—") for column in PREDICTION_TABLE_COLUMNS] for row in rows]

    def evaluate() -> tuple[dict[str, Any], list[list[Any]], Any, Any, dict[str, Any]]:
        outcome = run_rpt_risk_evaluation(load_settings())
        result = {
            key: value
            for key, value in outcome.items()
            if key not in {"prediction_table", "predictions", "rpt_metadata"}
        }
        metric_figure, confusion_figure = _evaluation_figures(outcome)
        return result, table_values(outcome["prediction_table"]), metric_figure, confusion_figure, outcome

    def save_completed_holdout(evaluation: dict[str, Any] | None) -> tuple[dict[str, Any], Any]:
        if not evaluation:
            return {"error": "먼저 80:20 Holdout 평가를 실행하세요."}, gr.update()
        try:
            saved = persist_rpt_holdout_snapshot(evaluation, load_settings())
            runs = list_saved_rpt_holdout_runs(load_settings())["runs"]
            choices = [(f"{run['name']} · {run['created_at']}", run["artifact_id"]) for run in runs]
            return saved, gr.update(choices=choices, value=saved["artifact_id"])
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}, gr.update()

    def refresh_saved_runs() -> tuple[dict[str, Any], Any]:
        try:
            outcome = list_saved_rpt_holdout_runs(load_settings())
            choices = [(f"{run['name']} · {run['created_at']}", run["artifact_id"]) for run in outcome["runs"]]
            return outcome, gr.update(choices=choices, value=None)
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}, gr.update()

    def load_saved_run(artifact_id: str) -> tuple[dict[str, Any], Any, dict[str, Any], dict[str, Any]]:
        if not artifact_id:
            return {}, gr.update(choices=[], value=None), {}, {}
        try:
            snapshot = load_saved_rpt_holdout_run(artifact_id, load_settings())
            scenarios = saved_rpt_holdout_scenarios(snapshot)
            choices = [(row["record_id"], row["record_id"]) for row in scenarios]
            summary = {
                "artifact_id": snapshot["artifact_id"],
                "run_id": snapshot["run_id"],
                "created_at": snapshot.get("created_at"),
                "model": snapshot.get("model"),
                "holdout_rows": len(scenarios),
                "metrics": snapshot.get("metrics"),
                "notice": "행을 선택해도 실제 risk_label은 표시하지 않습니다. 예측 실행 후에만 비교합니다.",
            }
            return snapshot, gr.update(choices=choices, value=None), summary, {}
        except Exception as error:
            return {}, gr.update(choices=[], value=None), {"error": f"{type(error).__name__}: {error}"}, {}

    def show_scenario(record_id: str, snapshot: dict[str, Any] | None) -> dict[str, Any]:
        if not record_id or not snapshot:
            return {}
        try:
            return next(row for row in saved_rpt_holdout_scenarios(snapshot) if row["record_id"] == record_id)
        except (StopIteration, ValueError):
            return {"error": "선택한 Holdout 행을 찾을 수 없습니다."}

    def predict_saved_row(record_id: str, snapshot: dict[str, Any] | None) -> dict[str, Any]:
        if not record_id or not snapshot:
            return {"error": "저장된 Holdout run과 행을 선택하세요."}
        try:
            return predict_saved_rpt_holdout_row(snapshot, record_id, load_settings())
        except Exception as error:
            return {"error": f"{type(error).__name__}: {error}"}

    preview = preview_risk_dataset()
    initial_rows = [{**row, "rpt_prediction": "대기", "rpt_confidence": "—"} for row in preview["rows"]]
    with gr.Blocks(title="SAP RPT 신용위험 분류", theme=_light_theme(gr)) as app:
        gr.Markdown(
            "# SAP RPT 신용위험 분류\n"
            "교육용 데이터의 RPT 예측입니다. Holdout snapshot 저장은 명시적 실행과 `ALLOW_WRITE_TOOLS=true`가 필요하며, 자동 승인·거절은 수행하지 않습니다."
        )
        evaluation_state = gr.State(value={})
        saved_run_state = gr.State(value={})
        with gr.Tabs():
            with gr.Tab("80:20 Holdout 평가"):
                evaluate_button = gr.Button("RPT 진행", variant="primary")
                prediction_table = gr.Dataframe(
                    value=table_values(initial_rows),
                    headers=PREDICTION_TABLE_COLUMNS,
                    datatype=["str"] * len(PREDICTION_TABLE_COLUMNS),
                    interactive=False,
                    label=f"교육용 원본 데이터 및 RPT 예측 ({preview['displayed_rows']} / {preview['total_rows']}행 미리보기)",
                )
                with gr.Accordion("평가 결과 및 근거", open=False):
                    result = gr.JSON(label="상세 평가 결과")
                with gr.Row():
                    metric_plot = gr.Plot(label="Holdout 성능 지표")
                    confusion_plot = gr.Plot(label="실제값과 RPT 예측 비교")
                gr.Markdown("### BTP Holdout snapshot 저장\n교육용 feature·가명 record ID·실제 label·예측·지표만 저장합니다. audit 속성과 원본 customer ID는 저장하지 않습니다.")
                save_button = gr.Button("BTP에 시나리오 저장")
                save_result = gr.JSON(label="저장 결과")

            with gr.Tab("저장된 Holdout 시나리오"):
                gr.Markdown("저장된 holdout 행을 선택하면 feature만 확인할 수 있습니다. 실제 label은 RPT 예측을 실행한 뒤에만 공개됩니다.")
                refresh_button = gr.Button("저장된 Run 새로고침")
                runs_result = gr.JSON(label="등록된 BTP Holdout Artifact")
                saved_run = gr.Dropdown(
                    label="저장된 Holdout Run",
                    choices=[],
                    filterable=False,
                    allow_custom_value=False,
                    info="'저장된 Run 새로고침' 후 목록에서 선택하세요. Artifact ID를 직접 입력할 수 없습니다.",
                )
                run_summary = gr.JSON(label="선택한 Run 요약")
                scenario_row = gr.Dropdown(label="Holdout 행 (record_id)", choices=[])
                scenario_features = gr.JSON(label="선택한 행의 RPT Feature")
                predict_button = gr.Button("이 행 예측", variant="primary")
                scenario_prediction = gr.JSON(label="재예측 결과")

        evaluate_button.click(
            evaluate,
            outputs=[result, prediction_table, metric_plot, confusion_plot, evaluation_state],
        )
        save_button.click(
            save_completed_holdout, inputs=evaluation_state, outputs=[save_result, saved_run],
        )
        refresh_button.click(refresh_saved_runs, outputs=[runs_result, saved_run])
        saved_run.change(load_saved_run, inputs=saved_run, outputs=[saved_run_state, scenario_row, run_summary, scenario_features])
        scenario_row.change(show_scenario, inputs=[scenario_row, saved_run_state], outputs=scenario_features)
        predict_button.click(predict_saved_row, inputs=[scenario_row, saved_run_state], outputs=scenario_prediction)
    return app
