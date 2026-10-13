# 모듈 3 · Orchestration + 콘텐츠 필터 + 데이터 마스킹 (강사용)

🎯 **목표**: Orchestration = 선언형 모듈 파이프라인임을 체득 + 엔터프라이즈 안전장치(필터 + PII 마스킹).
⏱️ **시간**: 50분 (설명 17분 + 실습·실험 33분) — 개념 밀도가 가장 높은 모듈
📓 기반: `08-orchestration-service.ipynb` + SAP BTP AI Best Practices(data-masking)

---

## 🧑‍🏫 강사 노트 — 개념 전환 지점

모듈 1~2는 "모델을 직접 부른다"였습니다. 여기서부터는 **"파이프라인을 선언한다"** 로 사고가 바뀝니다. 이 전환을 명시적으로 짚어주세요.

핵심 메시지 2개:
1. **모듈 조합**: `prompt_templating`, `filtering`, (뒤에서) `grounding`, `masking` 을 `ModuleConfig` 에 끼워 넣기만 하면 파이프라인이 된다.
2. **모델 독립성**: `LLMModelDetails(name=...)` 한 줄만 바꾸면 전체가 그대로 — 오늘의 핵심 가치를 가장 선명하게 보여주는 모듈.

⚠️ **네임스페이스 주의**: `gen_ai_hub.orchestration_v2` 입니다. 구버전 `orchestration` 과 클래스명이 다릅니다. Copilot/구글 검색은 구버전을 자주 내놓으니, 참가자가 import 에러를 만나면 여기를 의심하라고 미리 알려주세요.

## 1~2. 템플릿 + config + 실행

💬 **이렇게 말하세요**: "`{{?user_query}}` 처럼 생긴 게 플레이스홀더예요. 템플릿은 틀만 잡고, 실행할 때 `placeholder_values` 로 값을 꽂습니다. 프롬프트를 코드에 하드코딩하지 않고 **분리**하는 거죠 — 프롬프트를 바꿔도 코드는 그대로."

🧑‍🏫 `defaults={"to_lang": "English"}` 는 플레이스홀더 기본값. `to_lang` 을 안 넘기면 영어로 번역. 실행 시 `to_lang` 을 "Korean"으로 넘겨 바뀌는 걸 데모하면 좋음.

🎬 **라이브 데모**: 같은 config에서 `service.run(placeholder_values={"user_query": "...", "to_lang": "Korean"})` 로 번역 대상 언어를 바꿔 보여주기.

## 3~4. 콘텐츠 필터

🧑‍🏫 두 가지 필터 제공자:
- **Azure Content Safety**: hate/violence/self_harm/sexual 4개 카테고리, 각각 `AzureThreshold` 로 민감도 설정. `ALLOW_SAFE`(가장 엄격, safe만 허용) → `ALLOW_ALL`(사실상 off).
- **Llama Guard 3 8B**: LLM 기반 분류기, 카테고리 boolean.

💬 **이렇게 말하세요**: "임계값은 '어디까지 허용할지'예요. `ALLOW_SAFE` 는 safe 등급만 통과시키니 가장 빡빡하고, `ALLOW_ALL` 은 다 통과시켜 사실상 끈 상태입니다. 엔터프라이즈에선 입력(사용자가 뭘 넣든)과 출력(모델이 뭘 뱉든) 양쪽을 다 걸러야 하죠."

🎬 **라이브 데모 (반응 좋음)**: 독일어 욕설 프롬프트(`"Du bist ein ganz mieser Entwickler!"` = "너 아주 형편없는 개발자야")가 `OrchestrationError` 로 차단되고, 칭찬 프롬프트(`"super talentierter Entwickler"`)는 통과하는 걸 나란히 보여주세요. `try/except` 로 감싸 차단 메시지를 깔끔히 출력.

⚠️ 차단은 **예외로 떨어집니다**. `try/except OrchestrationError` 없이 돌리면 셀이 에러로 멈춥니다. 꼭 감싸게 하세요.

## 5. 출력 필터

🧑‍🏫 입력만 막으면 "사용자가 교묘히 우회해 모델이 유해 답변 생성"을 못 막습니다. 출력 필터가 모델 응답 자체를 검사. 데모용 프롬프트(폭력적 행위를 묻는)가 출력 단에서 걸리는 걸 보여주면 입력/출력 필터의 역할 차이가 명확.

## 5b. 데이터 마스킹 (PII 익명화)

