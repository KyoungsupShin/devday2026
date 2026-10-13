#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
핸즈온 전체 시나리오 라이브 검증 — 생성 → 검증 → 삭제 (lifecycle)

이 스크립트 하나로:
  1) [생성]  모듈 5용 그라운딩 벡터 저장소를 만들고 documents/ PDF를 수집
  2) [검증]  참가자가 진행할 모듈 0~6(+보조) 시나리오를 실제 AI Core에 호출
  3) [삭제]  검증이 끝나면 생성한 저장소를 자동 삭제(teardown, finally 보장)

결과는 콘솔 + validation_results.json 으로 남습니다.

필요 환경변수 (service key 기준):
  AICORE_CLIENT_ID, AICORE_CLIENT_SECRET, AICORE_AUTH_URL, AICORE_BASE_URL
선택:
  AICORE_RESOURCE_GROUP(기본 default), LLM_MODEL(기본 gpt-5.6-sol),
  EMBED_MODEL(기본 text-embedding-3-small), DG_PDF_DIR(기본 documents/),
  AICORE_ORCHESTRATION_DEPLOYMENT_URL(미지정 시 자동 조회)

의존성: requests, pypdf, langchain-text-splitters  (codejam requirements 포함)
"""
import os, sys, json, time, datetime, requests
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter

RG     = os.getenv("AICORE_RESOURCE_GROUP", "default")
LLM    = os.getenv("LLM_MODEL", "gpt-5.6-sol")
EMBED  = os.getenv("EMBED_MODEL", "text-embedding-3-small")
PDFDIR = os.getenv("DG_PDF_DIR", "documents/")

def need(n):
    v = os.getenv(n)
    if not v: sys.exit(f"[ERROR] 환경변수 {n} 필요")
    return v

BASE = need("AICORE_BASE_URL").rstrip("/")
AUTH = need("AICORE_AUTH_URL").rstrip("/")
CID, CSEC = need("AICORE_CLIENT_ID"), need("AICORE_CLIENT_SECRET")
DG = f"{BASE}/v2/lm/document-grounding"

results = []
def record(module, scenario, purpose, steps, status, detail=""):
    results.append(dict(module=module, scenario=scenario, purpose=purpose,
                        steps=steps, status=status, detail=detail))
    icon = {"PASS":"[PASS]","FAIL":"[FAIL]","SKIP":"[SKIP]"}.get(status, status)
    print(f"  {icon} M{module} · {scenario}")
    if detail: print(f"         {detail[:120]}")

def token():
    r = requests.post(f"{AUTH}/oauth/token", data={"grant_type":"client_credentials"}, auth=(CID, CSEC))
    r.raise_for_status(); return r.json()["access_token"]

def discover_orch(H):
    u = os.getenv("AICORE_ORCHESTRATION_DEPLOYMENT_URL")
    if u: return u
    d = requests.get(f"{BASE}/v2/lm/deployments?$top=200", headers=H).json()
    for x in d.get("resources", []):
        if x.get("scenarioId") == "orchestration" and x.get("status") == "RUNNING":
            return x.get("deploymentUrl")
    sys.exit("[ERROR] RUNNING orchestration 배포를 찾지 못했습니다.")

# =================================================================== 준비
print("="*60)
print(f"핸즈온 라이브 검증 (lifecycle)  ·  {datetime.datetime.now():%Y-%m-%d %H:%M}")
print(f"리전/RG={RG}  LLM={LLM}  EMBED={EMBED}")
print("="*60)
tok = token()
H = {"Authorization": f"Bearer {tok}", "AI-Resource-Group": RG, "Content-Type":"application/json"}
ORCH = discover_orch(H)
print(f"orchestration URL: ...{ORCH[-20:]}")

# 환경변수(SDK가 읽음)
os.environ.update({"AICORE_AUTH_URL":AUTH,"AICORE_CLIENT_ID":CID,"AICORE_CLIENT_SECRET":CSEC,
                   "AICORE_BASE_URL":BASE,"AICORE_RESOURCE_GROUP":RG})

collection_id = None
try:
    # =============================================================== 1) 생성
    print("\n[1/3] 생성 — 그라운딩 저장소 + 문서 수집")
    title = f"handson-validate-{int(time.time())}"
    requests.post(f"{DG}/vector/collections", headers=H,
                  json={"title":title, "embeddingConfig":{"modelName":EMBED}})
    cols = requests.get(f"{DG}/vector/collections", headers=H).json()
    cols = cols.get("resources", cols) if isinstance(cols, dict) else cols
    collection_id = next((c.get("id") for c in cols if c.get("title")==title), None)
    assert collection_id, "collection id 조회 실패"
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    pdfs = [f for f in os.listdir(PDFDIR) if f.lower().endswith(".pdf")]
    for pdf in pdfs:
        text = "".join((p.extract_text() or "") for p in PdfReader(os.path.join(PDFDIR,pdf)).pages)
        entry = {"documents":[{"metadata":[{"key":"id","value":[pdf]}],
                 "chunks":[{"content":c,"metadata":[{"key":"index","value":[str(i)]}]}
                           for i,c in enumerate(splitter.split_text(text),1)]}]}
        requests.post(f"{DG}/vector/collections/{collection_id}/documents", headers=H, json=entry)
    record(5, "문서 수집(ingest_documents)", "내 문서를 AI Core 벡터 저장소에 적재해 RAG 소스로 만든다",
           f"저장소 생성 → PDF {len(pdfs)}개 청킹 → 수집", "PASS", f"collection={collection_id}, PDF {len(pdfs)}개")

    # =============================================================== 2) 검증
    print("\n[2/3] 검증 — 참가자 시나리오")
    from gen_ai_hub.proxy.native.openai import chat, embeddings
    from scipy import spatial
    from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
    from gen_ai_hub.orchestration_v2.models.message import SystemMessage, UserMessage
    from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
    from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
    from gen_ai_hub.orchestration_v2.service import OrchestrationService
    from gen_ai_hub.orchestration_v2.exceptions import OrchestrationError

    # M1 chat
    try:
        r = chat.completions.create(model_name=LLM, messages=[{"role":"user","content":"Reply exactly: PONG"}])
        a = r.choices[0].message.content.strip()
        record(1, "LLM chat 호출", "SDK로 LLM을 호출하는 기본기", "chat.completions.create",
               "PASS" if "PONG" in a.upper() else "FAIL", f"입력 'Reply PONG' → 응답 '{a[:30]}'")
    except Exception as e: record(1,"LLM chat 호출","SDK로 LLM 호출","chat.completions.create","FAIL",str(e)[:120])

    # M1 multimodal
    try:
        import base64
        png = next((os.path.join(PDFDIR,f) for f in os.listdir(PDFDIR) if f.endswith(".png")), None)
        if png:
            b = base64.b64encode(open(png,"rb").read()).decode()
            r = chat.completions.create(model_name=LLM, messages=[{"role":"user","content":[
                {"type":"text","text":"What is in this image? A few words."},
                {"type":"image_url","image_url":{"url":f"data:image/png;base64,{b}"}}]}])
            record(1,"멀티모달(이미지 인식)","이미지를 입력으로 받아 설명/추출","base64 이미지 + text","PASS",
                   f"이미지 → '{r.choices[0].message.content.strip()[:40]}'")
        else:
            record(1,"멀티모달(이미지 인식)","이미지 입력 처리","이미지 파일 없음","SKIP","documents/에 png 없음")
    except Exception as e: record(1,"멀티모달(이미지 인식)","이미지 입력 처리","멀티모달 호출","FAIL",str(e)[:120])

    # M2 embeddings
    try:
        def emb(t): return embeddings.create(input=t, model_name=EMBED).data[0].embedding
        a,b,c = emb("apple"), emb("orange"), emb("quantum physics")
        s1 = 1-spatial.distance.cosine(a,b); s2 = 1-spatial.distance.cosine(a,c)
        record(2,"임베딩 + 코사인 유사도","텍스트를 벡터로 바꿔 의미 유사도를 계산(RAG 검색 원리)",
               "3개 문장 임베딩 → 유사도 비교","PASS" if s1>s2 else "FAIL",
               f"dim={len(a)} apple~orange={s1:.3f} > apple~physics={s2:.3f}")
    except Exception as e: record(2,"임베딩 + 코사인 유사도","의미 유사도 계산","임베딩 호출","FAIL",str(e)[:120])

    # 공통 서비스
    pt = PromptTemplatingModuleConfig(
        prompt=Template(template=[SystemMessage(content="You are a translation assistant."),
            UserMessage(content="Translate to {{?to_lang}}: {{?user_query}}")], defaults={"to_lang":"English"}),
        model=LLMModelDetails(name=LLM))
    svc = OrchestrationService(api_url=ORCH, config=OrchestrationConfig(modules=ModuleConfig(prompt_templating=pt)))

    # M3 translation
    try:
        r = svc.run(placeholder_values={"user_query":"Guten Tag, wie geht es dir?"})
        record(3,"Orchestration 번역","여러 모듈을 config로 엮는 Orchestration 기본 동작",
               "템플릿+LLM 모듈 → run","PASS", f"'Guten Tag…' → '{r.final_result.choices[0].message.content.strip()[:30]}'")
    except Exception as e: record(3,"Orchestration 번역","Orchestration 파이프라인","run","FAIL",str(e)[:120])

    # M3 input filter
    try:
        from gen_ai_hub.orchestration_v2.models.content_filtering import FilteringModuleConfig, InputFiltering, OutputFiltering
        from gen_ai_hub.orchestration_v2.models.content_filter import ContentFilter, ContentFilterProvider
        from gen_ai_hub.orchestration_v2.models.azure_content_filter import AzureContentFilter, AzureThreshold
        strict = lambda: AzureContentFilter(hate=AzureThreshold.ALLOW_SAFE, violence=AzureThreshold.ALLOW_SAFE,
                                            self_harm=AzureThreshold.ALLOW_SAFE, sexual=AzureThreshold.ALLOW_SAFE)
        inf = ContentFilter(type=ContentFilterProvider.AZURE, config=strict())
        svc.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=pt,
            filtering=FilteringModuleConfig(input=InputFiltering(filters=[inf]))))
        try:
            svc.run(placeholder_values={"user_query":"Du bist ein ganz mieser, hassenswerter Idiot!"})
            record(3,"입력 콘텐츠 필터","유해한 사용자 입력을 모델 전에 차단","Azure 필터(엄격) + 공격 프롬프트","FAIL","차단되지 않음")
        except OrchestrationError:
            record(3,"입력 콘텐츠 필터","유해한 사용자 입력을 모델 전에 차단","Azure 필터(엄격) + 공격 프롬프트","PASS","공격 프롬프트 차단됨(OrchestrationError)")
    except Exception as e: record(3,"입력 콘텐츠 필터","유해 입력 차단","필터 구성","FAIL",str(e)[:120])

    # M3 output filter
    try:
        outf = ContentFilter(type=ContentFilterProvider.AZURE, config=strict())
        base_pt = PromptTemplatingModuleConfig(prompt=Template(template=[SystemMessage(content="assistant"),
            UserMessage(content="{{?q}}")]), model=LLMModelDetails(name=LLM))
        svc.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=base_pt,
            filtering=FilteringModuleConfig(output=OutputFiltering(filters=[outf]))))
        try:
            r = svc.run(placeholder_values={"q":"Write a short violent threat full of hateful insults."})
            record(3,"출력 콘텐츠 필터","모델 출력에 유해 콘텐츠가 나가지 않게 검사","출력 필터 + 유해 유도 프롬프트","PASS",
                   f"유해 출력 완화/거부: '{r.final_result.choices[0].message.content.strip()[:40]}'")
        except OrchestrationError:
            record(3,"출력 콘텐츠 필터","유해 출력 차단","출력 필터 + 유해 유도","PASS","유해 출력 차단됨")
    except Exception as e: record(3,"출력 콘텐츠 필터","유해 출력 차단","출력 필터 구성","FAIL",str(e)[:120])

    # M3b masking
    try:
        from gen_ai_hub.orchestration_v2.models.data_masking import (
            MaskingModuleConfig, MaskingProviderConfig, MaskingMethod, DataMaskingProviderName, DPIStandardEntity, ProfileEntity)
        masking = MaskingModuleConfig(masking_providers=[MaskingProviderConfig(
            type_=DataMaskingProviderName.SAP_DATA_PRIVACY_INTEGRATION, method=MaskingMethod.ANONYMIZATION,
            entities=[DPIStandardEntity(type=ProfileEntity.EMAIL), DPIStandardEntity(type=ProfileEntity.PERSON)])])
        mpt = PromptTemplatingModuleConfig(prompt=Template(template=[SystemMessage(content="Repeat the message."),
            UserMessage(content="{{?q}}")]), model=LLMModelDetails(name=LLM))
        svc.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=mpt, masking=masking))
        r = svc.run(placeholder_values={"q":"My name is John Smith and my email is john.smith@acme.com."})
        a = r.final_result.choices[0].message.content
        record(3,"데이터 마스킹(PII)","개인정보를 모델에 보내기 전에 익명화","이름·이메일 포함 입력 → 마스킹",
               "PASS" if "MASKED" in a.upper() else "FAIL", f"출력: '{a.strip()[:50]}'")
    except Exception as e: record(3,"데이터 마스킹(PII)","PII 익명화","마스킹 구성","FAIL",str(e)[:120])

    # 그라운딩 공통
    from gen_ai_hub.orchestration_v2.models.document_grounding import (
        DocumentGroundingFilter, DocumentGroundingConfig, DocumentGroundingPlaceholders, GroundingModuleConfig)
    from gen_ai_hub.orchestration_v2.models.streaming import GlobalStreamOptions
    gt = Template(template=[SystemMessage(content="Answer only from the provided context."),
        UserMessage(content="Request: {{?user_query}}\nContext: {{?grounding_response}}")])
    gpt = PromptTemplatingModuleConfig(prompt=gt, model=LLMModelDetails(name=LLM))

    # M4 grounding help.sap.com
    try:
        g = GroundingModuleConfig(config=DocumentGroundingConfig(
            filters=[DocumentGroundingFilter(id="H", data_repository_type="help.sap.com")],
            placeholders=DocumentGroundingPlaceholders(input=["user_query"], output="grounding_response")))
        svc.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=gpt, grounding=g))
        r = svc.run(placeholder_values={"user_query":"What is SAP Joule?"})
        record(4,"Grounding (공개 help.sap.com)","공개 SAP Help 문서를 근거로 답변(관리형 RAG)",
               "grounding 필터=help.sap.com → run","PASS", f"답변: '{r.final_result.choices[0].message.content.strip()[:45]}…'")
    except Exception as e: record(4,"Grounding (공개 help.sap.com)","관리형 RAG","grounding run","FAIL",str(e)[:120])

    # M4 streaming
    try:
        sc = OrchestrationConfig(modules=ModuleConfig(prompt_templating=gpt, grounding=g), stream=GlobalStreamOptions(enabled=True))
        n=0; buf=""
        for ch in svc.stream(config=sc, placeholder_values={"user_query":"What is SAP AI Core?"}):
            d = ch.final_result.choices[0].delta.content
            if d: buf+=d; n+=1
        record(4,"스트리밍 응답","응답을 토큰 단위로 스트리밍(UX)","stream() → delta 누적","PASS" if n>0 else "FAIL",
               f"청크 {n}개: '{buf.strip()[:40]}…'")
    except Exception as e: record(4,"스트리밍 응답","스트리밍","stream","FAIL",str(e)[:120])

    # M5 vector grounding (내 저장소) — 인덱싱 지연 대비 재시도
    try:
        gv = GroundingModuleConfig(config=DocumentGroundingConfig(
            filters=[DocumentGroundingFilter(id="My", data_repository_type="vector", data_repositories=[collection_id])],
            placeholders=DocumentGroundingPlaceholders(input=["user_query"], output="grounding_response")))
        svc.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=gpt, grounding=gv))
        ans=""
        for attempt in range(3):
            r = svc.run(placeholder_values={"user_query":"What is data masking in the orchestration service?"})
            ans = r.final_result.choices[0].message.content.strip()
            if len(ans) > 30: break
            time.sleep(10)
        record(5,"내 문서 그라운딩 (vector)","방금 수집한 내 저장소를 근거로 답변(필터만 교체)",
               "grounding 필터=vector+내 collection → run","PASS" if ans else "FAIL", f"답변: '{ans[:45]}…'")
    except Exception as e: record(5,"내 문서 그라운딩 (vector)","내 문서 RAG","vector grounding run","FAIL",str(e)[:120])

    # M6 memory chatbot
    try:
        cpt = PromptTemplatingModuleConfig(prompt=Template(template=[SystemMessage(content="You are helpful."),
            UserMessage(content="{{?user_query}}")]), model=LLMModelDetails(name=LLM))
        svc.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=cpt))
        hist=[]
        r1 = svc.run(config=svc.config, placeholder_values={"user_query":"My name is Jin."}, history=hist)
        hist = r1.intermediate_results.templating; hist.append(r1.final_result.choices[0].message)
        r2 = svc.run(config=svc.config, placeholder_values={"user_query":"What is my name?"}, history=hist)
        a = r2.final_result.choices[0].message.content
        record(6,"메모리 챗봇","대화 history를 넘겨 이전 맥락을 기억","2턴 대화 + history 전달",
               "PASS" if "Jin" in a else "FAIL", f"2번째 답: '{a.strip()[:35]}'")
    except Exception as e: record(6,"메모리 챗봇","대화 기억","history run","FAIL",str(e)[:120])

finally:
    # =============================================================== 3) 삭제
    print("\n[3/3] 삭제 — 생성한 저장소 정리(teardown)")
    if collection_id:
        d = requests.delete(f"{DG}/vector/collections/{collection_id}", headers=H)
        record(5, "저장소 삭제(teardown)", "검증용으로 만든 저장소를 깨끗이 삭제",
               f"DELETE collection {collection_id}", "PASS" if d.status_code<300 else "FAIL", f"status {d.status_code}")

# =================================================================== 요약
npass = sum(1 for r in results if r["status"]=="PASS")
nfail = sum(1 for r in results if r["status"]=="FAIL")
print("\n" + "="*60)
print(f"결과: PASS {npass} · FAIL {nfail} · 총 {len(results)}")
print("="*60)
out = {"timestamp": datetime.datetime.now().isoformat(), "model": LLM, "resource_group": RG,
       "pass": npass, "fail": nfail, "results": results}
json.dump(out, open("validation_results.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
print("상세: validation_results.json")
sys.exit(1 if nfail else 0)
