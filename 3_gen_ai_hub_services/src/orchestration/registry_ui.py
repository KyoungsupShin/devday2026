"""Local Gradio adapter for browsing and invoking registered orchestrations."""
from __future__ import annotations

from textwrap import dedent
from typing import Any

import gradio as gr

from lab_common.config import load_settings
from .lab_core import (
    DEFAULT_INPUT_PLACEHOLDER,
    get_orchestration_config,
    input_placeholders,
    invoke_saved_orchestration_config,
    list_orchestration_configs,
)
from .str_lab import SYNTHETIC_STR_DATABASE_RESULT, build_str_database_input


_DEFAULT_CANDIDATE_RESUME = dedent("""\
    John Doe
    1234 Data St, San Francisco, CA 94101
    (123) 456-7890
    johndoe@email.com
    LinkedIn Profile
    GitHub Profile

    Objective
    Detail-oriented Data Scientist with 3+ years of experience in data analysis, statistical modeling, and machine learning. Seeking to leverage expertise in predictive modeling and data visualization to help drive data-informed decision-making at [Company Name].

    Education
    Master of Science in Data Science
    University of California, Berkeley
    Graduated: May 2021
    Bachelor of Science in Computer Science
    University of California, Los Angeles
    Graduated: May 2019

    Technical Skills
    Programming Languages: Python, R, SQL, Java
    Data Analysis & Visualization: Pandas, NumPy, Matplotlib, Seaborn, Tableau
    Machine Learning: Scikit-learn, TensorFlow, Keras, XGBoost
    Big Data Technologies: Hadoop, Spark
    Databases: MySQL, PostgreSQL
    Version Control: Git

    Professional Experience
    Data Scientist
    DataCorp Inc., San Francisco, CA
    June 2021 – Present

    Developed predictive models to optimize marketing campaigns, which increased ROI by 20%.
    Conducted in-depth data analysis using Python and SQL to identify trends and patterns in large datasets.
    Collaborated with cross-functional teams to implement data-driven strategies that improved customer satisfaction scores by 15%.
    Created interactive dashboards using Tableau to visualize KPIs for stakeholders.

    Data Analyst Intern
    Analytics Solutions, Los Angeles, CA
    June 2020 – August 2020

    Analyzed large datasets to identify opportunities for business growth and improvement.
    Assisted in the development of automated reporting tools using Python and Excel.
    Worked with data visualization tools to create insightful reports for management.

    Projects
    Customer Segmentation Analysis
    Conducted K-means clustering on customer data to segment the customer base into distinct groups, enabling targeted marketing strategies.

    Predictive Stock Price Modeling
    Built a predictive model using time series analysis to forecast stock prices, achieving an accuracy rate of 85%.

    Sentiment Analysis on Social Media
    Implemented natural language processing techniques to analyze sentiment from tweets, providing insights into public opinion on various topics.

    Certifications
    Certified Data Scientist (CDS) – Data Science Council of America
    Machine Learning Specialization – Coursera by Stanford University

    Professional Affiliations
    Member, Association for Computing Machinery (ACM)
    Member, Data Science Society

    References
    Available upon request.

    Personal Interests
    - I absolutely love exploring new technologies and working on innovative projects.
    - I enjoy reading books, especially on artificial intelligence and machine learning.
    - I hate people who are dishonest and unreliable.
    - I love traveling and experiencing new cultures.
    - I enjoy playing video games, especially competitive ones.
    - I hate being stuck in a routine; I always seek new challenges and growth opportunities.
    - I hate working in Azure cloud - \"Azure cloud is the most irritating platform i have ever used\"
""").strip()

_DEFAULT_STR_DATABASE_INPUT = build_str_database_input(SYNTHETIC_STR_DATABASE_RESULT)


