# 03 · Gen AI Hub Services

Orchestration, Grounding, RPT 서비스를 확인하는 단계입니다.

> 공통 환경 설정과 JupyterLab 실행은 [루트 README](../README.md)에서 진행합니다.

---

<details>
<summary><strong>🔧 시작 전 확인</strong></summary>

| 실습 범위 | 필요한 준비 |
| --- | --- |
| Orchestration | AI Core 인증 정보와 실행 가능한 orchestration deployment |
| Grounding | `GROUNDING_REPOSITORY_ID` |
| SAP RPT risk classification | AI Core 인증 정보와 RUNNING `RPT_MODEL=sap-rpt-1.5-large` deployment |
| SAP RPT Decision API | `SAP_RPT_API_KEY` |
| 고정 deployment 사용 | 선택적으로 `AICORE_ORCHESTRATION_DEPLOYMENT_URL` |
| Object Storage 연계 | 선택적으로 Object Storage 접속 정보와 bucket |

Grounding에는 문서 저장소가 필요합니다.

</details>

---

<details>
<summary><strong>📓 노트북 안내</strong></summary>

| 노트북 | 무엇을 하나요? | 확인할 결과 |
| --- | --- | --- |
| [01_orchestration.ipynb](notebooks/01_orchestration.ipynb) | 등록된 Orchestration을 조회·호출하고 prompt templating, 콘텐츠 필터, 데이터 마스킹을 살펴봅니다. | 어떤 서비스가 호출되었는지와 입력 보호 기능이 적용되는 위치를 확인합니다. |
| [02_grounding.ipynb](notebooks/02_grounding.ipynb) | 인덱싱된 문서 chunk를 근거로 질의하고, 답변의 참조 근거를 확인합니다. | 생성된 답변과 실제로 참조한 chunk를 분리해 검토합니다. |
| [03_rpt_risk_classification.ipynb](notebooks/03_rpt_risk_classification.ipynb) | ID를 제거한 교육용 신용위험 표 데이터를 SAP RPT로 80/20 holdout 평가하고 한 건을 분류합니다. | RPT 요청에 전달되는 feature·label, 성능 지표, 감사용 집계를 분리해 검토합니다. |
| [04_rpt_decision.ipynb](notebooks/04_rpt_decision.ipynb) | SAP RPT Decision API로 고객 문의의 담당 경로·의도·감정 상태·처리 방식·우선순위를 함께 결정합니다. | `SAP_RPT_API_KEY`를 사용한 읽기 전용 API 호출과 결정 근거를 검토합니다. |

Orchestration, Grounding, RPT 순으로 실행하세요. RPT는 읽기 전용 예측을 사용합니다.

```bash
.venv/bin/python main.py rpt-evaluate
.venv/bin/python main.py rpt-decision "카드에 중복 청구되었습니다. 오늘 확인해 주세요."
```

`RPT_MODEL`은 기본값 `sap-rpt-1.5-large`를 사용하며, 반복 가능한 대상이 필요하면 `AICORE_RPT_DEPLOYMENT_ID`로 RUNNING deployment 하나를 고정합니다.

</details>

---

<details>
<summary><strong>🧩 선택 기능: Object Storage → Grounding</strong></summary>

원본 문서는 Object Storage에 보관하고, Grounding은 인덱싱된 문서를 사용합니다.

</details>

---

<details>
<summary><strong>✅ 이 단계의 완료 기준</strong></summary>

- Orchestration 응답과 Grounding 문서 근거를 확인합니다.
- RPT 결과는 교육용 데이터로 검토합니다.

CLI 실행 명령은 위의 RPT 예시를 사용하고, 공통 설치와 JupyterLab 실행은 [루트 README](../README.md)를 따릅니다.

</details>
