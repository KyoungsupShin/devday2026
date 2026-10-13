# 모듈 3 · Orchestration + 콘텐츠 필터 + 데이터 마스킹

🎯 **목표**: 여러 모듈을 하나의 config로 엮는 Orchestration을 구성하고, 입력·출력 콘텐츠 필터와 PII 데이터 마스킹을 적용한다.
⏱️ **시간**: 약 50분
📓 기반: `08-orchestration-service.ipynb` + SAP BTP AI Best Practices(data-masking)

---

## 배경 — Orchestration은 "조립 설정"이다

지금까지(모듈 1)는 모델을 **직접** 불렀습니다. 하지만 실무에서는 모델 호출 전후로 할 일이 많습니다 — 프롬프트 템플릿 채우기, 개인정보 가리기, 문서 검색해서 끼워넣기, 유해 내용 거르기.

**Orchestration**은 이 단계들을 **하나의 설정(config)** 으로 선언하고, 그 설정대로 **파이프라인**을 돌립니다.

```
입력 → [템플릿] → [마스킹] → [그라운딩] → [LLM] → [출력 필터] → 결과
         (3번)     (6번)      (모듈4)      택1       (5번)
```

- **각 단계는 선택적**입니다. 이 모듈에선 템플릿 → 필터 → 마스킹을 하나씩 켜봅니다.
- 가장 큰 장점: 파이프라인은 그대로 두고 **`LLMModelDetails(name=...)` 한 줄만 바꿔** 모델을 교체할 수 있습니다.

> 🧩 **용어**: 각 단계를 **모듈(module)** 이라 부르고, 그 모듈들을 묶은 게 `OrchestrationConfig` 입니다. "모듈을 config에 꽂는다"는 표현이 반복됩니다.

> ⚠️ SDK 네임스페이스가 `orchestration_v2` 입니다. `orchestration`(v1 없는 버전)으로 쓰면 import 에러가 납니다 — Copilot이 자주 틀리는 지점이니 주의하세요.

## 1. import & 모델·템플릿

```python
import init_env, variables
init_env.set_environment_variables()

from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
from gen_ai_hub.orchestration_v2.models.message import SystemMessage, UserMessage
from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
from gen_ai_hub.orchestration_v2.service import OrchestrationService
from gen_ai_hub.orchestration_v2.exceptions import OrchestrationError

llm = LLMModelDetails(name="gpt-5.6-sol", params={"max_tokens": 5000, "temperature": 1})

template = Template(
    template=[
        SystemMessage(content="You are a helpful translation assistant."),
        UserMessage(content="Translate the following text to {{?to_lang}}: {{?user_query}}"),
    ],
    defaults={"to_lang": "English"},
)
```

**코드 뜯어보기**

- `LLMModelDetails(name=..., params=...)` : 어떤 모델을, 어떤 옵션(`max_tokens`, `temperature`)으로 쓸지 정의합니다.
- `Template(template=[SystemMessage, UserMessage])` : 모듈 1의 메시지 목록과 같은 개념인데, **재사용 가능한 틀**로 만들었습니다.
- `{{?user_query}}`, `{{?to_lang}}` : **플레이스홀더**(빈칸)입니다. 실행할 때 실제 값으로 채웁니다.
- `defaults={"to_lang": "English"}` : 값을 안 주면 기본으로 "English"를 씀 → 매번 안 넘겨도 됩니다.

> 💡 **왜 템플릿을 쓰나?** 프롬프트를 코드 곳곳에 흩어 쓰지 않고 한 곳에 모아, **값만 바꿔 재사용**하기 위해서입니다. 번역 대상 언어나 질문만 바꾸면 같은 틀이 돕니다.

## 2. config 조립 & 실행

```python
prompt_template = PromptTemplatingModuleConfig(prompt=template, model=llm)
config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=prompt_template))

service = OrchestrationService(
    api_url=variables.AICORE_ORCHESTRATION_DEPLOYMENT_URL,
    config=config,
)
result = service.run(placeholder_values={"user_query": "Geht das wirklich mit allen Modellen?"})
print(result.final_result.choices[0].message.content)
```

**코드 뜯어보기**

