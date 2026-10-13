# -*- coding: utf-8 -*-
"""Step 6 · 메모리 챗봇 (실습자용 모듈 6)
  - history 를 매 호출에 넘겨 '기억'하는 챗봇
  - reset() 후에는 기억 못 함을 확인
실행: .venv/bin/python step06_memory_chatbot.py
"""
import _env
_env.load()

from typing import List

from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
from gen_ai_hub.orchestration_v2.models.message import ChatMessage, SystemMessage, UserMessage
from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
from gen_ai_hub.orchestration_v2.service import OrchestrationService

print("=" * 56)
print("Step 6 · 메모리 챗봇")
print("=" * 56)


class ChatBot:
    def __init__(self, service: OrchestrationService):
        self.service = service
        self.template = Template(template=[
            SystemMessage(content="You are a helpful chatbot assistant."),
            UserMessage(content="{{?user_query}}"),
        ])
        self.llm = LLMModelDetails(name="gpt-5.6-sol", params={"max_tokens": 500})
        self.prompt_template = PromptTemplatingModuleConfig(prompt=self.template, model=self.llm)
        self.config = OrchestrationConfig(modules=ModuleConfig(prompt_templating=self.prompt_template))
        self.history: List[ChatMessage] = []

    def chat(self, user_input):
        response = self.service.run(
            config=self.config,
            placeholder_values={"user_query": user_input},
            history=self.history,
        )
        message = response.final_result.choices[0].message
        self.history = response.intermediate_results.templating
        self.history.append(message)
        return message.content

    def reset(self):
        self.history = []


service = OrchestrationService(api_url=_env.orchestration_url())
bot = ChatBot(service=service)

print("\n[1] 대화 (기억 테스트)")
print("  U: Hi, my name is Jin.")
print("  A:", bot.chat("Hi, my name is Jin."))
print("  U: Do you like SAP CodeJams?")
print("  A:", bot.chat("Do you like SAP CodeJams?"))
print("  U: What is my name?")
ans = bot.chat("What is my name?")
print("  A:", ans)
print("  → 이름 기억? ", "Jin" in ans)

print("\n[2] reset 후 (기억 못 함 테스트)")
bot.reset()
ans2 = bot.chat("What is my name?")
print("  A:", ans2)
print("  → 리셋 후 이름 모름? ", "Jin" not in ans2)

print("\n✅ Step 6 완료 — history 로 맥락 기억, reset 으로 초기화.")
