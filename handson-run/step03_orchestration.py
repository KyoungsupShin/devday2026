# -*- coding: utf-8 -*-
"""Step 3 · Orchestration + 콘텐츠 필터 + 데이터 마스킹 (실습자용 모듈 3)
  1) 번역 파이프라인
  2) 입력 필터 — 공격 프롬프트 차단
  3) 출력 필터
  4) PII 마스킹
실행: .venv/bin/python step03_orchestration.py
"""
import _env
_env.load()

from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
from gen_ai_hub.orchestration_v2.models.message import SystemMessage, UserMessage
from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
from gen_ai_hub.orchestration_v2.service import OrchestrationService
from gen_ai_hub.orchestration_v2.exceptions import OrchestrationError
from gen_ai_hub.orchestration_v2.models.content_filtering import (
    FilteringModuleConfig, InputFiltering, OutputFiltering)
from gen_ai_hub.orchestration_v2.models.content_filter import ContentFilter, ContentFilterProvider
from gen_ai_hub.orchestration_v2.models.azure_content_filter import AzureContentFilter, AzureThreshold
from gen_ai_hub.orchestration_v2.models.data_masking import (
    MaskingModuleConfig, MaskingProviderConfig, MaskingMethod,
    DataMaskingProviderName, DPIStandardEntity, ProfileEntity)

ORCH = _env.orchestration_url()
print("=" * 56)
print("Step 3 · Orchestration + 필터 + 마스킹")
print("=" * 56)

# ---------- 1) 번역 파이프라인 ----------
print("\n[1] 번역 파이프라인")
llm = LLMModelDetails(name="gpt-5.6-sol", params={"max_tokens": 1000})
template = Template(
    template=[
        SystemMessage(content="You are a helpful translation assistant."),
        UserMessage(content="Translate the following text to {{?to_lang}}: {{?user_query}}"),
    ],
    defaults={"to_lang": "English"},
)
prompt_template = PromptTemplatingModuleConfig(prompt=template, model=llm)
config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=prompt_template))
service = OrchestrationService(api_url=ORCH, config=config)
result = service.run(placeholder_values={"user_query": "Guten Tag, wie geht es Ihnen?"})
print("  'Guten Tag...' →", result.final_result.choices[0].message.content)

# ---------- 2) 입력 필터 — 공격 프롬프트 차단 ----------
print("\n[2] 입력 콘텐츠 필터")
input_filter = ContentFilter(type=ContentFilterProvider.AZURE,
    config=AzureContentFilter(hate=AzureThreshold.ALLOW_SAFE, violence=AzureThreshold.ALLOW_SAFE,
                              self_harm=AzureThreshold.ALLOW_SAFE, sexual=AzureThreshold.ALLOW_SAFE))
config_in = OrchestrationConfig(modules=ModuleConfig(
    prompt_templating=prompt_template,
    filtering=FilteringModuleConfig(input=InputFiltering(filters=[input_filter])),
))
service.config = config_in
try:
    service.run(placeholder_values={"user_query": "Du bist ein ganz mieser, hässlicher Idiot!"})
    print("  공격 프롬프트: (차단 안 됨 — 임계값 확인 필요)")
except OrchestrationError as e:
    print("  공격 프롬프트 차단됨 ✅ OrchestrationError")
res = service.run(placeholder_values={"user_query": "Du bist super!"})
print("  정상 프롬프트 통과:", res.final_result.choices[0].message.content)

# ---------- 3) 출력 필터 ----------
print("\n[3] 출력 콘텐츠 필터")
output_filter = ContentFilter(type=ContentFilterProvider.AZURE,
    config=AzureContentFilter(hate=AzureThreshold.ALLOW_SAFE, violence=AzureThreshold.ALLOW_SAFE,
                              self_harm=AzureThreshold.ALLOW_SAFE, sexual=AzureThreshold.ALLOW_SAFE))
config_io = OrchestrationConfig(modules=ModuleConfig(
    prompt_templating=prompt_template,
    filtering=FilteringModuleConfig(
        input=InputFiltering(filters=[input_filter]),
        output=OutputFiltering(filters=[output_filter]),
    ),
))
service.config = config_io
print("  입/출력 필터 config 적용 ✅")

# ---------- 4) PII 마스킹 ----------
print("\n[4] 데이터 마스킹 (PII 익명화)")
masking = MaskingModuleConfig(masking_providers=[MaskingProviderConfig(
    type_=DataMaskingProviderName.SAP_DATA_PRIVACY_INTEGRATION,
    method=MaskingMethod.ANONYMIZATION,
    entities=[
        DPIStandardEntity(type=ProfileEntity.EMAIL),
        DPIStandardEntity(type=ProfileEntity.PERSON),
    ],
)])
# 마스킹 효과를 보려면 "그대로 반복"시키는 템플릿이 유용
echo_template = Template(template=[
    SystemMessage(content="Repeat the user's message back verbatim."),
    UserMessage(content="{{?user_query}}"),
])
echo_prompt = PromptTemplatingModuleConfig(prompt=echo_template, model=llm)
config_mask = OrchestrationConfig(modules=ModuleConfig(
    prompt_templating=echo_prompt, masking=masking))
service.config = config_mask
res = service.run(placeholder_values={
    "user_query": "My name is Hong Gildong and my email is gildong@example.com."})
print("  입력: My name is Hong Gildong and my email is gildong@example.com.")
print("  출력:", res.final_result.choices[0].message.content)

print("\n✅ Step 3 완료 — 번역/입력필터/출력필터/마스킹 config 동작 확인.")