- `PromptTemplatingModuleConfig(prompt=..., model=...)` : 템플릿 + 모델을 묶어 **"프롬프트 모듈"** 로 만듭니다.
- `OrchestrationConfig(modules=ModuleConfig(prompt_templating=...))` : 모듈들을 담는 전체 설정. 지금은 프롬프트 모듈 하나뿐입니다.
- `service.run(placeholder_values={...})` : 플레이스홀더를 실제 값으로 채워 실행. 여기선 독일어 문장을 넘겨 영어로 번역시킵니다.
- `result.final_result.choices[0].message.content` : 모듈 1과 비슷하지만, Orchestration은 **중간 단계 결과**도 담기에 최종 답은 `final_result` 아래에 있습니다.

> 🔁 **앞으로의 패턴**: "① 모듈 하나를 더 만든다 → ② `ModuleConfig` 에 꽂는다 → ③ `service.config` 를 교체한다 → ④ 다시 `run`." 아래 3~6번이 전부 이 패턴입니다.

## 3. 입력 콘텐츠 필터 추가

**콘텐츠 필터**는 혐오·폭력·자해·성적 표현 같은 **유해 콘텐츠**를 걸러냅니다. **입력 필터**는 사용자가 보낸 프롬프트를, **출력 필터**는 모델이 생성한 답변을 검사합니다. 아래에서는 입력 필터부터 켭니다. 두 종류의 필터 제공자를 함께 씁니다 — Azure Content Safety와 Llama Guard.

```python
from gen_ai_hub.orchestration_v2.models.content_filtering import (
    FilteringModuleConfig, InputFiltering, OutputFiltering)
from gen_ai_hub.orchestration_v2.models.content_filter import ContentFilter, ContentFilterProvider
from gen_ai_hub.orchestration_v2.models.azure_content_filter import AzureContentFilter, AzureThreshold
from gen_ai_hub.orchestration_v2.models.llama_guard_3_filter import LlamaGuard38bFilter

input_filter = ContentFilter(type=ContentFilterProvider.AZURE,
    config=AzureContentFilter(hate=AzureThreshold.ALLOW_SAFE, violence=AzureThreshold.ALLOW_SAFE,
                              self_harm=AzureThreshold.ALLOW_SAFE, sexual=AzureThreshold.ALLOW_SAFE))
input_filter_llama = ContentFilter(type=ContentFilterProvider.LLAMA_GUARD_3_8B,
    config=LlamaGuard38bFilter(hate=True))

config_with_filter = OrchestrationConfig(modules=ModuleConfig(
    prompt_templating=prompt_template,
    filtering=FilteringModuleConfig(input=InputFiltering(filters=[input_filter, input_filter_llama])),
))
service.config = config_with_filter
```

**코드 뜯어보기**

- `AzureThreshold.ALLOW_SAFE` : "안전한 것만 통과" = **가장 엄격**. 뒤에서 `ALLOW_SAFE_LOW` → `ALLOW_SAFE_LOW_MEDIUM` → `ALLOW_ALL` 로 갈수록 **느슨**해집니다.
- `hate / violence / self_harm / sexual` : 네 가지 유해 카테고리를 각각 따로 조절할 수 있습니다.
- 필터를 **리스트**로 여러 개 넣으면 **하나라도 걸리면 차단**됩니다 (Azure + Llama Guard 동시 적용).
- `service.config = config_with_filter` : 서비스에 **새 설정을 꽂아** 교체 (위에서 말한 패턴 ③).

## 4. 필터 테스트

```python
try:
    result = service.run(placeholder_values={"user_query": "Du bist ein ganz mieser Entwickler!"})
    print(result.final_result.choices[0].message.content)
except OrchestrationError as e:
    print("차단됨:", e.message)

# 정상 프롬프트는 통과
result = service.run(placeholder_values={"user_query": "Du bist ein super talentierter Entwickler!"})
print(result.final_result.choices[0].message.content)
```

**무슨 일이 일어나나요?**

- 첫 번째 문장("너는 아주 형편없는 개발자야!")은 공격적 → 입력 필터가 **차단** → `OrchestrationError` 발생 → `except` 로 잡아 "차단됨" 출력.
- 두 번째 문장("너는 정말 재능 있는 개발자야!")은 안전 → **통과** → 정상 번역 결과 출력.

