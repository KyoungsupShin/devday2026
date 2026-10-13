# -*- coding: utf-8 -*-
"""Step 1 · LLM 프롬프트 기초 (실습자용 모듈 1)
  1) 기본 chat 호출
  2) system role 로 어조 바꾸기
  3) 환각 관찰 (모듈 4에서 다시 비교할 질문)
실행: .venv/bin/python step01_llm.py
"""
import _env
_env.load()

from gen_ai_hub.proxy.native.openai import chat

MODEL_NAME = "gpt-5.6-sol"

print("=" * 56)
print("Step 1 · LLM 프롬프트 기초")
print("=" * 56)

# 1) 기본 chat 호출 (교재는 긴 질문이지만, 공유 테넌트 배려로 짧게 PONG 확인부터)
print("\n[1] 기본 chat 호출")
messages = [{"role": "user", "content": "Reply with exactly one word: PONG"}]
resp = chat.completions.create(model_name=MODEL_NAME, messages=messages)
print("  요청: 'Reply with exactly one word: PONG'")
print("  응답:", resp.choices[0].message.content)

# 2) system role 로 어조 제어 (요다 말투)
print("\n[2] system role — 어조 바꾸기 (요다 말투)")
messages = [
    {"role": "system", "content": "Speak like Yoda from Star Wars. One short sentence."},
    {"role": "user", "content": "What is an LLM?"},
]
resp = chat.completions.create(model_name=MODEL_NAME, messages=messages)
print("  응답:", resp.choices[0].message.content)

# 3) 환각 관찰 — 모듈 4(그라운딩)에서 같은 질문으로 비교할 것
print("\n[3] 환각 관찰 (그라운딩 전/후 비교용 질문)")
messages = [
    {"role": "system", "content": "You are an SAP Consultant. Answer in 2 sentences."},
    {"role": "user", "content": "How does the data masking of the orchestration service work?"},
]
resp = chat.completions.create(model_name=MODEL_NAME, messages=messages)
print("  질문: How does the data masking of the orchestration service work?")
print("  응답(그라운딩 없음):", resp.choices[0].message.content)

print("\n✅ Step 1 완료 — role/환각 확인. [3]의 답을 Step 4와 비교하세요.")
