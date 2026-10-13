# -*- coding: utf-8 -*-
"""
심화 데모 — 본편(A)에서 쓰지 않은 Orchestration 기능 3종.
실습생이 데모 UI에서 버튼으로 직접 실행·확인할 수 있게 각 함수가 '결과'와 '호출한 SDK 코드'를 함께 반환한다.
  1) Response Format : 자유 텍스트 vs JSON 스키마 강제 (구조화 출력)
  2) Streaming(토큰) : svc.stream() 으로 토큰을 흘려보냄
  3) Translation     : 영문 응답을 Orchestration 번역 모듈로 한국어 변환
모두 본편과 동일한 OrchestrationService / gpt-5.6-sol 사용.
"""
import os, json, base64
from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
from gen_ai_hub.orchestration_v2.models.message import SystemMessage, UserMessage
from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
from gen_ai_hub.orchestration_v2.models.response_format import (
    ResponseFormatJsonSchema, JSONResponseSchema)
from gen_ai_hub.orchestration_v2.models.translation import (
    TranslationModuleConfig, SAPDocumentTranslation, TranslationConfig)
from gen_ai_hub.orchestration_v2.models.multimodal_items import TextPart, ImagePart, ImageUrl
from gen_ai_hub.orchestration_v2.models.streaming import GlobalStreamOptions
from gen_ai_hub.orchestration_v2.service import OrchestrationService

from . import config

INVOICE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "setup", "sample_invoice.png")

def _llm():
    return LLMModelDetails(name=config.LLM_MODEL)

def _svc():
    return OrchestrationService(api_url=config.orchestration_url())

# ─────────────────────────── 1) Response Format (JSON 스키마 강제) ───────────────────────────
# 발주 초안을 "사람이 읽는 문장"이 아니라 "기계가 바로 쓰는 JSON"으로 강제 → CAP POST 로 직결.
_REORDER_SCHEMA = {
    "type": "object",
    "properties": {
        "item":     {"type": "string",  "description": "품목 코드"},
        "qty":      {"type": "integer", "description": "발주 수량"},
        "supplier": {"type": "string",  "description": "공급사 코드"},
        "reason":   {"type": "string",  "description": "발주 사유(한 문장)"},
        "priority": {"type": "string",  "enum": ["high", "normal", "low"]},
    },
    "required": ["item", "qty", "supplier", "reason", "priority"],
    "additionalProperties": False,
}

_RF_CODE = '''from gen_ai_hub.orchestration_v2.models.response_format import (
    ResponseFormatJsonSchema, JSONResponseSchema)

rf = ResponseFormatJsonSchema(type_="json_schema", json_schema=JSONResponseSchema(
        name="reorder_draft", description="발주 초안", strict=True,
        **{"schema": REORDER_SCHEMA}))    # ← schema 는 alias 라 이렇게 전달(함정!)
tmpl = Template(template=[SystemMessage(...), UserMessage("{{?req}}")],
                response_format=rf)                          # ← Template 에 부착
res = svc.run(config=cfg, placeholder_values={"req": req})
# res...message.content 는 '항상' 스키마를 만족하는 JSON 문자열'''

def demo_response_format(req: str = "A 품목이 안전재고 미만이라 S1에서 긴급 발주해야 함"):
    """같은 요청을 (a) 자유 텍스트, (b) JSON 스키마 강제 로 각각 생성해 나란히 반환."""
    svc = _svc()
    sys_msg = SystemMessage(content="너는 재고 담당자다. 발주 초안을 작성하라.")
    user = UserMessage(content="{{?req}}")

    # (a) 자유 텍스트 (response_format 없음)
    tmpl_text = Template(template=[sys_msg, user])
    cfg_text = OrchestrationConfig(modules=ModuleConfig(
        prompt_templating=PromptTemplatingModuleConfig(prompt=tmpl_text, model=_llm())))
    free_text = svc.run(config=cfg_text, placeholder_values={"req": req}
                        ).final_result.choices[0].message.content

    # (b) JSON 스키마 강제  (schema_ 의 alias 가 'schema' 라 alias 키로 전달해야 함)
    rf = ResponseFormatJsonSchema(type_="json_schema", json_schema=JSONResponseSchema(
        name="reorder_draft", description="발주 초안", strict=True, **{"schema": _REORDER_SCHEMA}))
    tmpl_json = Template(template=[sys_msg, user], response_format=rf)
    cfg_json = OrchestrationConfig(modules=ModuleConfig(
        prompt_templating=PromptTemplatingModuleConfig(prompt=tmpl_json, model=_llm())))
    raw = svc.run(config=cfg_json, placeholder_values={"req": req}
                 ).final_result.choices[0].message.content
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {"_raw": raw}

    return {
        "req": req,
        "free_text": free_text,
        "schema": _REORDER_SCHEMA,
        "json_result": parsed,
        "code": _RF_CODE,
    }

