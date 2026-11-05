"""Core workflow for 01_prompt_and_model.ipynb."""

from __future__ import annotations

import ast
import json
import operator
import re
from collections.abc import Iterator
from typing import Any, Callable, Sequence

from .lesson_support.llm import chat_text, chat_text_stream, chat_tool_completion
from .lesson_support.config import Settings

MAX_CHAT_HISTORY_MESSAGES = 12
MAX_CHAT_HISTORY_CHARACTERS = 12_000
DEFAULT_COMPARISON_SYSTEM_PROMPT = (
    "너는 교육 보조자다. 반드시 한국어 Markdown으로만 답한다. "
    "설명 문단을 쓰지 말고, 먼저 '## 핵심 요약' 제목과 한 문장을 쓴다. "
    "그 다음 '## 구성 요소' 제목 아래에 '구성 요소 | 역할' 열을 가진 "
    "Markdown 표를 정확히 세 행으로 작성한다. 마지막에는 '## 기억할 점' 제목과 "
    "핵심 bullet 하나를 작성한다. 제목, 표, bullet 외의 텍스트는 쓰지 않는다."
)
MAX_REACT_TOOL_TURNS = 3
MAX_ADAPTIVE_REACT_TOOL_TURNS = 5
CALCULATOR_TOOL = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "사칙연산과 괄호가 있는 수식을 정확히 계산합니다.",
        "parameters": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
}
REACT_SYSTEM_INSTRUCTION = """
너는 계산 도구를 사용할 수 있는 ReAct(Reason → Act → Observe) 에이전트다.

사용 가능한 도구:
- calculate(expression: str): 사칙연산과 괄호가 있는 수식을 정확히 계산한다.

각 턴에서 다음 ReAct 순서를 따른다.
1. Thought (Reason): 질문과 이전 Observation을 보고 다음 행동을 결정한다. 결정 근거만 한두 문장으로
   <thinking>와 </thinking> 사이에 쓴다. 장문의 비공개 추론이나 풀이 과정 전체를 쓰지 않는다.
2. Action (Act): 계산값이 필요하면 반드시 calculate 도구를 호출한다. Action은 일반 텍스트가 아니라
   제공된 함수 호출로 수행하며, expression에는 계산할 수식만 넣는다.
3. Observation (Observe): 도구가 반환한 결과를 관찰값으로 사용한다. 관찰값이 없는 계산 결과를
   추측하거나 지어내지 않는다.
4. Final Answer: 답에 필요한 관찰값이 충분할 때만 최종 답을 작성한다. 사용자에게 줄 답은
   <answer>와 </answer> 사이에 쓴다.

계산이 필요 없는 질문에는 도구를 호출하지 않아도 된다. 도구 결과만으로 답할 수 없거나 도구 호출에
실패하면, 그 한계를 <answer> 안에서 명확히 설명한다.

출력 규칙:
- 도구 호출 전: <thinking>...</thinking>만 작성하고 calculate 함수를 호출한다.
- 도구 호출 후: <thinking>...</thinking><answer>...</answer> 형식으로 답한다.
""".strip()
ADAPTIVE_REACT_SYSTEM_INSTRUCTION = """
너는 계획을 상황에 맞게 수정하는 Adaptive ReAct 에이전트다. 제공된 작업 계획과 이전 도구
관찰값을 이용해 Plan/Reason → Act → Observe → Evaluate 순환을 반복하고, 답에 필요한 근거가
충분할 때만 Final Answer를 작성한다.

사용 가능한 도구:
- calculate(expression: str): 사칙연산과 괄호가 있는 수식을 정확히 계산한다.

각 턴의 동작 규칙:
1. Plan/Reason: 현재 질문, 작업 계획, 이전 Observation을 확인하고 다음 행동을 정한다. 공개 가능한
   짧은 근거만 <thinking>와 </thinking> 사이에 쓴다. 장문의 비공개 추론은 쓰지 않는다.
2. Act: 계산 또는 수치 검증이 필요하면 calculate 도구를 호출한다. Action은 텍스트로 흉내 내지 말고
   제공된 함수 호출로 수행하며 expression에는 수식만 넣는다.
3. Observe: 도구 반환값을 Observation으로 사용한다. 도구 결과가 없는 계산값을 추측하지 않는다.
4. Evaluate: Observation을 기준으로 결과의 정확성·충분성·다음 행동을 평가한다. 평가는
   <evaluation>와 </evaluation> 사이에 짧게 쓴다. 추가 근거가 필요하면 계획이나 수식을 고쳐
   다음 도구 호출을 한다. 도구 오류가 나면 같은 잘못된 호출을 반복하지 않는다.
5. Final Answer: 필요한 근거가 충분할 때에만 사용자 답변을 <answer>와 </answer> 사이에 작성한다.

출력 규칙:
- 첫 도구 호출 전: <thinking>...</thinking>을 쓰고 도구를 호출한다.
- Observation 뒤 추가 행동이 필요하면: <thinking>...</thinking><evaluation>...</evaluation>을 쓰고
  수정된 도구를 호출한다.
- 최종 응답: <thinking>...</thinking><evaluation>...</evaluation><answer>...</answer> 형식으로 쓴다.
- 도구 없이 답할 수 있는 질문도 <thinking>, <evaluation>, <answer> 태그를 모두 사용한다.
""".strip()
ADAPTIVE_PLANNER_SYSTEM_INSTRUCTION = (
    "너는 Adaptive ReAct의 Plan 단계만 담당하는 작업 계획기다. 사용자 질문을 분석해 목표, 필요한 근거, "
    "도구 사용 여부를 판단하고 실행 가능한 하위 작업으로 나눈다. 아직 도구를 호출하거나 최종 답을 만들지 않는다. "
    "반드시 Markdown 없이 JSON 객체만 반환한다. category는 calculation, explanation, comparison, or mixed 중 하나다. "
    "complexity는 simple 또는 multi_step이다. subtasks는 id, assignee, goal 키를 가진 배열이고 id는 번호가 아닌 짧은 한국어 작업명이다. assignee는 "
    "reasoning 또는 calculator 중 하나다. strategy는 한국어 한 문장으로 쓴다."
)


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _response_message(response: Any) -> Any:
    choices = _field(response, "choices", [])
    if not choices:
        raise RuntimeError("ReAct 에이전트 응답에 choice가 없습니다.")
    return _field(choices[0], "message")


