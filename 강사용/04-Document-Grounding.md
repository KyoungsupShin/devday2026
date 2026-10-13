# 모듈 4 · Document Grounding + Streaming (강사용)

🎯 **목표**: 관리형 RAG(그라운딩)로 환각을 잡고, 모듈 1과 수미상관을 완성.
⏱️ **시간**: 40분 (설명 12분 + 실습·실험 28분)
📓 기반: `09-orchestration-service-grounding.ipynb`

---

## 🧑‍🏫 강사 노트 — 핸즈온의 클라이맥스

이 모듈이 서사의 정점입니다. 모듈 1에서 심은 "환각" 문제를 여기서 해결합니다. **반드시 before/after를 같은 질문으로 보여주세요.** 이 한 번의 비교가 참가자가 가져갈 가장 큰 깨달음입니다.

핵심 메시지: **"직접 벡터 DB를 안 만들어도 RAG가 된다."** 모듈 2에서 임베딩·유사도를 손으로 계산했는데, 그라운딩은 그 전 과정(청킹·임베딩·검색)을 SAP가 대신해 줍니다. 그래서 코드가 필터 하나 추가하는 수준으로 짧습니다.

## 1~2. 그라운딩 config

🧑‍🏫 작동 원리를 칠판 그림처럼 설명:

```
질문(user_query)
   → [Grounding] help.sap.com에서 검색 → 결과를 grounding_response 로
   → [Template] Context: {{?grounding_response}} 자리에 주입
   → [LLM] 근거를 보고 답변
```

- `DocumentGroundingFilter(id="SAPHelp", data_repository_type="help.sap.com")`: SAP가 운영하는 **공개 관리형 저장소**. 설정 부담 0.
- `DocumentGroundingPlaceholders(input=["user_query"], output="grounding_response")`: 어떤 변수로 검색하고, 결과를 어떤 변수로 받을지.

💬 **이렇게 말하세요**: "모듈 2 기억나시죠? 질문을 임베딩해서 가까운 문서를 찾는 거. 그걸 지금 SAP가 `help.sap.com` 문서로 대신 해줍니다. 우리는 '이 저장소에서 찾아줘'라고 필터 한 줄만 쓰면 되고요."

## 3. 스트리밍

🧑‍🏫 `.run()` → `.stream()`, 응답은 `delta.content` 를 이어 붙임. UX 관점: 긴 답변을 기다리지 않고 토큰이 흘러나와 체감 지연↓. ChatGPT 타이핑 효과와 동일 원리.

🎬 스트리밍은 라이브로 보여줄 때 효과적 — 터미널에 글자가 주르륵 나오는 걸 보여주세요.

## 직접 바꿔보기 (실험) — ⭐ 수미상관 데모

🎬 **반드시 할 것**: 모듈 1의 환각 질문을 그대로 다시.

```python
# 그라운딩 없이 (모듈 1 방식) vs 그라운딩 있이 (이 모듈) 같은 질문
q = "How does the data masking of the orchestration service work?"
```

진행:
1. "모듈 1에서 이 질문에 모델이 그럴듯하게 답했지만 진짜인지 몰랐죠. 메모해두신 답 꺼내보세요."
2. 그라운딩 config로 같은 질문 실행.
3. "이번엔 SAP Help 문서를 근거로 답합니다. 두 답을 비교해 보세요 — 무엇이 달라졌나요?"

💬 참가자에게 직접 말로 차이를 설명하게 하세요. "출처가 생겼다 / 구체적이다 / 더 정확하다" 같은 답이 나오면 성공.

## ❓ 예상 질문 & 답

- **"내 회사 문서로 하려면?"** → `data_repository_type="vector"` + `data_repositories=[내 저장소 id]`. 저장소는 Grounding Management(UI)로 미리 만들어 문서 수집. **바로 다음 모듈 5에서 실습**.
- **"그라운딩이 관련 문서를 못 찾으면?"** → 엉뚱하거나 빈 context → 여전히 환각 가능. 그래서 템플릿에 "context에 없으면 모른다고 답하라"를 넣는 게 실무 팁.
- **"출처(citation)도 받을 수 있나요?"** → 그라운딩 응답에 메타데이터가 포함될 수 있음. 실무에선 출처 표시가 신뢰의 핵심.
- **"help.sap.com 말고 공개 저장소 더 있나요?"** → `data_repository_type` 종류는 SAP Help 문서에서 확인. 핵심은 "타입만 바꾸면 소스가 바뀐다".

## ⚠️ 흔한 실수

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| 빈/엉뚱한 답 | placeholder 이름 불일치 | `input`/`output` 이름과 템플릿 `{{?...}}` 일치 확인 |
| grounding 무시됨 | `grounding=grounding_config` 누락 | `ModuleConfig` 에 포함했는지 |
| 스트리밍 안 나옴 | `stream` 옵션 누락 | `GlobalStreamOptions(enabled=True)` |

## ⏭️ 전환 멘트

> "그라운딩이 환각을 어떻게 잡는지 봤습니다. 그런데 방금은 **공개 SAP Help** 문서였죠. 다음 모듈에서는 **우리 문서**로 똑같이 해봅니다. 놀랍게도 바뀌는 건 필터 한 줄이에요 — `help.sap.com` 이 우리 저장소로. 소스 교체가 얼마나 쉬운지 보게 됩니다."
