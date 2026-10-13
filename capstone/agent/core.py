# -*- coding: utf-8 -*-
"""
캡스톤 에이전트 코어 — 두 모드 모두 AI Core Orchestration 기반.
  모드 A (고정형): 정해진 순서로만 수행 (코드가 흐름 고정) + Orchestration으로 governed 생성
  모드 B (자율형): 목표만 받으면 Orchestration(두뇌)이 도구를 자유 선택·반복 → 목표 달성
Orchestration을 "충분히": 두 모드 모두 데이터 마스킹 + 콘텐츠 필터 적용.
"""
import json
from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
from gen_ai_hub.orchestration_v2.models.message import (
    SystemMessage, UserMessage, AssistantMessage, ToolChatMessage)
from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
from gen_ai_hub.orchestration_v2.models.content_filtering import FilteringModuleConfig, InputFiltering, OutputFiltering
from gen_ai_hub.orchestration_v2.models.content_filter import ContentFilter, ContentFilterProvider
from gen_ai_hub.orchestration_v2.models.azure_content_filter import AzureContentFilter, AzureThreshold
from gen_ai_hub.orchestration_v2.models.data_masking import (
    MaskingModuleConfig, MaskingProviderConfig, MaskingMethod,
    DataMaskingProviderName, DPIStandardEntity, ProfileEntity)
from gen_ai_hub.orchestration_v2.service import OrchestrationService
from gen_ai_hub.orchestration_v2.exceptions import OrchestrationError

from . import config, tools

def _llm():
    return LLMModelDetails(name=config.LLM_MODEL)  # gpt-5.6-sol 등 (temperature=0 미지원 → 생략)

def _masking():
    return MaskingModuleConfig(masking_providers=[MaskingProviderConfig(
        type_=DataMaskingProviderName.SAP_DATA_PRIVACY_INTEGRATION,
        method=MaskingMethod.ANONYMIZATION,
        entities=[DPIStandardEntity(type=ProfileEntity.EMAIL), DPIStandardEntity(type=ProfileEntity.PERSON),
                  DPIStandardEntity(type=ProfileEntity.PHONE)])])

def _filtering():
    f = ContentFilter(type=ContentFilterProvider.AZURE, config=AzureContentFilter(
        hate=AzureThreshold.ALLOW_SAFE, violence=AzureThreshold.ALLOW_SAFE,
        self_harm=AzureThreshold.ALLOW_SAFE, sexual=AzureThreshold.ALLOW_SAFE))
    return FilteringModuleConfig(input=InputFiltering(filters=[f]), output=OutputFiltering(filters=[f]))

def _service():
    return OrchestrationService(api_url=config.orchestration_url())

def _exec_tool(tc):
    """tool_call 하나를 안전하게 실행. 모르는 도구/인자 오류도 '관찰'로 돌려 루프가 깨지지 않게 한다."""
    name = tc.function.name
    try:
        args = json.loads(tc.function.arguments or "{}")
    except Exception as e:
        return name, {}, f"[오류] 인자 파싱 실패: {e}"
    if name not in tools.RAW:                                   # LLM이 없는 도구를 지어낸 경우
        return name, args, f"[오류] '{name}' 라는 도구는 없습니다. 사용 가능한 도구: {list(tools.RAW)}"
    try:
        return name, args, str(tools.RAW[name](**args))
    except Exception as e:                                      # 잘못된 인자/실행 오류
        return name, args, f"[오류] 도구 실행 실패({name}): {e}"

# ─────────────────────────── 모드 A · 제한형(단일 라운드) ───────────────────────────
SYSTEM_A = ("너는 재고 담당 에이전트다. 주어진 도구로 현재 상황을 파악해 과업을 수행하라. "
            "도구로 얻을 수 없는 정보는 추측하지 말고 '정보 없음'으로 처리하고, 가정이 필요하면 명시하라. "
            "결과를 한국어로 간결히 정리하라.")

