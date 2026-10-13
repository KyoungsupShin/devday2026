# 모듈 4 · Document Grounding + Streaming

🎯 **목표**: Orchestration에 그라운딩 모듈을 붙여 근거 기반 답변을 만들고, 스트리밍으로 받는다.
⏱️ **시간**: 약 40분
📓 기반: `09-orchestration-service-grounding.ipynb`

---

## 배경 — 그라운딩 = 관리형 RAG

모듈 1에서 모델이 **환각**(그럴듯한 거짓)을 내는 걸 봤습니다. 이를 줄이는 가장 효과적인 방법이 **RAG**입니다.

> **RAG**: 모델에게 바로 묻지 않고, ① 질문과 관련된 **문서를 먼저 검색**해서 ② 그 내용을 프롬프트에 **같이 넣어** 묻는 것. 모델은 "주어진 근거 안에서" 답하므로 환각이 줄고 출처가 생깁니다.

**Document Grounding**은 이 RAG를 SAP가 **관리형**으로 제공합니다. 직접 임베딩·벡터DB·검색을 구현하지 않아도, **저장소만 지정**하면 검색·주입을 대신 해줍니다. 이 모듈에서는 공개 저장소 `help.sap.com` 을 씁니다.

**동작 흐름**

```
질문(user_query)
   → [그라운딩] help.sap.com 에서 관련 청크 검색
   → 검색 결과를 grounding_response 에 담음
   → [템플릿] "Context:" 자리에 그 결과를 끼워넣음
   → [LLM] 질문 + Context 를 함께 보고 답변
```

즉 `input` 플레이스홀더(질문)로 검색하고, 결과를 `output` 플레이스홀더(`grounding_response`)로 돌려받아 템플릿의 `Context:` 자리에 자동으로 채웁니다.

## 1. 모델 + 템플릿

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
    SystemMessage(content="You are a helpful assistant."),
    UserMessage(content="""Answer the request by providing relevant answers that fit to the request.
        Request: {{?user_query}}
        Context: {{?grounding_response}}
        """),
])
```

**템플릿의 두 플레이스홀더에 주목하세요.**

- `{{?user_query}}` : 내가 넣을 **질문**.
- `{{?grounding_response}}` : 내가 채우지 않습니다! **그라운딩 모듈이 검색 결과로 자동으로 채워주는** 자리입니다.

> 💡 그래서 `service.run()` 에서 `grounding_response` 는 안 넘기고 `user_query` 만 넘깁니다. 나머지는 그라운딩이 알아서 합니다.

## 2. 그라운딩 config

```python
filters = [DocumentGroundingFilter(id="SAPHelp", data_repository_type="help.sap.com")]

grounding_config = GroundingModuleConfig(config=DocumentGroundingConfig(
    filters=filters,
    placeholders=DocumentGroundingPlaceholders(input=["user_query"], output="grounding_response"),
))

prompt_template = PromptTemplatingModuleConfig(prompt=template, model=llm)
config = OrchestrationConfig(modules=ModuleConfig(
    prompt_templating=prompt_template, grounding=grounding_config))

service = OrchestrationService(api_url=variables.AICORE_ORCHESTRATION_DEPLOYMENT_URL, config=config)
resp = service.run(placeholder_values={"user_query": "What is Joule?"})
print(resp.final_result.choices[0].message.content)
```

**코드 뜯어보기**

- `DocumentGroundingFilter(id="SAPHelp", data_repository_type="help.sap.com")` : **어디서 검색할지** 지정. 여기선 공개 SAP Help.
- `DocumentGroundingPlaceholders(input=["user_query"], output="grounding_response")` : **무엇으로 검색하고**(input=질문), **어디에 결과를 담을지**(output=템플릿의 Context 자리) 연결.
- `grounding=grounding_config` : 그라운딩 모듈을 config에 꽂음 (모듈 3의 패턴 그대로).
- `run(placeholder_values={"user_query": "What is Joule?"})` : 질문만 넘기면 검색→주입→답변이 **한 번에** 일어납니다.

## 3. 스트리밍

**스트리밍**은 답을 **다 만든 뒤 한꺼번에** 받는 대신, 생성되는 **토큰을 실시간으로** 흘려받는 방식입니다. ChatGPT가 글자를 또르륵 찍어내는 그 느낌 — 체감 응답 속도가 빨라집니다.

```python
from gen_ai_hub.orchestration_v2.models.streaming import GlobalStreamOptions

stream_config = OrchestrationConfig(
    modules=ModuleConfig(prompt_templating=prompt_template, grounding=grounding_config),
    stream=GlobalStreamOptions(enabled=True))

for chunk in service.stream(config=stream_config,
                            placeholder_values={"user_query": "What is Joule?"}):
    delta = chunk.final_result.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
```

**코드 뜯어보기**

- `GlobalStreamOptions(enabled=True)` : 스트리밍 켜기.
- `service.stream(...)` : `run` 대신 **반복(for문)으로** 조각(`chunk`)을 받습니다.
- `delta.content` : 이번 조각에서 **새로 추가된 글자**. (`message.content` 전체가 아니라 **증분**)
- `print(delta, end="", flush=True)` : 줄바꿈 없이 이어 붙여 바로바로 화면에 출력.

> 🔑 **다음 모듈 예고**: 지금 코드는 거의 그대로 쓰고, 모듈 5에서는 **그라운딩 필터만** `help.sap.com` → 내 벡터 저장소로 바꿉니다. "소스만 교체"의 위력을 보게 됩니다.

## 직접 바꿔보기 (실험)

- **그라운딩 on/off 비교 (가장 중요)**: 모듈 1 방식(그라운딩 없이)과 이 방식(그라운딩)으로 **같은 질문**을 던져 답을 비교. 모듈 1에서 환각을 봤던 "How does the data masking of the orchestration service work?" 를 다시!
- 질문 바꾸기: "What is SAP AI Core?", "What models does orchestration support?" 등 SAP Help에 있을 법한 질문들
- `.run()` vs `.stream()` 체감 차이
- 낮은 temperature(생략=기본) vs 높은 값에서 근거 답변 안정성
- (심화) 템플릿에 "Context에 없으면 '문서에 없음'이라고 답하라" 추가

## ✅ 체크포인트

- [ ] 그라운딩으로 답변을 받았다
- [ ] 같은 질문의 그라운딩 on/off 답변 차이를 확인했다
- [ ] 스트리밍으로 토큰이 흘러나오는 걸 봤다
