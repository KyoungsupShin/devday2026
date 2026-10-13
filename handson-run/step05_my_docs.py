# -*- coding: utf-8 -*-
"""Step 5 · 내 문서 그라운딩 (AI Core vector 저장소) (실습자용 모듈 5)
  - 모듈 4 코드에서 '그라운딩 필터만' 내 벡터 저장소로 교체
  - GROUNDING_REPOSITORY_ID 없으면 문서 있는 첫 저장소 자동 선택
  - 먼저 retrieval/search 로 '검색된 청크'를 보고, 그다음 LLM 답변
실행: .venv/bin/python step05_my_docs.py
"""
import _env
_env.load()

import os
import requests

from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
from gen_ai_hub.orchestration_v2.models.document_grounding import (
    DocumentGroundingFilter, DocumentGroundingConfig,
    DocumentGroundingPlaceholders, GroundingModuleConfig)
from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
from gen_ai_hub.orchestration_v2.models.message import SystemMessage, UserMessage
from gen_ai_hub.orchestration_v2.service import OrchestrationService

print("=" * 56)
print("Step 5 · 내 문서 그라운딩")
print("=" * 56)

base = os.getenv("AICORE_BASE_URL").rstrip("/")
h = _env.headers()
DG = f"{base}/v2/lm/document-grounding"

# 1) 저장소 id 결정 (env 우선, 없으면 문서 있는 첫 저장소)
repo_id = os.getenv("GROUNDING_REPOSITORY_ID")
if not repo_id:
    cols = requests.get(f"{DG}/vector/collections", headers=h, timeout=30).json()
    cols = cols.get("resources", cols) if isinstance(cols, dict) else cols
    for c in cols:
        cid = c.get("id")
        n = requests.get(f"{DG}/vector/collections/{cid}/documents",
                         headers=h, timeout=30).json().get("count", 0)
        if n and int(n) > 0:
            repo_id = cid
            print(f"  (자동 선택) title={c.get('title')} docs={n}")
            break
assert repo_id, "문서가 든 저장소를 찾지 못함"
print("  저장소 id:", repo_id)

# 2) 질문 — 저장소 내용에 맞춰 (procurement policy 가정 + 일반 질문 둘 다 시도)
QUESTION = os.getenv("Q", "What does this document say? Summarize the key points.")

# 2a) 먼저 검색된 청크 보기 (retrieval/search)
print(f"\n[1] 검색된 청크 보기 — '{QUESTION}'")
body = {"query": QUESTION,
        "filters": [{"id": "f", "dataRepositoryType": "vector", "dataRepositories": [repo_id]}]}
r = requests.post(f"{DG}/retrieval/search", headers=h, json=body, timeout=60).json()
found = 0
for res in r.get("results", []):
    for rr in res.get("results", []):
        for doc in rr.get("dataRepository", {}).get("documents", []):
            for ch in doc.get("chunks", []):
                found += 1
                score = ch.get("searchScores", {}).get("aggregatedScore", {}).get("value", 0)
                print(f"  [{found}] score={score:.3f}  {ch.get('content','')[:120]}")
if not found:
    print("  (검색된 청크 없음)")

# 3) 그라운딩 질의 — 모듈 4와 '필터만' 다름
print(f"\n[2] 그라운딩 LLM 답변 — '{QUESTION}'")
llm = LLMModelDetails(name="gpt-5.6-sol", params={"max_tokens": 1000})
template = Template(template=[
    SystemMessage(content="You are a helpful assistant. Answer only from the provided context."),
    UserMessage(content="""Request: {{?user_query}}
        Context: {{?grounding_response}}
        """),
])
filters = [DocumentGroundingFilter(
    id="MyDocs", data_repository_type="vector", data_repositories=[repo_id])]
grounding_config = GroundingModuleConfig(config=DocumentGroundingConfig(
    filters=filters,
    placeholders=DocumentGroundingPlaceholders(input=["user_query"], output="grounding_response")))
prompt_template = PromptTemplatingModuleConfig(prompt=template, model=llm)
config = OrchestrationConfig(modules=ModuleConfig(
    prompt_templating=prompt_template, grounding=grounding_config))
service = OrchestrationService(api_url=_env.orchestration_url(), config=config)
resp = service.run(placeholder_values={"user_query": QUESTION})
print("  응답:", resp.final_result.choices[0].message.content[:500])

print("\n✅ Step 5 완료 — 모듈 4 대비 '필터만' 바꿔 내 문서 기반 답변.")
