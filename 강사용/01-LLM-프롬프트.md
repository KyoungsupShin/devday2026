# 모듈 1 · LLM 프롬프트 기초 (강사용)

🎯 **목표**: SDK 호출 감각 + role/환각/멀티모달. 이후 모든 모듈의 토대.
⏱️ **시간**: 35분 (설명 12분 + 실습·실험 23분)
📓 기반: `03-prompt-llm.ipynb`

---

## 🧑‍🏫 강사 노트 — 이 모듈이 왜 먼저인가

본격적인 Orchestration/Grounding에 들어가기 전에, **SDK로 모델을 부르는 가장 단순한 형태**를 손에 익히는 단계입니다. 동시에 이 모듈은 **뒤 모듈의 동기(motivation)를 심는** 역할을 합니다.

- role → 모듈 3의 프롬프트 템플릿으로 이어짐
- 환각 → 모듈 4의 그라운딩이 푸는 문제
- (암묵적으로) "모델은 그냥 다음 토큰을 예측할 뿐"이라는 점을 환각으로 체감시킴

## 1. 기본 chat 호출

```python
from gen_ai_hub.proxy.native.openai import chat
MODEL_NAME = 'gpt-5.6-sol'
response = chat.completions.create(model_name=MODEL_NAME,
    messages=[{"role": "user", "content": "What is the underlying model architecture of an LLM? Explain it as short as possible."}])
print(response.choices[0].message.content)
```

💬 **이렇게 말하세요**: "`gen_ai_hub.proxy.native.openai` 는 OpenAI와 똑같은 인터페이스예요. 그런데 뒤에서는 SAP AI Core를 거쳐 호출됩니다. 그래서 모델명만 바꾸면 OpenAI가 아닌 Claude·Gemini도 같은 코드로 부를 수 있죠. 이게 오늘의 첫 번째 핵심입니다."

## 2. role 이해

🧑‍🏫 세 가지 role을 명확히: `system`(규칙/페르소나), `user`(질문), `assistant`(모델의 이전 답변). "Yoda처럼 말하라"는 장난 같지만, **system이 출력 전체를 지배한다**는 걸 직관적으로 보여주는 좋은 장치입니다.

🎬 **라이브 데모**: system을 "You are a terse senior architect. Max 2 sentences." 로 바꿔 같은 질문을 다시 던지고, 답이 확 짧아지는 걸 보여주세요.

## 3. 환각 — 이 핸즈온의 서사적 핵심

```python
messages = [
    {"role": "system", "content": "You are an SAP Consultant."},
    {"role": "user", "content": "How does the data masking of the orchestration service work?"},
]
```

🧑‍🏫 이 질문을 고른 이유: data masking은 **실제로 Orchestration에 있는 기능**이지만, 모델이 학습 시점에 정확히 몰랐다면 **그럴듯하게 지어냅니다**. 참가자에게 답을 소리내어 읽게 한 뒤 "이게 진짜일까요?"라고 물으세요.

💬 **이렇게 말하세요**: "답이 자신감 넘치죠? 근데 이게 맞는지 우리는 모릅니다. 모델은 '모른다'고 말하는 걸 잘 못해요 — 가장 그럴듯한 다음 단어를 이어붙일 뿐이니까요. **이 질문을 꼭 기억해두세요. 3시간쯤 뒤, 모듈 4에서 똑같은 질문을 그라운딩으로 다시 던질 겁니다.**"

⭐ **수미상관 장치**: 참가자에게 이 답변을 메모해두라고 하세요. 모듈 4에서 before/after를 비교합니다.

## 4. 멀티모달

🧑‍🏫 이미지를 base64로 인코딩해 `content` 리스트에 넣습니다. 멀티모달 모델(`gpt-5.6-sol` 등)이어야 동작. 실무 포인트: 스캔 문서·스크린샷·다이어그램에서 구조화 데이터 추출.

🎬 `bananabread.png` 로 "재료와 조리법을 각각 JSON으로" 요청하면, 이미지 → 구조화 JSON 변환이 한 방에 되는 걸 보여줄 수 있어 반응이 좋습니다.

## 직접 바꿔보기 (실험) — 23분 중 15분

실습자용의 실험 목록을 돌리게 하되, 강사는 다음을 유도하세요.

- **모델 교체 비교**를 반드시 시킵니다 (오늘의 핵심 가치 1). 같은 질문을 `gpt-5.6-sol` vs `claude-4.6-sonnet` 로 돌려 어조 차이를 느끼게.
- temperature 0.2 vs 1.5를 **각 3회** 실행시켜, 0.2는 거의 같은 답, 1.5는 매번 다른 답이 나오는 걸 보게. (⚠️ `gpt-5.6-sol` 등 GPT-5 계열은 `temperature=0` 을 거부 — 0.2 이상으로. 0을 쓰려면 `gpt-4.1` 같은 모델로 바꿔 보여주면 됨)

## ❓ 예상 질문 & 답

- **"temperature가 뭐예요?"** → 다음 토큰 선택의 무작위성. 0이면 가장 확률 높은 토큰만 → 재현성↑. 높으면 다양성↑, 환각·일탈↑.
- **"왜 모델명만 바꿔도 되나요?"** → Gen AI Hub가 벤더별 API 차이를 흡수(harmonize)하기 때문. 프록시가 중간에서 변환.
- **"환각을 완전히 없앨 수 있나요?"** → 완전히는 어렵지만, 그라운딩(근거 주입)·낮은 temperature·"모르면 모른다" 지시로 크게 줄임. 모듈 4에서 실습.
- **"max_tokens는?"** → 출력 길이 상한. 모듈 3에서 `params` 로 설정.

## ⚠️ 흔한 실수

- 멀티모달 셀에서 **비(非)멀티모달 모델** 지정 → 이미지 입력 에러. `gpt-5.6-sol` 등 멀티모달 모델 쓰도록.
- 이미지 경로 오류(`documents/...`) — 노트북 작업 디렉터리 기준 상대경로 확인.
- `response.choices[0].message.content` 구조를 헷갈림 — OpenAI 응답 스키마와 동일하다고 안내.

## ⏭️ 전환 멘트

> "모델이 '모르는 걸 지어낸다'는 문제를 봤습니다. 이걸 풀려면 관련 문서를 찾아 넣어줘야 하는데 — 그 '관련'을 기계가 어떻게 판단할까요? 바로 임베딩입니다. 다음 모듈에서 텍스트를 숫자로 바꿔 '의미가 가깝다'를 계산해 보겠습니다."
