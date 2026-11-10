# 운영 컨텍스트

이 디렉터리는 Agent와 Grounding 실습에서 사용하는 운영 기준의 단일 진입점이다. 공통 규칙부터 업무별 시나리오까지 아래 순서로 읽는다. 각 문서는 검토와 인계를 위한 근거이며, 구매·승인·예산 배정·시스템 변경 또는 외부 실행 권한을 부여하지 않는다.

## 공통 기준

| 문서 | 용도 | 읽을 때 |
| --- | --- | --- |
| [협업 SOP](collaboration_sop.md) | 요청 접수, 부서 간 검토 순서, Human-in-the-loop 경계 | 모든 협업 요청 |
| [역할·책임 운영기준](roles.md) | 역할별 검토 범위, 인계 형식, 요청 유형별 상세 절차 | 담당 부서와 다음 인계를 판단할 때 |
| [업무 카탈로그·KPI 기준](work_catalog.md) | 정기·비정기 업무, KPI 정의, 이슈 관리 절차 | 업무 유형과 관찰 지표를 확인할 때 |

## 업무별 컨텍스트

`work_units/`에는 위 공통 기준을 특정 업무에 적용한 독립 시나리오가 있다. 필요한 업무만 추가로 읽고, 제공되지 않은 값·승인 상태·최신 운영 상태는 추정하지 않는다.

| 번호 | 업무 | 문서 |
| --- | --- | --- |
| 01 | 현장 운영 점검 | [01_field_operations_check.md](work_units/01_field_operations_check.md) |
| 02 | 예방정비 검토 | [02_preventive_maintenance_review.md](work_units/02_preventive_maintenance_review.md) |
| 03 | 재고·수급 검토 | [03_inventory_supply_review.md](work_units/03_inventory_supply_review.md) |
| 04 | 생산 준비도 검토 | [04_production_readiness_review.md](work_units/04_production_readiness_review.md) |
| 05 | EHS 점검 | [05_ehs_inspection.md](work_units/05_ehs_inspection.md) |
| 06 | 품질 검사 검토 | [06_quality_inspection_review.md](work_units/06_quality_inspection_review.md) |
| 07 | 예산·원가 검토 | [07_budget_cost_review.md](work_units/07_budget_cost_review.md) |
| 08 | 사업계획 가정 검토 | [08_business_plan_assumptions.md](work_units/08_business_plan_assumptions.md) |
| 09 | ERP·MDM 변경 기록 점검 | [09_erp_mdm_change_log_review.md](work_units/09_erp_mdm_change_log_review.md) |
| 10 | 전사 KPI 검토 | [10_enterprise_kpi_review.md](work_units/10_enterprise_kpi_review.md) |
| 11 | 설비 사고 검토 | [11_equipment_incident_review.md](work_units/11_equipment_incident_review.md) |
| 12 | 유지보수 구매 요청 | [12_maintenance_purchase_request.md](work_units/12_maintenance_purchase_request.md) |
| 13 | 신규 자재 투입 검토 | [13_new_material_intake_review.md](work_units/13_new_material_intake_review.md) |
| 14 | 공급 차질 대응 | [14_supply_disruption_response.md](work_units/14_supply_disruption_response.md) |
| 15 | 예산 이관·Cost Center 변경 | [15_budget_transfer_cost_center.md](work_units/15_budget_transfer_cost_center.md) |
| 16 | ERP·MDM 변경 영향 | [16_erp_mdm_change_impact.md](work_units/16_erp_mdm_change_impact.md) |
| 17 | 품질 이탈 검토 | [17_quality_deviation_review.md](work_units/17_quality_deviation_review.md) |
| 18 | 공정 변경·수율 검토 | [18_process_change_yield_review.md](work_units/18_process_change_yield_review.md) |
| 19 | EHS 사고 보고 | [19_ehs_incident_report.md](work_units/19_ehs_incident_report.md) |

## 관리 원칙

- 공통 기준은 `data/context/`만을 정본으로 관리한다.
- 업무 단위 문서는 재사용성과 Grounding 검색 정확도를 위해 분리한다.
- SOP를 수정하면 역할·업무 카탈로그 및 영향을 받는 업무 단위 문서와의 정합성을 함께 확인한다.
