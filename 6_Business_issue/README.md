# 6. Business Issue — Harness 기반 업무 의사결정

앞 단계에서 만든 Harness를 실제 업무 문제에 연결하는 캡스톤 실습입니다.

## 시나리오

| 시나리오 | 업무 이슈 | Harness의 결과 | 최종 승인자 |
| --- | --- | --- | --- |
| 재고·발주 | 품절과 과잉재고 사이에서 MOQ·할인·예산을 함께 판단 | 발주 초안 | 구매 담당자 |
| KYC | 법인·대표자·실소유자 증빙, 제재·PEP 결과를 일관되게 검토 | 강화심사/차단/승인 권고 | 준법감시인 |
| 채권 RA | 여신한도, 연체 aging, 신규 주문을 함께 평가 | 출고 보류/조건부 출고 권고 | 신용관리자 |
| 압류·AML Multi-Agent | 압류 문서, KYC, 원장, 자금 흐름, 컴플라이언스를 연결 | 검토 보고서 초안 및 조사 확대 권고 | 법무·준법감시인 |

모든 fixture는 합성 데이터이며, 모든 예제는 읽기 전용입니다. 실제 계정 개설, 신용한도 변경, 발주·출고를 실행하지 않습니다.

## 개발 순서

업무 정책과 계산은 src/가 단일 기준입니다. 변경은 src/*.py와 tests/test_business_issue.py에서 먼저 개발·검증하고, 노트북은 fixture를 읽어 solve_* 또는 run_* entry point를 호출해 결과와 UI를 표시합니다. 노트북에 정책 함수나 fixture 사본을 추가하지 않습니다.

압류·AML Multi-Agent 시나리오는 Jupyter의 코드 출력 대신 **Gradio UI**를 기본 진입점으로 사용합니다. 요청, 병렬 Agent trace, 재계획·동적 위임, 근거, 그래프, 보고서 초안과 승인 통제를 한 화면에서 확인합니다.

## Harness가 맡는 일

```
업무 요청
  → Harness reranker: Business Agent 선택
  → 읽기 전용 증거 수집: 재고·수요·구매정책 fixture
  → 결정론적 계산: 안전재고, MOQ, 할인, 예산 검증
  → Analyst Writer: 근거 기반 발주 초안
  → 사람 승인(HIL) 후에만 ERP 발주
```

계산이 필요한 수량·금액은 재현 가능한 코드가 담당하고, Harness는 적절한 specialist 선택과 근거 패킷·설명 생성의 틀을 제공합니다. 데모는 **읽기 전용**이며 실제 ERP 또는 발주 시스템을 변경하지 않습니다.

## 실행

JupyterLab에서 원하는 노트북을 위에서 아래로 실행합니다. AI Core 키나 외부 모델 없이도 동일한 결과를 재현합니다.

- [01_inventory_replenishment_case.ipynb](notebooks/01_inventory_replenishment_case.ipynb)
- [02_kyc_review_case.ipynb](notebooks/02_kyc_review_case.ipynb)
- [03_receivables_risk_assessment.ipynb](notebooks/03_receivables_risk_assessment.ipynb)
- [04_seizure_aml_multiagent.ipynb](notebooks/04_seizure_aml_multiagent.ipynb)

```bash
python3 -m unittest discover -s 6_Business_issue/tests -v
```

## 구성

| 경로 | 역할 |
| --- | --- |
| `fixtures/replenishment_case.json` | 읽기 전용 ERP/수요/구매정책 데모 데이터 |
| `fixtures/kyc_case.json` | 법인 KYC 증빙·스크리닝 데모 데이터(합성) |
| `fixtures/receivables_ra_case.json` | 채권 aging·여신한도·주문 데모 데이터(합성) |
| `fixtures/seizure_aml_case.json` + `seizure_order_mock.txt` | 압류·KYC·원장·자금흐름 모의 데이터와 OCR 텍스트 |
| `src/business_issue.py` | Harness 라우팅, 근거 패킷, 발주안 및 승인 게이트 |
| `src/kyc_issue.py` | KYC 증빙·스크리닝 평가 및 준법 승인 게이트 |
| `src/receivables_ra_issue.py` | 채권 Risk Assessment 및 신용관리 승인 게이트 |
| `src/seizure_aml_multiagent.py` | 병렬 분석, Graph/AML 동적 위임, 재계획, 관찰성, 보고서 초안 |
| `notebooks/01_inventory_replenishment_case.ipynb` | 문제 → Harness 처리 → 사람 승인 흐름을 보여주는 실습 |
| `notebooks/02_kyc_review_case.ipynb` | KYC 강화심사 흐름을 보여주는 실습 |
| `notebooks/03_receivables_risk_assessment.ipynb` | 채권 RA와 조건부 출고 판단을 보여주는 실습 |
| `notebooks/04_seizure_aml_multiagent.ipynb` | 압류 대응·AML Multi-Agent Harness 실습 |
| `requirements-financial-multiagent.txt` | 선택적인 NetworkX/PyVis 그래프 UI 의존성 |
| `tests/test_business_issue.py` | 라우팅·예산·승인 게이트 검증 |

## 데모에서 볼 결과

- 요청은 `Business Agent`로 라우팅된다. (`5_harness`의 specialist reranker 재사용)
- SKU-A/B/C의 예상 재고가 안전재고 미달임을 근거로 확인한다.
- MOQ와 SKU-B의 500개 이상 10% 할인을 반영한 발주 초안은 **9,580,000원**으로 1,000만원 예산 안에 있다.
- 결과는 `approval_required` 상태다. 발주 생성·전송은 이 예제의 범위 밖이며, 승인 뒤 별도 write tool로만 연결한다.

## 다음 확장 후보

- 이상 거래·중복 지급 탐지와 지급 보류
- 수금 우선순위와 회수 액션 추천
- 수출통제·거래제한 국가 스크리닝
- 계약 조항·갱신 리스크 검토
- 보험금 청구 또는 구매송장 예외 처리

확장할 때도 `읽기 전용 근거 → 코드로 검증 가능한 규칙 → Harness가 설명·handoff → 사람 승인 → 분리된 write tool` 경계를 유지합니다.
