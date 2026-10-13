# -*- coding: utf-8 -*-
"""Step 4 · Document Grounding (공개 help.sap.com) + Streaming (실습자용 모듈 4)
  1) 그라운딩 질의
  2) 스트리밍
  3) Step 1 환각 질문 재질의 → 비교
실행: .venv/bin/python step04_grounding.py
"""
import _env
_env.load()

from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
from gen_ai_hub.orchestration_v2.models.document_grounding import (
    DocumentGroundingFilter, DocumentGroundingConfig,
    DocumentGroundingPlaceholders, GroundingModuleConfig)
from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
from gen_ai_hub.orchestration_v2.models.message import SystemMessage, UserMessage
from gen_ai_hub.orchestration_v2.models.streaming import GlobalStreamOptions
from gen_ai_hub.orchestration_v2.service import OrchestrationService

ORCH = _env.orchestration_url()
print("=" * 56)
print("Step 4 · 공개 그라운딩 + 스트리밍")
print("=" * 56)

llm = LLMModelDetails(name="gpt-5.6-sol", params={"max_tokens": 1000})
template = Template(template=[
    SystemMessage(content="You are a helpful assistant."),
    UserMessage(content="""Answer the request using the provided context.
        Request: {{?user_query}}
        Context: {{?grounding_response}}
        """),
])
filters = [DocumentGroundingFilter(id="SAPHelp", data_repository_type="help.sap.com")]
grounding_config = GroundingModuleConfig(config=DocumentGroundingConfig(
    filters=filters,
    placeholders=DocumentGroundingPlaceholders(input=["user_query"], output="grounding_response"),
))
prompt_template = PromptTemplatingModuleConfig(prompt=template, model=llm)
config = OrchestrationConfig(modules=ModuleConfig(
    prompt_templating=prompt_template, grounding=grounding_config))
service = OrchestrationService(api_url=ORCH, config=config)

# 1) 그라운딩 질의
print("\n[1] 그라운딩 질의: 'What is Joule?'")
resp = service.run(placeholder_values={"user_query": "What is Joule?"})
print("  응답:", resp.final_result.choices[0].message.content[:300])

# 2) 스트리밍
print("\n[2] 스트리밍: 'What is SAP AI Core?'")
stream_config = OrchestrationConfig(
    modules=ModuleConfig(prompt_templating=prompt_template, grounding=grounding_config),
    stream=GlobalStreamOptions(enabled=True))
chunks = 0
print("  ", end="")
for chunk in service.stream(config=stream_config,
                            placeholder_values={"user_query": "What is SAP AI Core?"}):
    delta = chunk.final_result.choices[0].delta.content
    if delta:
        chunks += 1
        print(delta, end="", flush=True)
print(f"\n  (총 {chunks}개 청크 수신)")

# 3) Step 1 환각 질문 재질의 → 비교
print("\n[3] 환각 비교: 'How does the data masking of the orchestration service work?'")
resp = service.run(placeholder_values={
    "user_query": "How does the data masking of the orchestration service work?"})
print("  응답(그라운딩 있음):", resp.final_result.choices[0].message.content[:400])

print("\n✅ Step 4 완료 — 그라운딩/스트리밍 동작. [3]을 Step 1 [3]과 비교하세요.")