def build_orchestration_registry_ui() -> gr.Blocks:
    """Build a read-only registry browser; invocation uses the selected config ID."""
    settings = load_settings()

    def require_config_id(config_id: str | None) -> str:
        if not isinstance(config_id, str) or not config_id.strip():
            raise gr.Error("Step 1에서 Orchestration을 선택한 뒤 Step 2에서 확인하세요.")
        return config_id.strip()

    def refresh() -> tuple[Any, ...]:
        result = list_orchestration_configs(settings=settings)
        resources = result["resources"]
        choices = [
            (
                f"{item.get('scenario', '')} / {item.get('name', '')} / "
                f"{item.get('version', '')} — {item.get('id', '')}",
                item.get("id", ""),
            )
            for item in resources
            if item.get("id")
        ]
        has_choices = bool(choices)
        status = (
            "### Step 1 완료 — Orchestration을 선택한 뒤 **Step 2. Orchestration 확인**을 누르세요."
            if has_choices
            else "### 등록된 Orchestration이 없습니다. Registry 필터와 resource group을 확인하세요."
        )
        return (
            result,
            gr.Dropdown(choices=choices, value=None, interactive=has_choices),
            gr.Button(interactive=False),
            gr.Button(interactive=False),
            gr.Markdown(value=""),
            gr.Markdown(value=status),
        )

    def select_config(config_id: str | None) -> tuple[Any, ...]:
        selected = isinstance(config_id, str) and bool(config_id.strip())
        status = (
            "### Step 1 완료 — **Step 2. Orchestration 확인**을 누르세요."
            if selected
            else "### Step 1 — 먼저 목록에서 Orchestration을 선택하세요."
        )
        return (
            gr.Button(interactive=selected),
            gr.Button(interactive=False),
            gr.Markdown(value=""),
            gr.Markdown(value=status),
        )

    def load(config_id: str | None) -> tuple[gr.Button, gr.Markdown]:
        config = get_orchestration_config(require_config_id(config_id), settings=settings)
        placeholder_names = input_placeholders(config)
        if placeholder_names != [DEFAULT_INPUT_PLACEHOLDER]:
            raise gr.Error(
                f"이 STR 실습은 입력 placeholder가 '{DEFAULT_INPUT_PLACEHOLDER}' 하나인 Config가 필요합니다. "
                f"현재 값: {placeholder_names}"
            )
        return (
            gr.Button(interactive=True),
            gr.Markdown(value="### Step 2 완료 — 질문을 확인한 뒤 **Step 3. Orchestration 호출**을 누르세요."),
        )

    def invoke(config_id: str | None, query: str) -> tuple[str, gr.Markdown]:
        result = invoke_saved_orchestration_config(
            None,
            settings,
            config_id=require_config_id(config_id),
            placeholder_values={DEFAULT_INPUT_PLACEHOLDER: query},
        )
        return (
            result["answer"],
            gr.Markdown(value="### Step 3 완료 — 다른 Orchestration을 사용하려면 Step 1부터 다시 진행하세요."),
        )

    with gr.Blocks(title="BTP Orchestration Registry") as app:
        with gr.Sidebar(open=True, width=340, position="left"):
            gr.Markdown("## Orchestration 선택")
            gr.Markdown("Step 1 → 2 → 3 순서로 진행하세요. 이전 단계가 완료되기 전에는 다음 버튼이 비활성화됩니다.")
            refresh_button = gr.Button("Step 1. 등록된 Orchestration 조회", variant="primary")
            config_id = gr.Dropdown(
                label="Orchestration 선택", choices=[], interactive=False
            )
            load_button = gr.Button("Step 2. Orchestration 확인", interactive=False)
            with gr.Accordion("조회 결과", open=False):
                listed_configs = gr.JSON(label="등록된 Orchestration 목록")

        gr.Markdown(
            "# BTP Orchestration Registry\n"
            "사이드바에서 등록된 Orchestration을 선택하고 확인한 뒤 호출합니다. 이 화면은 Registry를 변경하지 않습니다."
        )
        with gr.Accordion("선택한 Orchestration 호출", open=True):
            workflow_status = gr.Markdown("### Step 1 — 등록된 Orchestration을 조회하세요.")
            invoke_button = gr.Button("Step 3. 선택한 Orchestration 호출", variant="primary", size="sm", interactive=False)
            query = gr.Textbox(
                label="STR 초안 작성 요청 (교육용 가명 사례)",
                value=_DEFAULT_STR_DATABASE_INPUT,
                lines=24,
            )
            gr.Markdown("### 응답")
            answer = gr.Markdown(value="")

        refresh_button.click(
            refresh,
            outputs=[
                listed_configs, config_id, load_button, invoke_button, answer, workflow_status,
            ],
        )
        config_id.change(
            select_config,
            inputs=config_id,
            outputs=[load_button, invoke_button, answer, workflow_status],
        )
        load_button.click(load, inputs=config_id, outputs=[invoke_button, workflow_status])
        invoke_button.click(invoke, inputs=[config_id, query], outputs=[answer, workflow_status])
    return app
