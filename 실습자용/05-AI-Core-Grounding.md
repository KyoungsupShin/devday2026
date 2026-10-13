# 모듈 5 · 내 문서 그라운딩 (AI Core Grounding)

🎯 **목표**: 내 문서를 **AI Core의 관리형 Grounding(벡터 저장소)** 에 올려두고, 모듈 4 코드에서 **필터만 바꿔** SDK로 질의한다.
⏱️ **시간**: 약 35분
📓 기반: 노트북 07(Grounding Management) + 09(SDK 소비)

---

## 배경 — 소스만 바꾸면 "내 문서 챗봇"

모듈 4는 공개 저장소 `help.sap.com` 에 그라운딩했습니다. 하지만 실무에서 진짜 필요한 건 **우리 회사 문서**(매뉴얼·규정·제품 스펙)에 기반한 답변이죠. 이 모듈은 **같은 메커니즘을 내 문서에** 적용합니다.

좋은 소식: 벡터 데이터베이스(HANA 등)를 직접 구축할 필요가 없습니다. **AI Core가 관리하는 벡터 저장소**에 문서를 한 번 넣어두면, 청킹(문서 쪼개기)·임베딩·검색을 **AI Core가 알아서** 해줍니다.

```
① 수집 (강사가 사전 수행)
   내 문서(PDF 등) → AI Core Grounding 벡터 저장소에 적재
                     (문서 쪼개기 + 임베딩은 AI Core가 수행)

② 질의 (여러분이 실습)
   모듈 4 코드에서 grounding 필터만 '내 저장소'로 지정 → SDK로 호출
```

> 핵심은 **"코드는 모듈 4와 거의 같고, 그라운딩 필터만 바뀐다"** 입니다. `data_repository_type` 을 `help.sap.com` → `vector` 로, 그리고 **내 저장소 id**를 지정하는 것뿐입니다.

> 이 과정의 문서 묶음(corpus)은 `documents/` 폴더의 **SDK 레퍼런스 PDF들**입니다. 모듈 4(공개)와 **같은 질문**을 던져 "내 문서 기반 답변"이 어떻게 다른지 비교해보세요.

## Part A. 저장소 준비 (대부분 강사가 사전 완료)

**단일 공유 AI Core** 환경에서는 강사가 **공유 벡터 저장소 1개**를 미리 만들고 문서를 수집해 둔 뒤, **저장소 id**를 공유합니다. 참가자는 그 id만 받으면 됩니다.

> 수집(ingestion)은 **Grounding Vector API**(REST)로 합니다. 강사는 저장소 폴더의 `ingest_documents.py`(저장소 생성 → PDF 청킹 → 수집 → 검색 확인)를 한 번 실행해 두고, 출력된 collection id 를 공유합니다. 그래서 참가자 실습은 **질의(SDK)** 에 집중합니다.

받을 값: **`GROUNDING_REPOSITORY_ID`** (= 수집으로 만든 collection id, 강사 공유)

## Part B. 내 저장소에 SDK로 질의

모듈 4 코드를 거의 그대로 쓰고, **필터만** 내 저장소로 바꿉니다.

```python
import init_env, variables
init_env.set_environment_variables()

from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
from gen_ai_hub.orchestration_v2.models.document_grounding import (
    DocumentGroundingFilter, DocumentGroundingConfig,
    DocumentGroundingPlaceholders, GroundingModuleConfig)
from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
from gen_ai_hub.orchestration_v2.models.message import SystemMessage, UserMessage
from gen_ai_hub.orchestration_v2.service import OrchestrationService

llm = LLMModelDetails(name="gpt-5.6-sol")

template = Template(template=[
    SystemMessage(content="You are a helpful assistant. Answer only from the provided context."),
    UserMessage(content="""Request: {{?user_query}}
        Context: {{?grounding_response}}
        """),
])

# ★ 핵심: help.sap.com 대신 내 벡터 저장소를 지정
GROUNDING_REPOSITORY_ID = "<강사가 공유한 저장소 id>"

filters = [DocumentGroundingFilter(
    id="MyDocs",
    data_repository_type="vector",              # ← 모듈 4는 "help.sap.com", 여기선 "vector"(내 저장소)
    data_repositories=[GROUNDING_REPOSITORY_ID] # ← 검색할 내 저장소 id (강사 공유)
)]
# ↑ 모듈 4와 비교해 '이 세 줄'만 달라졌습니다. 나머지는 사실상 동일!

grounding_config = GroundingModuleConfig(config=DocumentGroundingConfig(
    filters=filters,
    placeholders=DocumentGroundingPlaceholders(input=["user_query"], output="grounding_response"),
))

prompt_template = PromptTemplatingModuleConfig(prompt=template, model=llm)
config = OrchestrationConfig(modules=ModuleConfig(
    prompt_templating=prompt_template, grounding=grounding_config))

service = OrchestrationService(api_url=variables.AICORE_ORCHESTRATION_DEPLOYMENT_URL, config=config)
resp = service.run(placeholder_values={"user_query": "What is data masking in the orchestration service?"})
print(resp.final_result.choices[0].message.content)
```

> `data_repositories` 를 비우면 해당 타입의 모든 저장소를 검색합니다. 특정 저장소만 보려면 id를 지정하세요.

## 검색된 청크 보기 (UI 없이 — 코드로)

LLM이 **답하기 전에** 그라운딩이 실제로 어떤 청크를 찾았는지 직접 볼 수 있습니다 (Launchpad의 Run Search를 코드로):

```bash
python inspect_aicore.py search <내 저장소 id> "What is data masking in the orchestration service?"
```
```
[검색] 'What is data masking...' → collection=...
  [1] score=0.630  Orchestration data masking anonymizes PII like names, emails ...
```

→ 점수(score)와 함께 검색된 청크가 보입니다. "왜 이렇게 답했는지"를 근거 단계에서 확인하는 용도. 저장소 문서 목록은 `python inspect_aicore.py documents <id>` 로 확인합니다.

## 직접 바꿔보기 (실험)

- **검색된 청크 보기**: 질문을 바꿔가며 `inspect_aicore.py search` 로 어떤 청크가 검색되는지(score 변화) 관찰
- **공개 vs 내 문서 비교**: 같은 질문을 모듈 4(`help.sap.com`)와 이 모듈(`vector` + 내 저장소)로 던져 답·출처 비교
- **질문 바꾸기**: `documents/` PDF(Orchestration·Grounding SDK 문서)에 있을 법한 질문들
- 템플릿에 "context에 없으면 '문서에 없음'이라고 답하라" 추가 → 환각 억제
- (심화) `GroundingSearchConfig` 의 `max_document_count` 로 검색 청크 수 조절

## ✅ 체크포인트

- [ ] 내 저장소 id로 그라운딩 질의가 동작한다
- [ ] 같은 질문의 공개(help.sap.com) vs 내 문서 답변 차이를 확인했다
- [ ] 필터만 바꿔 소스를 전환할 수 있음을 이해했다
