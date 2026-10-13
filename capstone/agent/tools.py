# -*- coding: utf-8 -*-
"""
에이전트 도구 정의.
- 내부 데이터(재고/공급사): 지금은 샘플(=CAP 대체). 운영 시 CAP OData 호출로 교체(아래 주석 참고).
- 외부 데이터(환율): 실제 공개 API.
- 정책 문서: AI Core Document Grounding (Orchestration 경유).
각 도구는 (a) 실제 실행용 raw 함수, (b) Orchestration 등록용 @function_tool 래퍼로 제공한다.
"""
import json
import requests
from gen_ai_hub.orchestration_v2.models.tools import function_tool
from . import config

# ─────────────────────────── 내부 데이터 (CAP 대체 샘플) ───────────────────────────
# 운영 교체 지점: 아래 리스트 대신
#   requests.get(f"{CAP_BASE}/odata/v4/InventoryService/Inventory").json()["value"]
# 로 바꾸면 CAP OData 데이터가 그대로 들어온다. (스키마는 cap/ 참고)
_INVENTORY = [
    {"item": "A", "name": "수입 원자재",  "stock": 20,  "safety": 100, "imported": True},
    {"item": "B", "name": "국산 부품",    "stock": 80,  "safety": 100, "imported": False},
    {"item": "C", "name": "소모품",      "stock": 500, "safety": 100, "imported": False},
]
_SUPPLIERS = {
    "A": [{"supplier": "S1", "price_usd": 12.0, "moq": 300, "lead_days": 21, "discount": "500개↑ 8%"}],
    "B": [{"supplier": "S2", "price_krw": 3000, "moq": 100, "lead_days": 5,  "discount": "-"}],
    "C": [{"supplier": "S3", "price_krw": 200,  "moq": 1000,"lead_days": 3,  "discount": "-"}],
}

def raw_get_inventory() -> str:
    return json.dumps(_INVENTORY, ensure_ascii=False)

def raw_get_suppliers(item: str) -> str:
    return json.dumps(_SUPPLIERS.get(item, []), ensure_ascii=False)

def raw_get_fx(base: str = "USD", quote: str = "KRW") -> str:
    r = requests.get(f"https://open.er-api.com/v6/latest/{base}", timeout=10).json()
    rate = r.get("rates", {}).get(quote)
    return f"1 {base} = {rate} {quote}"

# ─────────────────────────── 행동(action) — 발주 초안 생성 ───────────────────────────
# 조회가 아니라 "상태를 바꾸는" 도구. 여기선 초안만 생성(실행=사람 승인). 운영 시 CAP OData POST로 교체.
_DRAFTS = []

def raw_draft_reorder(item: str, qty: int, supplier: str = "", reason: str = "") -> str:
    """발주 초안을 생성(기록)한다. 실제 발주가 아니라 승인 대기 초안."""
    draft = {"item": item, "qty": int(qty), "supplier": supplier, "reason": reason, "status": "DRAFT"}
    _DRAFTS.append(draft)
    return f"발주 초안 생성됨: {item} {qty}개 / 공급사 {supplier or '-'} (상태: DRAFT, 승인 대기)"

def get_drafts():
    return list(_DRAFTS)

def clear_drafts():
    _DRAFTS.clear()

# ─────────────────────────── 미충족 need(도구에 없는 정보/역량) 수집 ───────────────────────────
# 에이전트가 "타당하게 필요하나 도구로 못 얻는 것"을 기록 → 사람 확인 / 다음에 도구 추가 신호.
_NEEDS = []

def raw_need_info(topic: str, reason: str = "") -> str:
    """현재 도구로 얻을 수 없는 정보/역량을 요청(기록)한다."""
    _NEEDS.append({"topic": topic, "reason": reason})
    return (f"'{topic}' 은(는) 현재 도구로 확보 불가 → 미충족 요구로 기록됨(사람 확인/도구 추가 필요). "
            f"지금은 이 정보 없이, 가정을 명시하며 진행하라.")

def get_needs():
    return list(_NEEDS)

def clear_needs():
    _NEEDS.clear()