# ─────────────────────────── 2) Streaming (토큰 스트리밍) ───────────────────────────
_STREAM_CODE = '''from gen_ai_hub.orchestration_v2.models.streaming import GlobalStreamOptions
# 스트리밍을 켜려면 OrchestrationConfig(stream=GlobalStreamOptions(enabled=True))
cfg = OrchestrationConfig(modules=..., stream=GlobalStreamOptions(enabled=True))
# svc.run() 대신 svc.stream() → 조각(delta)으로 흘려보냄
for chunk in svc.stream(config=cfg, placeholder_values={"topic": topic}):
    delta = chunk.final_result.choices[0].delta.content
    if delta:
        yield delta           # 한 조각씩 화면에 출력'''

def _extract_delta(chunk):
    """스트리밍 chunk에서 텍스트 조각을 안전하게 꺼낸다(SDK 버전차 대비)."""
    try:
        return chunk.orchestration_result.choices[0].delta.content or ""
    except Exception:
        pass
    try:
        return chunk.final_result.choices[0].delta.content or ""
    except Exception:
        return ""

def demo_stream(topic: str = "재고 자율 에이전트의 장점"):
    """토큰 스트리밍 제너레이터 — 조각(delta) 텍스트를 순서대로 yield."""
    svc = _svc()
    tmpl = Template(template=[
        SystemMessage(content="요청 주제를 3~4문장으로, 한국어로 설명하라."),
        UserMessage(content="{{?topic}}")])
    cfg = OrchestrationConfig(
        modules=ModuleConfig(
            prompt_templating=PromptTemplatingModuleConfig(prompt=tmpl, model=_llm())),
        stream=GlobalStreamOptions(enabled=True, chunk_size=20))   # ← 스트리밍 켜기
    for chunk in svc.stream(config=cfg, placeholder_values={"topic": topic}):
        d = _extract_delta(chunk)
        if d:
            yield d

# ─────────────────────────── 3) Translation (번역 모듈) ───────────────────────────
_TR_CODE = '''from gen_ai_hub.orchestration_v2.models.translation import (
    TranslationModuleConfig, SAPDocumentTranslation, TranslationConfig)

translation = TranslationModuleConfig(                        # 출력(output) 번역
    output=SAPDocumentTranslation(type_="sap_document_translation",
        config=TranslationConfig(source_language="en-US", target_language="ko-KR")))
cfg = OrchestrationConfig(modules=ModuleConfig(
        prompt_templating=..., translation=translation))     # ← 모듈 슬롯에 부착'''

