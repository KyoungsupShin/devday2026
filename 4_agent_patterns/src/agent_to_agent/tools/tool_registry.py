"""Schemas and explicit execution registry for local read-only Tools."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .business_context import search_business_context
from .erp_change_records import lookup_erp_readiness_evidence
from .facility_records import lookup_facility_context
from .financial_records import (
    lookup_business_outlook_evidence,
    lookup_cost_driver_evidence,
    lookup_financial_control_evidence,
)
from .manufacturing_records import (
    lookup_material_intake_context,
    lookup_production_context,
)
from .process_engineering_records import lookup_process_evidence
from .production_execution_records import lookup_production_execution_evidence
from .profitability_forecast import calculate_profitability_scenarios
from .purchasing_records import lookup_procurement_evidence, lookup_supply_evidence
from .quality_records import lookup_quality_evidence
from .research_development_records import lookup_rnd_evidence
from .safety_environment_records import lookup_ehs_evidence
from .site_services_records import lookup_general_affairs_evidence
from .workforce_records import lookup_hr_workforce_evidence

REQUEST_TEXT_PARAMETERS = {
    "type": "object",
    "properties": {
        "request_text": {
            "type": "string",
            "description": "현장 요청에 포함된 제품·자재·생산라인·설비 관련 문구",
        }
    },
    "required": ["request_text"],
    "additionalProperties": False,
}
CONTEXT_ID_PARAMETERS = {
    "type": "object",
    "properties": {
        "context_id": {
            "type": "string",
            "description": "Context 검색 또는 이전 artifact에서 확인된 Context ID",
        }
    },
    "required": ["context_id"],
    "additionalProperties": False,
}


def _schema(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


TOOL_SCHEMAS = {
    "search_business_context": _schema(
        "search_business_context",
        "요청의 제품·자재·생산라인·설비 표시명 또는 별칭으로 Context를 찾습니다. 후속 조회용 Context ID만 제공하며 Agent 선택이나 업무 단계 판단은 하지 않습니다.",
        REQUEST_TEXT_PARAMETERS,
    ),
    "lookup_facility_context": _schema(
        "lookup_facility_context",
        "Context ID에 연결된 설비 마스터, 정비 오더, 설비 BOM 스냅샷을 읽습니다. 실제 설비 진단·정비·교체 결과를 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_procurement_evidence": _schema(
        "lookup_procurement_evidence",
        "Context ID에 연결된 자재 기준정보, 공급처 자격, 견적, 구매요청, 입고예정, 승인 기준 스냅샷을 읽습니다. 실제 구매·계약·승인 결과를 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_supply_evidence": _schema(
        "lookup_supply_evidence",
        "Context ID에 연결된 재고, 예약·소요량, 입고예정, 재주문 기준 스냅샷을 읽습니다. 실시간 재고 또는 배정 결과를 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_production_context": _schema(
        "lookup_production_context",
        "Context ID에 연결된 제품, BOM, 생산계획, 자재 소요량 스냅샷을 읽습니다. 실제 생산 지시나 확정 계획을 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_material_intake_context": _schema(
        "lookup_material_intake_context",
        "Context ID에 연결된 신규 자재 등록, BOM 변경, 품질 승인, 생산 투입 준비 스냅샷을 읽습니다. 실제 등록·승인·투입을 수행하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_cost_driver_evidence": _schema(
        "lookup_cost_driver_evidence",
        "Context ID에 연결된 환율 시나리오, 원자재 가격, 제품 BOM, 제조원가 가정 스냅샷을 읽습니다. 실제 환율·가격·수익성 결과를 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_business_outlook_evidence": _schema(
        "lookup_business_outlook_evidence",
        "Context ID에 연결된 제품 상태, 수요·매출 전망, 계획 기간 스냅샷을 읽습니다. 실제 판매 실적·수요 확정·사업 승인 결과를 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "calculate_profitability_scenarios": _schema(
        "calculate_profitability_scenarios",
        "Context ID에 연결된 BOM, 월별 환율·원자재 단가, 판매 전망, 제조원가 가정을 결합해 시나리오별 월별 예상원가·BEP·분기 손익을 읽기 전용으로 계산합니다. 입력이 누락·중복·통화 불일치이면 임의 보정 없이 계산을 중단합니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_financial_control_evidence": _schema(
        "lookup_financial_control_evidence",
        "Context ID에 연결된 OPEX, 구매 승인 기준, Cost Center, 커밋먼트, 변경·이관 상태 스냅샷을 읽습니다. 실제 잔액·승인·이관·전기 결과를 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_erp_readiness_evidence": _schema(
        "lookup_erp_readiness_evidence",
        "Context ID에 연결된 ERP 변경요청, 필드 매핑, 검증 전제조건 스냅샷을 읽습니다. 실제 ERP 반영·검증 완료를 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_ehs_evidence": _schema(
        "lookup_ehs_evidence",
        "Context ID에 연결된 작업 안전, 환경 관리, 화학물질, 작업허가 스냅샷을 읽습니다. 실제 위험성 평가 완료, 허가 발행, 환경 준수 결과를 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_hr_workforce_evidence": _schema(
        "lookup_hr_workforce_evidence",
        "Context ID에 연결된 인력 배치, 교육·자격, 근태·노무 통제 스냅샷을 읽습니다. 실제 인사 조치, 근무 배정, 근태 확정을 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_general_affairs_evidence": _schema(
        "lookup_general_affairs_evidence",
        "Context ID에 연결된 사업장 지원, 비생산 자산·비품, 출입·보안 지원 스냅샷을 읽습니다. 실제 서비스 제공, 자산 지급, 출입 권한 부여를 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_process_evidence": _schema(
        "lookup_process_evidence",
        "Context ID에 연결된 공정 조건, 수율·처리량, 공정 변경·검증 스냅샷을 읽습니다. 실제 공정 변경, 검증 완료, 성능 확정을 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_rnd_evidence": _schema(
        "lookup_rnd_evidence",
        "Context ID에 연결된 제품·배합 개발, 원료·규격 개발, 스케일업·기술이전 스냅샷을 읽습니다. 실제 개발 승인, 양산 전환, 품질 release를 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_production_execution_evidence": _schema(
        "lookup_production_execution_evidence",
        "Context ID에 연결된 생산 실행, 라인 운영, 배치·Lot 추적성 스냅샷을 읽습니다. 실제 생산 지시, 가동 완료, 품질 판정을 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
    "lookup_quality_evidence": _schema(
        "lookup_quality_evidence",
        "Context ID에 연결된 품질시스템, 시험·검사, 품질 release 스냅샷을 읽습니다. 실제 적합 판정, 출하 승인, CAPA 완료를 뜻하지 않습니다.",
        CONTEXT_ID_PARAMETERS,
    ),
}

TOOL_EXECUTORS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "search_business_context": search_business_context,
    "lookup_facility_context": lookup_facility_context,
    "lookup_procurement_evidence": lookup_procurement_evidence,
    "lookup_supply_evidence": lookup_supply_evidence,
    "lookup_production_context": lookup_production_context,
    "lookup_material_intake_context": lookup_material_intake_context,
    "lookup_cost_driver_evidence": lookup_cost_driver_evidence,
    "lookup_business_outlook_evidence": lookup_business_outlook_evidence,
    "calculate_profitability_scenarios": calculate_profitability_scenarios,
    "lookup_financial_control_evidence": lookup_financial_control_evidence,
    "lookup_erp_readiness_evidence": lookup_erp_readiness_evidence,
    "lookup_ehs_evidence": lookup_ehs_evidence,
    "lookup_hr_workforce_evidence": lookup_hr_workforce_evidence,
    "lookup_general_affairs_evidence": lookup_general_affairs_evidence,
    "lookup_process_evidence": lookup_process_evidence,
    "lookup_rnd_evidence": lookup_rnd_evidence,
    "lookup_production_execution_evidence": lookup_production_execution_evidence,
    "lookup_quality_evidence": lookup_quality_evidence,
}


def schemas_for_tool_ids(tool_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Return schemas in the Catalog-declared capability order."""
    schemas: list[dict[str, Any]] = []
    for tool_id in tool_ids:
        try:
            schemas.append(TOOL_SCHEMAS[tool_id])
        except KeyError as error:
            raise ValueError(
                f"등록되지 않은 local CSV Tool입니다: {tool_id}"
            ) from error
    return schemas


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute one registered local read-only Tool without any fallback."""
    try:
        executor = TOOL_EXECUTORS[name]
    except KeyError as error:
        raise ValueError(f"허용되지 않은 CSV snapshot Tool입니다: {name}") from error
    argument_name = (
        "request_text" if name == "search_business_context" else "context_id"
    )
    return executor(arguments.get(argument_name))
