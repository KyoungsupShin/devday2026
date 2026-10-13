#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAP Generative AI Hub 핸즈온 — 라이브 스모크 테스트

사용법:
  1) codejam 저장소의 exercises/ 폴더로 이 파일을 복사
     (init_env.py, variables.py, documents/ 가 같은 폴더에 있어야 함)
  2) variables.py 에 공유 값 입력 (RESOURCE_GROUP, *_DEPLOYMENT_ID,
     AICORE_ORCHESTRATION_DEPLOYMENT_URL, GROUNDING_REPOSITORY_ID)
  3) 가상환경 활성 후:  python smoke_test.py

각 모듈을 실제로 1회씩 호출해 통과/실패를 출력합니다.
자격증명/배포가 올바르면 전부 [PASS] 가 나와야 합니다.
"""
import sys, traceback

def banner(t): print("\n" + "=" * 8, t)
def ok(m):   print(f"  [PASS] {m}")
def bad(m, e): print(f"  [FAIL] {m}\n         -> {type(e).__name__}: {e}")

# ---------------------------------------------------------------- 0. 연결
banner("0. 환경/연결")
try:
    import init_env, variables, importlib
    importlib.reload(variables)
    init_env.set_environment_variables()
    assert variables.AICORE_ORCHESTRATION_DEPLOYMENT_URL, "Orchestration URL 비어있음"
    ORCH_URL = variables.AICORE_ORCHESTRATION_DEPLOYMENT_URL
    ok(f"연결 값 로드 (RG={variables.RESOURCE_GROUP})")
except Exception as e:
    bad("연결 값 로드 실패 — 이후 테스트 중단", e)
    sys.exit(1)

LLM = "gpt-5.6-sol"   # 배포된 모델명으로 바꾸세요

# ---------------------------------------------------------------- 1. LLM
banner("1. LLM 프롬프트 (chat)")
try:
    from gen_ai_hub.proxy.native.openai import chat
    r = chat.completions.create(model_name=LLM,
        messages=[{"role": "user", "content": "Say 'hello' in one word."}])
    ok("chat 응답: " + r.choices[0].message.content.strip()[:40])
except Exception as e:
    bad("chat 호출", e)

# ---------------------------------------------------------------- 2. 임베딩
banner("2. 임베딩 & 유사도")
try:
    from gen_ai_hub.proxy.native.openai import embeddings
    from scipy import spatial
    def emb(t): return embeddings.create(input=t, model_name="text-embedding-3-small").data[0].embedding
    a, b = emb("apple"), emb("orange")
    sim = 1 - spatial.distance.cosine(a, b)
    ok(f"임베딩 dim={len(a)}, apple~orange 유사도={sim:.3f}")
except Exception as e:
    bad("임베딩/유사도", e)

# ---------------------------------------------------------------- 3. Orchestration + 필터
banner("3. Orchestration + 콘텐츠 필터")
try:
    from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
    from gen_ai_hub.orchestration_v2.models.message import SystemMessage, UserMessage
    from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
    from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
    from gen_ai_hub.orchestration_v2.service import OrchestrationService
    from gen_ai_hub.orchestration_v2.exceptions import OrchestrationError
    from gen_ai_hub.orchestration_v2.models.content_filtering import FilteringModuleConfig, InputFiltering
    from gen_ai_hub.orchestration_v2.models.content_filter import ContentFilter, ContentFilterProvider
    from gen_ai_hub.orchestration_v2.models.azure_content_filter import AzureContentFilter, AzureThreshold

    tmpl = Template(template=[SystemMessage(content="You are a translation assistant."),
        UserMessage(content="Translate to {{?to_lang}}: {{?user_query}}")], defaults={"to_lang": "English"})
    pt = PromptTemplatingModuleConfig(prompt=tmpl, model=LLMModelDetails(name=LLM))
    svc = OrchestrationService(api_url=ORCH_URL,
        config=OrchestrationConfig(modules=ModuleConfig(prompt_templating=pt)))
    res = svc.run(placeholder_values={"user_query": "Guten Tag"})
    ok("orchestration 번역: " + res.final_result.choices[0].message.content.strip()[:40])

    inf = ContentFilter(type=ContentFilterProvider.AZURE, config=AzureContentFilter(
        hate=AzureThreshold.ALLOW_SAFE, violence=AzureThreshold.ALLOW_SAFE,
        self_harm=AzureThreshold.ALLOW_SAFE, sexual=AzureThreshold.ALLOW_SAFE))
    svc.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=pt,
        filtering=FilteringModuleConfig(input=InputFiltering(filters=[inf]))))
    try:
        svc.run(placeholder_values={"user_query": "Du bist ein ganz mieser Entwickler!"})
        print("  [WARN] 공격 프롬프트가 차단되지 않음 — 임계값 확인")
    except OrchestrationError:
        ok("입력 필터가 공격 프롬프트를 차단함")
except Exception as e:
    bad("Orchestration/필터", e)

# ---------------------------------------------------------------- 3b. 데이터 마스킹
banner("3b. 데이터 마스킹 (PII)")
try:
    from gen_ai_hub.orchestration_v2.models.data_masking import (
        MaskingModuleConfig, MaskingProviderConfig, MaskingMethod,
        DataMaskingProviderName, DPIStandardEntity, ProfileEntity)
    masking = MaskingModuleConfig(masking_providers=[MaskingProviderConfig(
        type_=DataMaskingProviderName.SAP_DATA_PRIVACY_INTEGRATION,
        method=MaskingMethod.ANONYMIZATION,
        entities=[DPIStandardEntity(type=ProfileEntity.EMAIL),
                  DPIStandardEntity(type=ProfileEntity.PERSON)])])
    svc.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=pt, masking=masking))
    res = svc.run(placeholder_values={"user_query": "내 이름은 홍길동, 이메일은 gildong@example.com. 한 문장으로 답해줘."})
    ok("마스킹 적용 응답 수신: " + res.final_result.choices[0].message.content.strip()[:40])
except Exception as e:
    bad("데이터 마스킹", e)

# ---------------------------------------------------------------- 4. Grounding (공개)
banner("4. Document Grounding (help.sap.com)")
try:
    from gen_ai_hub.orchestration_v2.models.document_grounding import (
        DocumentGroundingFilter, DocumentGroundingConfig, DocumentGroundingPlaceholders, GroundingModuleConfig)
    g = GroundingModuleConfig(config=DocumentGroundingConfig(
        filters=[DocumentGroundingFilter(id="SAPHelp", data_repository_type="help.sap.com")],
        placeholders=DocumentGroundingPlaceholders(input=["user_query"], output="grounding_response")))
    tmpl2 = Template(template=[SystemMessage(content="Answer from context."),
        UserMessage(content="Request: {{?user_query}}\nContext: {{?grounding_response}}")])
    pt2 = PromptTemplatingModuleConfig(prompt=tmpl2, model=LLMModelDetails(name=LLM))
    svc.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=pt2, grounding=g))
    res = svc.run(placeholder_values={"user_query": "What is Joule?"})
    ok("grounding 답변: " + res.final_result.choices[0].message.content.strip()[:50] + " ...")
except Exception as e:
    bad("Grounding(help.sap.com)", e)

# ---------------------------------------------------------------- 5. 내 문서 그라운딩
banner("5. 내 문서 그라운딩 (vector)")
repo = getattr(variables, "GROUNDING_REPOSITORY_ID", None)
if not repo:
    print("  [SKIP] variables.GROUNDING_REPOSITORY_ID 없음 — 공유 저장소 id 설정 후 재시도")
else:
    try:
        gv = GroundingModuleConfig(config=DocumentGroundingConfig(
            filters=[DocumentGroundingFilter(id="MyDocs", data_repository_type="vector",
                                             data_repositories=[repo])],
            placeholders=DocumentGroundingPlaceholders(input=["user_query"], output="grounding_response")))
        svc.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=pt2, grounding=gv))
        res = svc.run(placeholder_values={"user_query": "What is data masking in the orchestration service?"})
        ok("내문서 grounding 답변: " + res.final_result.choices[0].message.content.strip()[:50] + " ...")
    except Exception as e:
        bad("내 문서 Grounding(vector)", e)

# ---------------------------------------------------------------- 6. 메모리 챗봇
banner("6. 메모리 챗봇")
try:
    svc.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=PromptTemplatingModuleConfig(
        prompt=Template(template=[SystemMessage(content="You are helpful."),
                                  UserMessage(content="{{?user_query}}")]),
        model=LLMModelDetails(name=LLM))))
    history = []
    r1 = svc.run(config=svc.config, placeholder_values={"user_query": "My name is Jin."}, history=history)
    history = r1.intermediate_results.templating
    history.append(r1.final_result.choices[0].message)
    r2 = svc.run(config=svc.config, placeholder_values={"user_query": "What is my name?"}, history=history)
    ans = r2.final_result.choices[0].message.content
    ok(("이름 기억함" if "Jin" in ans else "응답(기억 확인 필요): ") + ans.strip()[:40])
except Exception as e:
    bad("메모리 챗봇", e)

print("\n완료. 위에서 [FAIL] 이 없으면 핸즈온 코드가 이 환경에서 동작합니다.")