🧑‍🏫 필터가 "유해성"을 본다면, 마스킹은 **개인정보**를 모델에 보내기 전에 가립니다. 같은 Orchestration에 `masking` 모듈을 추가 — "모듈을 끼운다"는 메시지를 한 번 더 강화하는 좋은 예.

💬 **이렇게 말하세요**: "민감정보를 LLM(특히 외부 모델)에 그대로 보내긴 꺼려지죠. Orchestration이 **보내기 전에** 이름·이메일·전화번호를 가려줍니다. 규제 산업에선 거의 필수예요."

```python
from gen_ai_hub.orchestration_v2.models.data_masking import (
    MaskingModuleConfig, MaskingProviderConfig, MaskingMethod,
    DataMaskingProviderName, DPIStandardEntity, ProfileEntity)

masking = MaskingModuleConfig(masking_providers=[MaskingProviderConfig(
    type_=DataMaskingProviderName.SAP_DATA_PRIVACY_INTEGRATION,
    method=MaskingMethod.ANONYMIZATION,        # 또는 PSEUDONYMIZATION
    entities=[DPIStandardEntity(type=ProfileEntity.EMAIL),
              DPIStandardEntity(type=ProfileEntity.PHONE),
              DPIStandardEntity(type=ProfileEntity.PERSON)],
)])
service.config = OrchestrationConfig(modules=ModuleConfig(
    prompt_templating=prompt_template, masking=masking))
```

🧑‍🏫 **ANONYMIZATION**(복원 불가) vs **PSEUDONYMIZATION**(가명, 매핑 복원 가능) 차이를 강조. SAP Data Privacy Integration(DPI)이 제공자(`DataMaskingProviderName.SAP_DATA_PRIVACY_INTEGRATION`).

🎬 **데모**: PII가 든 프롬프트("내 이름은 홍길동, 이메일 gildong@example.com")를 마스킹 on/off로 돌려 모델에 전달되는 내용이 어떻게 가려지는지 보여주세요. (근거: `sap-btp-ai-best-practices` 의 data-masking best practice)

## 직접 바꿔보기 (실험) — 33분 중 20분

- **차단 경계 찾기**를 꼭 시키세요: 같은 프롬프트로 임계값을 단계적으로 낮추며 어디서 통과로 바뀌는지. "안전은 이분법이 아니라 스펙트럼"을 체감.
- **모델 교체**(핵심 가치): 필터·템플릿 그대로 두고 모델만 Claude로.

## ❓ 예상 질문 & 답

- **"Azure랑 Llama Guard 둘 다 왜 켜요?"** → 상호 보완. 규칙 기반(Azure)과 LLM 기반(Llama Guard)이 잡는 패턴이 다름. 하나만 써도 되지만 함께 쓰면 커버리지↑.
- **"이 필터가 한국어도 되나요?"** → Azure는 다국어 지원. 단, 언어별 정확도 차이가 있으니 실제 데이터로 검증 권장.
- **"마스킹 복원이 되나요?"** → ANONYMIZATION은 복원 불가, PSEUDONYMIZATION은 가명↔원본 매핑으로 복원 가능. 용도에 따라 선택.
- **"필터와 마스킹 차이는?"** → 필터는 유해/정책 위반 콘텐츠를 **차단**, 마스킹은 PII를 **가려서 통과**. 목적이 다름 — 함께 씀.
- **"필터 비용은?"** → 추가 모듈 호출이라 지연·비용이 늘 수 있음. 실무에선 필요한 카테고리만.

## ⚠️ 흔한 실수

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| 셀이 에러로 멈춤 | `try/except` 누락 | 차단은 예외임을 설명 |
| ImportError | `orchestration` vs `orchestration_v2` | v2 네임스페이스 확인 |
| 필터가 안 먹음 | 임계값이 `ALLOW_ALL` | 더 엄격하게 |
| `api_url` 오류 | Orchestration 배포 URL | 모듈 0 재확인 |

## ⏭️ 전환 멘트

> "파이프라인에 모듈을 끼워 넣는 감을 잡았죠? 이제 가장 강력한 모듈을 추가합니다 — **Grounding**. 모델이 모르는 걸 지어내던 모듈 1의 그 문제, 기억하시죠? 문서에서 근거를 찾아 자동으로 넣어주는 모듈을 붙여보겠습니다. (여기서 휴식 후) 아까 그 질문을 다시 던질 거예요."