def raw_search_policy(query: str) -> str:
    """사내 정책을 AI Core Document Grounding(SDK 모듈)로 검색해 근거 기반 답변을 반환한다.
    REST 직접 호출 대신 gen_ai_hub.orchestration_v2 의 grounding 모듈을 사용한다."""
    if not config.GROUNDING_REPOSITORY_ID:
        return "정책 저장소가 설정되지 않음(GROUNDING_REPOSITORY_ID 없음)."
    from gen_ai_hub.orchestration_v2.service import OrchestrationService
    from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
    from gen_ai_hub.orchestration_v2.models.message import SystemMessage, UserMessage
    from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
    from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
    from gen_ai_hub.orchestration_v2.models.document_grounding import (
        DocumentGroundingFilter, DocumentGroundingConfig, DocumentGroundingPlaceholders, GroundingModuleConfig)

    grounding = GroundingModuleConfig(config=DocumentGroundingConfig(
        filters=[DocumentGroundingFilter(id="policy", data_repository_type="vector",
                                         data_repositories=[config.GROUNDING_REPOSITORY_ID])],
        placeholders=DocumentGroundingPlaceholders(input=["query"], output="grounding_response")))
    tmpl = Template(template=[
        SystemMessage(content="제공된 '정책' 발췌만 근거로 질문에 간결히 답하라. 근거에 없으면 '정책에 없음'이라고 답하라."),
        UserMessage(content="질문: {{?query}}\n정책:\n{{?grounding_response}}")])
    cfg = OrchestrationConfig(modules=ModuleConfig(
        prompt_templating=PromptTemplatingModuleConfig(prompt=tmpl, model=LLMModelDetails(name=config.LLM_MODEL)),
        grounding=grounding))
    res = OrchestrationService(api_url=config.orchestration_url()).run(
        config=cfg, placeholder_values={"query": query})
    return res.final_result.choices[0].message.content or "관련 정책을 찾지 못함."

# ─────────────────────────── Orchestration 등록용 도구 ───────────────────────────
@function_tool
def get_inventory() -> str:
    """현재 재고 목록(품목코드/이름/재고/안전재고/수입여부)을 조회한다."""
    return raw_get_inventory()

@function_tool
def get_suppliers(item: str) -> str:
    """특정 품목(item 코드)의 공급사 정보(단가/MOQ/리드타임/할인)를 조회한다."""
    return raw_get_suppliers(item)

@function_tool
def get_fx(base: str = "USD", quote: str = "KRW") -> str:
    """현재 환율을 외부 API에서 조회한다. 수입품 비용 판단용. 예: base=USD, quote=KRW."""
    return raw_get_fx(base, quote)

@function_tool
def search_policy(query: str) -> str:
    """조달/할인/반품 등 사내 정책 문서를 검색한다."""
    return raw_search_policy(query)

@function_tool
def draft_reorder(item: str, qty: int, supplier: str = "", reason: str = "") -> str:
    """발주 초안을 생성한다(행동). item 품목을 qty 수량으로, supplier 공급사에 발주하는 초안.
    실제 발주가 아니라 승인 대기 초안이다."""
    return raw_draft_reorder(item, qty, supplier, reason)

@function_tool
def need_info(topic: str, reason: str = "") -> str:
    """현재 도구로 얻을 수 없지만 과업에 '타당하게 필요한' 정보/역량을 요청한다.
    예: 날씨, 수요예측, 환율전망 등 제공 도구가 없을 때. (추측 대신 이 도구로 명시적으로 요청)"""
    return raw_need_info(topic, reason)

# 이름 → 실제 실행 함수 (루프에서 tool_call 실행용)
RAW = {
    "get_inventory": lambda **kw: raw_get_inventory(),
    "get_suppliers": lambda **kw: raw_get_suppliers(**kw),
    "get_fx": lambda **kw: raw_get_fx(**kw),
    "search_policy": lambda **kw: raw_search_policy(**kw),
    "draft_reorder": lambda **kw: raw_draft_reorder(**kw),
    "need_info": lambda **kw: raw_need_info(**kw),
}
ALL_TOOLS = [get_inventory, get_suppliers, get_fx, search_policy, draft_reorder, need_info]
