# 모듈 1 · LLM 프롬프트 기초

🎯 **목표**: SDK로 LLM을 호출하고, role·환각·멀티모달을 이해한다.
⏱️ **시간**: 약 35분
📓 기반: `03-prompt-llm.ipynb`

---

## 배경 — LLM과 "프롬프트"

**LLM(대형 언어 모델)** 은 지금까지의 대화를 보고 **다음에 올 가장 그럴듯한 말**을 생성하는 모델입니다. 우리가 모델에 보내는 입력을 **프롬프트(prompt)** 라고 부릅니다.

프롬프트는 보통 **메시지 목록**으로 보냅니다. 각 메시지에는 **역할(role)** 이 붙습니다.

| role | 의미 | 예시 |
| --- | --- | --- |
| `system` | 모델의 **성격·규칙** 설정 | "너는 친절한 SAP 상담원이다" |
| `user` | 사람의 **질문/요청** | "AI Core가 뭐야?" |
| `assistant` | 모델의 **이전 답변** (대화를 이어갈 때) | (모듈 6 메모리에서 사용) |

이 모듈에서는 ① 기본 호출 → ② role로 어조 바꾸기 → ③ 환각 관찰 → ④ 이미지 입력(멀티모달) 순서로 체험합니다.

## 1. 기본 chat 호출

가장 단순한 형태입니다. `user` 메시지 하나만 보내고 답을 받습니다.

```python
from gen_ai_hub.proxy.native.openai import chat

MODEL_NAME = 'gpt-5.6-sol'   # 배포된 모델명으로 (강사 안내 값)

messages = [
    {"role": "user", "content": "What is the underlying model architecture of an LLM? Explain it as short as possible."}
]
response = chat.completions.create(model_name=MODEL_NAME, messages=messages)
print(response.choices[0].message.content)
```

**코드 뜯어보기**

- `from ... import chat` : Gen AI Hub가 제공하는 OpenAI 호환 `chat` 인터페이스를 가져옵니다. 모델이 Claude든 GPT든 **같은 방식**으로 부릅니다.
- `MODEL_NAME` : 어떤 배포(모델)를 쓸지 지정. **이 한 줄만 바꾸면 다른 모델로 전환**됩니다.
- `messages` : 위에서 설명한 메시지 목록.
- `response.choices[0].message.content` : 모델의 답변 텍스트. 응답은 여러 후보(`choices`)를 담을 수 있어 보통 **첫 번째**(`[0]`)를 봅니다.

## 2. role 이해 — system 프롬프트로 스타일 제어

이번엔 `system` 메시지를 추가합니다. **질문은 그대로**인데 어조가 어떻게 바뀌는지 보세요.

```python
messages = [
    {"role": "system", "content": "Speak like Yoda from Star Wars."},
    {"role": "user", "content": "What is the underlying model architecture of an LLM? Explain it as short as possible."},
]
response = chat.completions.create(model_name=MODEL_NAME, messages=messages)
print(response.choices[0].message.content)
```

- `system`: 모델의 **역할·규칙·어조**를 정의 (여기선 "요다처럼 말하라")
- `user`: 실제 질문 (내용은 1번과 동일)
- (`assistant`: 이전 모델 답변 — 모듈 6 메모리에서 활용)

> 💡 **포인트**: `system` 은 "모델에게 미리 주는 지시서"입니다. 어조뿐 아니라 "반드시 한국어로", "3문장 이내로", "표로 정리" 같은 **출력 형식**도 여기서 통제합니다.

## 3. 환각(Hallucination) 관찰

이제 **일부러** 모델이 잘 모를 만한 SAP 내부 동작을 물어봅니다.

```python
messages = [
    {"role": "system", "content": "You are an SAP Consultant."},
    {"role": "user", "content": "How does the data masking of the orchestration service work?"},
]
response = chat.completions.create(model_name=MODEL_NAME, messages=messages)
print(response.choices[0].message.content)
```

답변이 그럴듯하지만 세부가 틀릴 수 있습니다. **모델은 "모른다"고 하기보다 지어내는 경향**이 있는데, 이를 **환각(hallucination)** 이라고 합니다.

> 🔑 **이 순간을 기억하세요.** 지금 받은 "그럴듯하지만 미심쩍은" 답을, **모듈 4(그라운딩)** 에서 **똑같은 질문**으로 다시 던져 비교합니다. 그라운딩이 환각을 어떻게 줄이는지 직접 확인하게 됩니다. 가능하면 지금 답변을 메모해두세요.

## 4. 멀티모달 — 이미지 입력

**멀티모달**이란 텍스트뿐 아니라 **이미지도 함께** 입력하는 것입니다. 모델에게 그림을 "보여주고" 설명을 받습니다.

```python
import base64

# 이미지는 그대로 못 보내므로 base64 문자열로 인코딩해서 보냄
with open("documents/ai-foundation-architecture.png", "rb") as f:
    image_data = base64.b64encode(f.read()).decode("utf-8")

messages = [{"role": "user", "content": [
    {"type": "text", "text": "Describe the image as an alternative text."},
    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
]}]
response = chat.completions.create(model_name=MODEL_NAME, messages=messages)
print(response.choices[0].message.content)
```

**코드 뜯어보기**

- `base64.b64encode(...)` : 이미지 파일을 **텍스트(문자열)로 변환**합니다. API는 바이너리 대신 이 문자열을 받습니다.
- `content` 가 리스트로 바뀌었습니다 → **텍스트 + 이미지**를 한 메시지에 함께 담은 형태입니다.
- `"type": "image_url"` + `data:image/png;base64,...` : "이건 PNG 이미지이고 내용은 이 문자열이다"라고 알려주는 형식입니다.

이미지에서 **텍스트/표를 구조화해서 뽑을** 수도 있습니다. 예를 들어 `documents/bananabread.png`(요리 레시피 이미지)로 재료·조리법을 JSON으로 추출해보세요 — 영수증·송장·명함 처리 같은 실무로 바로 이어집니다.

## 직접 바꿔보기 (실험)

- **system 프롬프트**: "초등학생에게 설명하듯", "반드시 3문장으로" 등으로 톤·길이 제어
- **모델 교체**: `MODEL_NAME` 을 `gpt-5.6-sol`, `anthropic--claude-4.6-sonnet`, `gpt-5` 로 바꿔 응답·속도·어조 비교
- **temperature**: `create(..., temperature=0.2)` 과 `1.5` 를 각각 여러 번 실행해 일관성 차이 (⚠️ GPT-5 계열(`gpt-5.6-sol` 등)은 `temperature=0` 을 거부하니 0.2 이상 사용)
- **환각 교정 시도**: system에 "모르면 모른다고 답하라"를 추가 → 어떻게 바뀌는지
- **멀티모달 응용**: `bananabread.png` 로 재료·조리법을 2개 JSON으로 추출

## ✅ 체크포인트

- [ ] chat 호출로 답변을 받았다
- [ ] system 프롬프트로 어조가 바뀌는 걸 확인했다
- [ ] 환각 사례를 하나 관찰했다
- [ ] 모델명 한 줄 교체로 다른 모델이 응답하는 걸 확인했다