def mode_a_bounded(task: str = "재고를 점검하고 발주가 필요한 품목과 권장 수량을 정리해줘."):
    """LLM에게 도구를 알려주고 LLM이 '한 번' 선택(반복 없음).
    흐름: 도구 등록 → LLM이 도구 pick → 실행 → (도구 없이) 결과로 바로 답.
    = 모드 B와 메커니즘은 같되 '루프가 없다'는 점만 다름. (거버넌스: 마스킹+필터)"""
    tmpl = Template(template=[SystemMessage(content=SYSTEM_A), UserMessage(content="{{?task}}")],
                    tools=tools.ALL_TOOLS)                       # ← 도구를 LLM에 알려줌
    cfg = OrchestrationConfig(modules=ModuleConfig(
        prompt_templating=PromptTemplatingModuleConfig(prompt=tmpl, model=_llm()),
        masking=_masking(), filtering=_filtering()))
    svc = _service()
    trace = []

    res = svc.run(config=cfg, placeholder_values={"task": task})  # 1회차: LLM이 도구 선택
    ch = res.final_result.choices[0]; msg = ch.message
    if ch.finish_reason == "tool_calls" and msg.tool_calls:
        history = res.intermediate_results.templating
        history.append(AssistantMessage(content=msg.content or "", tool_calls=msg.tool_calls))
        for tc in msg.tool_calls:                                # 선택된 도구 실행(안전)
            name, args, out = _exec_tool(tc)
            trace.append({"tool": name, "args": args, "observation": out[:300]})
            history.append(ToolChatMessage(tool_call_id=tc.id, content=out))
        # 반복 없이: 도구를 '빼고' 한 번 더 호출 → 결과로 최종 답만 생성
        final_tmpl = Template(template=[UserMessage(content="위 도구 결과로 과업 결과를 정리해줘.")])
        final_cfg = OrchestrationConfig(modules=ModuleConfig(
            prompt_templating=PromptTemplatingModuleConfig(prompt=final_tmpl, model=_llm()),
            masking=_masking(), filtering=_filtering()))
        res2 = svc.run(config=final_cfg, history=history)
        answer = res2.final_result.choices[0].message.content
    else:
        answer = msg.content                                     # 도구 없이 바로 답한 경우
    return {"mode": "A-bounded", "task": task, "trace": trace, "answer": answer}

# ─────────────────────────── 모드 B · 목표지향 자율형 ───────────────────────────
SYSTEM_B = ("너는 재고/발주 자율 에이전트다. 목표만 주어지면 필요한 도구(재고/공급사/환율/정책)를 "
            "스스로 선택·반복 호출해 달성하라. 수입 품목은 환율을 반드시 고려하라. "
            "도구를 호출할 때는, 응답 본문(content)에 '왜 이 도구를 쓰는지'를 한 문장 생각(가설)으로 "
            "한국어로 먼저 적어라. "
            "도구로 얻을 수 없지만 과업에 타당하게 필요한 정보/역량이 있으면, 추측하지 말고 "
            "need_info(topic, reason) 도구로 그 필요를 명시적으로 요청하라(미충족 요구로 기록됨). "
            "충분히 정보를 모았으면, 발주가 필요한 각 품목에 대해 draft_reorder 도구로 발주 초안을 "
            "'행동'으로 생성한 뒤, 무엇을 왜 발주했는지 한국어로 간결히 요약·결론지어라.")