def demo_translation(topic: str = "benefits of an autonomous inventory agent"):
    """LLM이 영어로 답하게 한 뒤, Orchestration 번역 모듈로 한국어로 자동 변환.
    (a) 번역 모듈 OFF = 영어 원문, (b) ON = 한국어 — 를 나란히 반환."""
    svc = _svc()
    sys_msg = SystemMessage(content="Answer ONLY in English, in 3 sentences.")
    user = UserMessage(content="{{?topic}}")

    # (a) 번역 OFF → 영어 원문
    cfg_off = OrchestrationConfig(modules=ModuleConfig(
        prompt_templating=PromptTemplatingModuleConfig(
            prompt=Template(template=[sys_msg, user]), model=_llm())))
    english = svc.run(config=cfg_off, placeholder_values={"topic": topic}
                     ).final_result.choices[0].message.content

    # (b) 번역 ON → 출력(en-US → ko-KR)
    translation = TranslationModuleConfig(
        output=SAPDocumentTranslation(type_="sap_document_translation",
            config=TranslationConfig(source_language="en-US", target_language="ko-KR")))
    cfg_on = OrchestrationConfig(modules=ModuleConfig(
        prompt_templating=PromptTemplatingModuleConfig(
            prompt=Template(template=[sys_msg, user]), model=_llm()),
        translation=translation))
    korean = svc.run(config=cfg_on, placeholder_values={"topic": topic}
                    ).final_result.choices[0].message.content

    return {"topic": topic, "english": english, "korean": korean, "code": _TR_CODE}

# ─────────────────────────── 4) Multimodal (이미지 입력) ───────────────────────────
# 공급사 송장 이미지를 '보고' 품목/수량/금액을 추출 → Response Format 으로 구조화 JSON.
_MM_SCHEMA = {
    "type": "object",
    "properties": {
        "supplier":       {"type": "string"},
        "item":           {"type": "string"},
        "item_name":      {"type": "string"},
        "qty":            {"type": "integer"},
        "unit_price_usd": {"type": "number"},
        "total_usd":      {"type": "number"},
        "lead_days":      {"type": "integer"},
        "discount":       {"type": "string"},
    },
    # strict 모드: required 에 모든 property 키가 포함돼야 함
    "required": ["supplier", "item", "item_name", "qty",
                 "unit_price_usd", "total_usd", "lead_days", "discount"],
    "additionalProperties": False,
}

_MM_CODE = '''from gen_ai_hub.orchestration_v2.models.multimodal_items import TextPart, ImagePart, ImageUrl

data = base64.b64encode(open("sample_invoice.png","rb").read()).decode()
user = UserMessage(content=[                                  # ← content 가 '리스트'(텍스트+이미지)
    TextPart(text="이 송장에서 공급사/품목/수량/단가/금액을 JSON으로 추출하라.", type_="text"),
    ImagePart(image_url=ImageUrl(url=f"data:image/png;base64,{data}"), type_="image_url")])
tmpl = Template(template=[SystemMessage(...), user], response_format=rf)  # 멀티모달 + 구조화
res = svc.run(config=cfg)'''

def demo_multimodal():
    """송장 이미지를 모델에 입력 → 품목/수량/금액을 구조화 JSON으로 추출."""
    svc = _svc()
    data = base64.b64encode(open(INVOICE_PATH, "rb").read()).decode()
    url = f"data:image/png;base64,{data}"
    user = UserMessage(content=[
        TextPart(text="이 공급사 송장 이미지에서 공급사코드/품목코드/품명/수량/단가(USD)/"
                      "금액(USD)/리드타임/할인조건을 읽어 추출하라.", type_="text"),
        ImagePart(image_url=ImageUrl(url=url), type_="image_url")])
    rf = ResponseFormatJsonSchema(type_="json_schema", json_schema=JSONResponseSchema(
        name="invoice_extract", description="송장 추출", strict=True, **{"schema": _MM_SCHEMA}))
    tmpl = Template(template=[
        SystemMessage(content="너는 이미지를 읽어 구조화 데이터를 추출하는 비서다."), user],
        response_format=rf)
    cfg = OrchestrationConfig(modules=ModuleConfig(
        prompt_templating=PromptTemplatingModuleConfig(prompt=tmpl, model=_llm())))
    try:
        raw = svc.run(config=cfg).final_result.choices[0].message.content
        try:
            extracted = json.loads(raw)
        except Exception:
            extracted = {"_raw": raw}
        return {"image": "setup/sample_invoice.png", "extracted": extracted,
                "schema": _MM_SCHEMA, "code": _MM_CODE, "supported": True}
    except Exception as e:
        return {"image": "setup/sample_invoice.png", "extracted": None,
                "schema": _MM_SCHEMA, "code": _MM_CODE, "supported": False,
                "error": f"{type(e).__name__}: {e}"}
