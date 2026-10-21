# 03 · Gen AI Hub Services

AI Core Orchestration과 document grounding을 서비스 단위로 확인합니다. 문서 원본 보관과 검색 근거를 분리해, 답변이 어떤 근거를 참조했는지 확인하는 단계입니다.

> 공통 환경 설정과 JupyterLab 실행은 [루트 README](../README.md)에서 진행합니다.

---

<details>
<summary><strong>🔧 시작 전 확인</strong></summary>

| 실습 범위 | 필요한 준비 |
| --- | --- |
| Orchestration | AI Core 인증 정보와 실행 가능한 orchestration deployment |
| Grounding | `GROUNDING_REPOSITORY_ID` |
| SAP RPT risk classification | AI Core 인증 정보와 RUNNING `RPT_MODEL=sap-rpt-1.5-large` deployment |
| 고정 deployment 사용 | 선택적으로 `AICORE_ORCHESTRATION_DEPLOYMENT_URL` |
| Object Storage 연계 | 선택적으로 Object Storage 접속 정보와 bucket |

Grounding 저장소가 비어 있거나 조회에 실패한 상태는 답변 근거가 없는 상태와 구분해서 확인합니다.

</details>

---

<details>
<summary><strong>📓 노트북 안내</strong></summary>

| 노트북 | 무엇을 하나요? | 확인할 결과 |
| --- | --- | --- |
| [01_orchestration.ipynb](notebooks/01_orchestration.ipynb) | 등록된 Orchestration을 조회·호출하고 prompt templating, 콘텐츠 필터, 데이터 마스킹을 살펴봅니다. | 어떤 서비스가 호출되었는지와 입력 보호 기능이 적용되는 위치를 확인합니다. |
| [02_grounding.ipynb](notebooks/02_grounding.ipynb) | 인덱싱된 문서 chunk를 근거로 질의하고, 답변의 참조 근거를 확인합니다. | 생성된 답변과 실제로 참조한 chunk를 분리해 검토합니다. |
| [03_rpt_risk_classification.ipynb](notebooks/03_rpt_risk_classification.ipynb) | ID를 제거한 교육용 신용위험 표 데이터를 SAP RPT로 80/20 holdout 평가하고 한 건을 분류합니다. | RPT 요청에 전달되는 feature·label, 성능 지표, 감사용 집계를 분리해 검토합니다. |

먼저 Orchestration의 서비스 호출 흐름을 이해한 뒤 Grounding에서 문서 근거가 답변으로 연결되는 방식을 확인하세요. RPT 실습은 별도 학습·deployment 생성 없이 RUNNING foundation model에 읽기 전용 예측만 요청합니다.

</details>

---

<details>
<summary><strong>🧩 선택 기능: Object Storage → Grounding</strong></summary>

Grounding 노트북의 Object Storage 연계는 UTF-8 Markdown 원본을 Object Storage에 보관하고, 같은 텍스트를 선택한 vector repository에 인덱싱합니다. 질의는 Object Storage 원본이 아니라 인덱싱된 vector chunk를 근거로 수행됩니다. Grounding UI에서 문서를 삭제해도 원본 object는 유지될 수 있음을 확인하세요.

</details>

---

<details>
<summary><strong>✅ 이 단계의 완료 기준</strong></summary>

- 등록된 Orchestration을 호출하고 서비스 응답을 확인할 수 있습니다.
- Grounding 답변과 참조 문서 근거를 함께 검토할 수 있습니다.
- 교육용 risk 데이터의 RPT 분류 지표와 감사용 그룹 집계를 자동 신용 의사결정과 구분해 검토할 수 있습니다.
- 저장소 미설정·조회 실패를 근거 있는 답변처럼 표시하지 않습니다.

테스트와 실행 명령은 [루트 README](../README.md)를 따릅니다.

</details>
