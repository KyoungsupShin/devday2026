# 4. Agent Patterns

Food Manufacturing Agent Pattern의 세 실습은 모두 AI Core LLM과 공통 Food 도메인 모델을 사용합니다.

- `notebooks/01_agent_workflow.ipynb`: Cohere Rerank가 Chat/Work를 선택하고, Work Planning Agents가 전문 Agent 협업을 조율하는 고정 workflow입니다.
- `notebooks/02_agent_loop_mcp.ipynb`: 01의 Agent Graph를 유지한 채 전문 Agent가 읽기 전용 Tool Calling을 사용하는 흐름입니다. 별도 MCP 서버는 실행하지 않습니다.
- `notebooks/03_agent_to_agent.ipynb`: Food Researcher가 Launch Advisor에게 명시적 artifact를 전달하는 LLM 기반 A2A handoff입니다.
- `src/`: 프레임워크에 묶이지 않은 Food workflow, Graph 내 Tool Calling, A2A core 및 얇은 Gradio UI 구현입니다.
- `demo_app/`: 이전 AI Core Orchestration 기반 캡스톤 웹/API 예제입니다.

모든 현재 core API는 외부 쓰기 작업을 수행하지 않습니다. 02의 MCP Tool 계약과 03의 handoff artifact는 노트북과 UI에서 직접 확인할 수 있습니다.