> 💡 `try/except` 로 감싸는 이유: 차단되면 **예외(에러)** 로 알려주기 때문입니다. 감싸지 않으면 노트북 셀이 빨간 에러로 멈춥니다.

## 5. 출력 필터도 추가

```python
output_filter = ContentFilter(type=ContentFilterProvider.AZURE,
    config=AzureContentFilter(hate=AzureThreshold.ALLOW_SAFE, violence=AzureThreshold.ALLOW_SAFE_LOW,
                              self_harm=AzureThreshold.ALLOW_SAFE_LOW_MEDIUM, sexual=AzureThreshold.ALLOW_ALL))

config_with_io = OrchestrationConfig(modules=ModuleConfig(
    prompt_templating=prompt_template,
    filtering=FilteringModuleConfig(
        input=InputFiltering(filters=[input_filter, input_filter_llama]),
        output=OutputFiltering(filters=[output_filter]),
    ),
))
service.config = config_with_io
```

## 6. 데이터 마스킹 (PII 익명화)

필터가 "유해 콘텐츠"를 막는다면, 마스킹은 **개인정보(PII)를 모델에 보내기 전에 가립니다**. 같은 Orchestration config에 `masking` 모듈을 추가합니다.

```python
from gen_ai_hub.orchestration_v2.models.data_masking import (
    MaskingModuleConfig, MaskingProviderConfig, MaskingMethod,
    DataMaskingProviderName, DPIStandardEntity, ProfileEntity)

masking = MaskingModuleConfig(masking_providers=[MaskingProviderConfig(
    type_=DataMaskingProviderName.SAP_DATA_PRIVACY_INTEGRATION,
    method=MaskingMethod.ANONYMIZATION,        # 또는 PSEUDONYMIZATION
    entities=[
        DPIStandardEntity(type=ProfileEntity.EMAIL),
        DPIStandardEntity(type=ProfileEntity.PHONE),
        DPIStandardEntity(type=ProfileEntity.PERSON),
    ],
)])

config_with_masking = OrchestrationConfig(modules=ModuleConfig(
    prompt_templating=prompt_template,
    masking=masking,
))
service.config = config_with_masking

result = service.run(placeholder_values={
    "user_query": "내 이름은 홍길동이고 이메일은 gildong@example.com 입니다. 요약해줘."
})
print(result.final_result.choices[0].message.content)
```

- **ANONYMIZATION**: PII를 `MASKED_PERSON` 등으로 **익명화** (복원 불가)
- **PSEUDONYMIZATION**: 가명으로 치환 (매핑으로 복원 가능)
- `ProfileEntity`: EMAIL, PHONE, PERSON, ORG, LOCATION, ADDRESS, CREDIT_CARD_NUMBER, IBAN, SSN 등

> 마스킹·필터·그라운딩을 한 `ModuleConfig` 에 모두 넣으면 "규정 준수형" 파이프라인이 됩니다.

## 직접 바꿔보기 (실험)

- 마스킹 **ANONYMIZATION ↔ PSEUDONYMIZATION** 전환 후 출력 차이 비교
- `entities` 에 `ProfileEntity.ORG`, `ADDRESS`, `CREDIT_CARD_NUMBER` 등을 추가
- `AzureThreshold` 를 `ALLOW_SAFE` → `ALLOW_SAFE_LOW` → `ALLOW_SAFE_LOW_MEDIUM` → `ALLOW_ALL` 로 낮추며 차단 경계 찾기
- hate/violence/self_harm/sexual 카테고리를 각각 조절
- Azure만 / Llama Guard만 / 둘 다 켰을 때 판정 차이
- 출력 필터 없음 vs 있음: 모델이 유해 답변을 생성하려는 프롬프트로 차이 확인
- `LLMModelDetails(name=...)` 만 `anthropic--claude-4.6-sonnet` 등으로 바꿔 동일 config 재사용

## ✅ 체크포인트

- [ ] 번역 파이프라인이 동작한다
- [ ] 입력 필터가 공격적 프롬프트를 차단한다 (`OrchestrationError`)
- [ ] 임계값을 바꿔 차단 경계가 달라지는 걸 확인했다
- [ ] 데이터 마스킹으로 PII가 가려지는 걸 확인했다
- [ ] 모델명만 바꿔도 같은 config가 동작한다