def mode_b_autonomous(goal: str, max_iter: int = 8):
    """목표만 받아 Orchestration(두뇌)이 도구를 자유롭게 쓰며 반복 → 최종 결론.
    Orchestration이 tool_call 출력 → 코드가 실행 → ToolChatMessage로 되먹임 → 반복."""
    template = Template(
        template=[SystemMessage(content=SYSTEM_B), UserMessage(content="{{?goal}}")],
        tools=tools.ALL_TOOLS)
    cfg = OrchestrationConfig(modules=ModuleConfig(
        prompt_templating=PromptTemplatingModuleConfig(prompt=template, model=_llm()),
        masking=_masking(), filtering=_filtering()))
    svc = _service()
    tools.clear_drafts(); tools.clear_needs()                   # 이번 실행의 행동(초안)·미충족 need 초기화
    trace, history, q = [], None, goal
    for _ in range(max_iter):
        res = svc.run(config=cfg, placeholder_values={"goal": q}, history=history)
        ch = res.final_result.choices[0]
        msg = ch.message
        if ch.finish_reason == "tool_calls" and msg.tool_calls:
            history = res.intermediate_results.templating
            history.append(AssistantMessage(content=msg.content or "", tool_calls=msg.tool_calls))
            for tc in msg.tool_calls:
                name, args, out = _exec_tool(tc)               # 안전 실행(모르는 도구/오류도 관찰로)
                trace.append({"tool": name, "args": args, "observation": out[:300]})
                history.append(ToolChatMessage(tool_call_id=tc.id, content=out))
            q = "도구 결과를 반영해 계속 진행하고, 목표가 달성되면 결론을 내라."
        else:
            return {"mode": "B-autonomous", "goal": goal, "trace": trace,
                    "drafts": tools.get_drafts(), "needs": tools.get_needs(), "answer": msg.content}
    return {"mode": "B-autonomous", "goal": goal, "trace": trace,
            "drafts": tools.get_drafts(), "needs": tools.get_needs(),
            "answer": "(최대 반복 도달 — 중간 결과 참고)"}

def mode_b_stream(goal: str, max_iter: int = 8):
    """모드 B를 '이벤트 제너레이터'로 — 진행바/단계표시를 위해 턴·도구 이벤트를 흘려보낸다."""
    template = Template(
        template=[SystemMessage(content=SYSTEM_B), UserMessage(content="{{?goal}}")],
        tools=tools.ALL_TOOLS)
    cfg = OrchestrationConfig(modules=ModuleConfig(
        prompt_templating=PromptTemplatingModuleConfig(prompt=template, model=_llm()),
        masking=_masking(), filtering=_filtering()))
    svc = _service()
    tools.clear_drafts(); tools.clear_needs()
    trace, history, q = [], None, goal
    yield {"event": "start", "goal": goal, "max_iter": max_iter}
    for turn in range(1, max_iter + 1):
        yield {"event": "phase", "phase": "reason", "turn": turn}       # ① LLM 추론(Orchestration 호출)
        res = svc.run(config=cfg, placeholder_values={"goal": q}, history=history)
        ch = res.final_result.choices[0]; msg = ch.message
        if ch.finish_reason == "tool_calls" and msg.tool_calls:
            history = res.intermediate_results.templating
            history.append(AssistantMessage(content=msg.content or "", tool_calls=msg.tool_calls))
            if msg.content:                                             # 💭 생각(가설) — 왜 이 도구를
                trace.append({"thought": msg.content, "turn": turn})
                yield {"event": "thought", "turn": turn, "text": msg.content}
            yield {"event": "phase", "phase": "select", "turn": turn,    # ② 도구 선택(모델이 고름)
                   "tools": [tc.function.name for tc in msg.tool_calls]}
            for tc in msg.tool_calls:
                yield {"event": "phase", "phase": "act", "turn": turn,  # ③ 도구 실행(함수 호출)
                       "tool": tc.function.name}
                name, args, out = _exec_tool(tc)
                trace.append({"tool": name, "args": args, "observation": out[:300]})
                history.append(ToolChatMessage(tool_call_id=tc.id, content=out))
                yield {"event": "phase", "phase": "observe", "turn": turn,  # 👀 관찰(결과 되먹임)
                       "tool": name, "args": args, "observation": out[:200]}
            q = "도구 결과를 반영해 계속 진행하고, 목표가 달성되면 결론을 내라."
        else:
            yield {"event": "done", "answer": msg.content, "trace": trace,
                   "drafts": tools.get_drafts(), "needs": tools.get_needs()}
            return
    yield {"event": "done", "answer": "(최대 반복 도달 — 중간 결과 참고)", "trace": trace,
           "drafts": tools.get_drafts(), "needs": tools.get_needs()}