def _public_reasoning_and_answer(content: str) -> tuple[str, str, str]:
    """Read the concise, model-authored public reasoning from a ReAct turn."""
    thinking = re.search(r"<thinking>\s*(.*?)\s*</thinking>", content, flags=re.DOTALL)
    answer = re.search(r"<answer>\s*(.*?)\s*</answer>", content, flags=re.DOTALL)
    evaluation = re.search(r"<evaluation>\s*(.*?)\s*</evaluation>", content, flags=re.DOTALL)
    public_reasoning = thinking.group(1).strip() if thinking else ""
    final_answer = answer.group(1).strip() if answer else content.strip()
    if not answer:
        final_answer = re.sub(
            r"<(?:thinking|evaluation)>.*?</(?:thinking|evaluation)>",
            "",
            content,
            flags=re.DOTALL,
        ).strip()
    return public_reasoning, final_answer, evaluation.group(1).strip() if evaluation else ""


def _structured_react_reply(thinking: str, answer: str, evaluation: str) -> str:
    """Build a parser-friendly, public summary of a completed ReAct turn."""
    parts = [
        f"<thinking>{thinking.strip()}</thinking>",
        f"<answer>{answer.strip()}</answer>",
    ]
    if evaluation.strip():
        parts.append(f"<evaluation>{evaluation.strip()}</evaluation>")
    return "\n".join(parts)


def _adaptive_plan(raw: str) -> dict[str, Any]:
    """Validate a planner response before it influences agent execution."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        value = {}
    subtasks = value.get("subtasks") if isinstance(value, dict) else None
    if not isinstance(subtasks, list):
        subtasks = [{"id": "answer", "assignee": "reasoning", "goal": "질문에 답합니다."}]
    normalized_subtasks = [
        {
            "id": str(item.get("id", "task")),
            "assignee": str(item.get("assignee", "reasoning")),
            "goal": str(item.get("goal", "질문을 처리합니다.")),
        }
        for item in subtasks
        if isinstance(item, dict)
    ] or [{"id": "answer", "assignee": "reasoning", "goal": "질문에 답합니다."}]
    return {
        "category": str(value.get("category", "explanation")) if isinstance(value, dict) else "explanation",
        "complexity": str(value.get("complexity", "simple")) if isinstance(value, dict) else "simple",
        "subtasks": normalized_subtasks,
        "strategy": str(value.get("strategy", "질문을 분석한 뒤 답변을 작성합니다.")) if isinstance(value, dict) else "질문을 분석한 뒤 답변을 작성합니다.",
    }


def _calculator(expression: str) -> float | int:
    """Evaluate a deliberately small arithmetic grammar without eval()."""
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 200:
        raise ValueError("계산식은 1~200자 문자열이어야 합니다.")
    operators = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
    }

    def evaluate(node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
            return operators[type(node.op)](evaluate(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](evaluate(node.left), evaluate(node.right))
        raise ValueError("허용되지 않은 계산식입니다. 숫자, 괄호, + - * / // % ** 만 사용하세요.")

    return evaluate(ast.parse(expression, mode="eval").body)


def compare_prompts(
    question: str,
    settings: Settings,
    chat_caller: Callable[
        [Settings, list[dict[str, str]], str | None], str
    ] = chat_text,
    system_prompt: str = DEFAULT_COMPARISON_SYSTEM_PROMPT,
) -> dict[str, str]:
    cleaned = question.strip()
    if not cleaned:
        raise ValueError("질문을 입력하세요.")
    constrained_system_prompt = system_prompt.strip()
    if not constrained_system_prompt:
        raise ValueError("비교할 system prompt를 입력하세요.")
    baseline = chat_caller(settings, [{"role": "user", "content": cleaned}], None)
    constrained = chat_caller(
        settings,
        [
            {
                "role": "system",
                "content": constrained_system_prompt,
            },
            {"role": "user", "content": cleaned},
        ],
        None,
    )
    return {"question": cleaned, "baseline": baseline, "constrained": constrained}


def _chat_messages(
    message: str, history: Sequence[dict[str, str]] = (), system_prompt: str = ""
) -> tuple[str, list[dict[str, str]]]:
    cleaned = message.strip()
    if not cleaned:
        raise ValueError("질문을 입력하세요.")
    normalized: list[dict[str, str]] = []
    for item in history:
        role, content = item.get("role"), str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            raise ValueError(
                "대화 history에는 내용이 있는 user 또는 assistant 메시지만 넣을 수 있습니다."
            )
        normalized.append({"role": role, "content": content})
    retained: list[dict[str, str]] = []
    remaining = MAX_CHAT_HISTORY_CHARACTERS
    for item in reversed(normalized[-MAX_CHAT_HISTORY_MESSAGES:]):
        if len(item["content"]) <= remaining:
            retained.append(item)
            remaining -= len(item["content"])
    messages = (
        [{"role": "system", "content": system_prompt.strip()}]
        if system_prompt.strip()
        else []
    )
    messages.extend(reversed(retained))
    messages.append({"role": "user", "content": cleaned})
    return cleaned, messages


def run_chat(
    message: str,
    settings: Settings,
    history: Sequence[dict[str, str]] = (),
    system_prompt: str = "",
    model: str | None = None,
    chat_caller: Callable[
        [Settings, list[dict[str, str]], str | None], str
    ] = chat_text,
) -> dict[str, str]:
    cleaned, messages = _chat_messages(message, history, system_prompt)
    selected_model = model.strip() if model and model.strip() else settings.llm_model
    return {
        "message": cleaned,
        "model": selected_model,
        "reply": chat_caller(settings, messages, selected_model),
    }


def run_chat_stream(
    message: str,
    settings: Settings,
    history: Sequence[dict[str, str]] = (),
    system_prompt: str = "",
    model: str | None = None,
    chat_stream_caller: Callable[
        [Settings, list[dict[str, str]], str | None], Iterator[str]
    ] = chat_text_stream,
) -> Iterator[str]:
    _, messages = _chat_messages(message, history, system_prompt)
    selected_model = model.strip() if model and model.strip() else settings.llm_model
    yield from chat_stream_caller(settings, messages, selected_model)


def run_react_agent(
    message: str,
    settings: Settings,
    history: Sequence[dict[str, str]] = (),
    system_prompt: str = "",
    model: str | None = None,
    agent_caller: Callable[..., Any] = chat_tool_completion,
    tool_runner: Callable[[str], float | int] = _calculator,
    _instruction: str = REACT_SYSTEM_INSTRUCTION,
    _max_tool_turns: int = MAX_REACT_TOOL_TURNS,
) -> dict[str, Any]:
    """Run a bounded ReAct loop with one local, read-only calculator tool.

    The returned observations are public UI evidence; private model reasoning is
    never collected or displayed.
    """
    supplied_system_prompt = system_prompt.strip()
    # The UI exposes the actual agent instruction for editing. Avoid sending it
    # twice, while callers that supply only an extra instruction still receive
    # the mandatory ReAct behavior.
    combined_system_prompt = supplied_system_prompt
    if _instruction and _instruction not in supplied_system_prompt:
        combined_system_prompt = "\n\n".join(
            part for part in (supplied_system_prompt, _instruction) if part
        )
    cleaned, messages = _chat_messages(message, history, combined_system_prompt)
    selected_model = model.strip() if model and model.strip() else settings.llm_model
    observations: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []

    for turn in range(_max_tool_turns + 1):
        response = agent_caller(
            settings,
            messages,
            [CALCULATOR_TOOL],
            selected_model,
            "none" if turn == _max_tool_turns else "auto",
        )
        assistant = _response_message(response)
        raw_calls = list(_field(assistant, "tool_calls", []) or [])
        content = str(_field(assistant, "content", "") or "")
        public_reasoning, final_answer, agent_evaluation = _public_reasoning_and_answer(content)
        if not raw_calls:
            final_reply = final_answer or "에이전트가 최종 답변을 반환하지 않았습니다."
            public_summary = public_reasoning or (
                "도구가 필요한 요청인지 확인했습니다. 현재 질문은 도구 없이 답할 수 있습니다."
                if not observations else "도구 관찰값을 바탕으로 사용자에게 전달할 답을 정리합니다."
            )
            evaluation_summary = agent_evaluation or (
                "질문에 필요한 도구가 없음을 확인하고 최종 답변을 생성했습니다."
                if not observations else "도구 실행 결과를 사용한 최종 응답 단계를 마쳤습니다."
            )
            if not observations:
                trace.append({
                    "thinking": public_summary,
                    "evaluation": evaluation_summary,
                    "answer": final_reply,
                })
            else:
                trace.append({
                    "thinking": public_summary,
                    "evaluation": evaluation_summary,
                    "answer": final_reply,
                })
            return {
                "message": cleaned,
                "model": selected_model,
                "reply": final_reply,
                "structured_reply": _structured_react_reply(
                    public_summary, final_reply, evaluation_summary,
                ),
                "tool_calls": observations,
                "trace": trace,
            }

        if turn == _max_tool_turns:
            raise RuntimeError(f"ReAct 도구 호출은 최대 {_max_tool_turns}회까지 허용됩니다.")

        assistant_calls: list[dict[str, Any]] = []
        tool_messages: list[dict[str, str]] = []
        for raw_call in raw_calls:
            function = _field(raw_call, "function")
            name = _field(function, "name")
            call_id = _field(raw_call, "id")
            raw_arguments = _field(function, "arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError as error:
                raise RuntimeError("도구 호출 arguments가 유효한 JSON이 아닙니다.") from error
            if not isinstance(name, str) or not isinstance(call_id, str) or not isinstance(arguments, dict):
                raise RuntimeError("도구 호출 형식이 올바르지 않습니다.")
            if name != "calculate":
                result: dict[str, Any] = {"error": f"허용되지 않은 도구입니다: {name}"}
            else:
                try:
                    result = {"expression": arguments.get("expression"), "value": tool_runner(arguments.get("expression"))}
                except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
                    result = {"error": f"{type(error).__name__}: {error}"}
            observations.append({"name": name, "arguments": arguments, "result": result})
            succeeded = "error" not in result
            trace.append({
                "thinking": public_reasoning or (
                    "정확한 수치 계산이 필요해 계산 도구로 식을 확인합니다."
                    if name == "calculate"
                    else "요청을 처리하기 위해 선택한 도구를 실행합니다."
                ),
                "action": f"{name}({json.dumps(arguments, ensure_ascii=False)})",
                "observation": json.dumps(result, ensure_ascii=False),
                "evaluation": agent_evaluation or (
                    "도구 결과를 받았습니다. 이 관찰값을 다음 응답 생성에 사용합니다."
                    if succeeded
                    else "도구 실행에 실패했습니다. 오류를 반영해 다음 단계를 결정합니다."
                ),
            })
            assistant_calls.append({
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
            })
            tool_messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False),
            })
        messages.extend([
            {"role": "assistant", "content": content, "tool_calls": assistant_calls},
            *tool_messages,
        ])

    raise RuntimeError("ReAct 에이전트가 종료되지 않았습니다.")


def run_adaptive_react_agent(
    message: str,
    settings: Settings,
    history: Sequence[dict[str, str]] = (),
    system_prompt: str = "",
    model: str | None = None,
    agent_caller: Callable[..., Any] = chat_tool_completion,
    tool_runner: Callable[[str], float | int] = _calculator,
    planner_caller: Callable[[Settings, list[dict[str, str]], str | None], str] = chat_text,
) -> dict[str, Any]:
    """Classify and allocate work before running the adaptive ReAct loop."""
    selected_model = model.strip() if model and model.strip() else settings.llm_model
    plan = _adaptive_plan(planner_caller(
        settings,
        [
            {"role": "system", "content": ADAPTIVE_PLANNER_SYSTEM_INSTRUCTION},
            {"role": "user", "content": message.strip()},
        ],
        selected_model,
    ))
    planning_context = "Adaptive 작업 계획:\n" + json.dumps(plan, ensure_ascii=False)
    outcome = run_react_agent(
        message,
        settings,
        history,
        "\n\n".join(part for part in (system_prompt.strip(), planning_context) if part),
        model,
        agent_caller,
        tool_runner,
        _instruction=ADAPTIVE_REACT_SYSTEM_INSTRUCTION,
        _max_tool_turns=MAX_ADAPTIVE_REACT_TOOL_TURNS,
    )
    planning_step = {
        "thinking": "질문의 유형과 난이도를 분류한 뒤, 필요한 하위 작업을 역할별로 나눕니다.",
        "action": "질문 분류 및 하위 작업 배정",
        "observation": json.dumps(plan, ensure_ascii=False),
        "evaluation": f"{plan['complexity']} 작업으로 판단해 다음 전략을 선택합니다: {plan['strategy']}",
        "plan": plan,
    }
    outcome["trace"].insert(0, planning_step)
    return outcome
