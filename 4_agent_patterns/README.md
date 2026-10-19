# 4. Agent Patterns

Food Manufacturing Agent Pattern의 세 실습은 모두 AI Core LLM과 공통 Food 도메인 모델을 사용합니다.

- `notebooks/01_agent_workflow.ipynb`: Cohere Rerank가 Chat/Work를 선택하고, Work Planning Agents가 전문 Agent 협업을 조율하는 고정 workflow입니다.
- `notebooks/02_agent_loop_mcp.ipynb`: 01의 Agent Graph를 유지한 채 전문 Agent가 읽기 전용 Tool Calling을 사용하는 흐름입니다. 별도 MCP 서버는 실행하지 않습니다.
- `notebooks/03_agent_to_agent.ipynb`: F&B 설비·구매·제조기획·재무·사업기획·IT·EHS 환경안전·인사·총무·공정·R&D·생산·품질 Team Agent가 A2A Protocol 1.0으로 협업합니다. 각 Team은 LLM이 선택한 역할별 Sub-agent와 읽기 전용 로컬 스냅샷 Tool로 근거를 검토하며, Team 선택과 호출 순서는 누적 artifact를 바탕으로 LLM이 결정합니다. 누적 근거가 사람의 제출·승인 판단을 요구하면 Orchestration은 Outlook 메일 초안만 만들며, 검토자가 UI에서 명시적으로 승인해야만 EAI Graph API로 전송합니다.
- `src/`: 노트북별 core와 얇은 Gradio UI 구현입니다.

기본 core API와 모든 LLM Tool은 읽기 전용입니다. 단, 03 UI의 Outlook 전송은 사람이 수신자·제목·본문을 확인하고 `승인 후 Outlook 메일 발송`을 누른 경우에만, 별도 EAI 인증 토큰과 `ALLOW_WRITE_TOOLS=true`가 모두 설정된 상태에서 실행됩니다. 02의 MCP Tool 계약과 03의 A2A Message·Task·Artifact는 노트북과 UI에서 직접 확인할 수 있습니다.

```text
src/
├── agent_workflow/
│   └── lab_core.py
├── agent_loop_mcp/
│   └── lab_core.py
└── agent_to_agent/
    ├── catalog.py
    ├── prompts/             # TOML prompt resources
    ├── data/hana_raw/       # local HANA CSV snapshots
    ├── grounding.py
    ├── tools/               # local snapshot Tool implementations and registry
    ├── transport.py
    ├── orchestration.py
    ├── executor.py
    ├── server.py
    └── ui.py
```

`.env`에 `GROUNDING_REPOSITORY_ID`를 설정하면 03의 Orchestration Agent는 판단에 매뉴얼 근거가 필요할 때만 `search_manuals` Tool을 호출할 수 있습니다. Tool 호출 여부와 검색 질의, Team·Sub-agent 선택은 모두 LLM이 결정합니다. 검색 근거는 이후 Orchestration Agent와 Team/Sub-agent의 입력으로 전달됩니다. 저장소가 비어 있거나 설정되지 않은 상태는 UI와 로그에 남고, 설정된 저장소 조회가 실패하면 근거 없이 계속 진행하지 않고 오류를 표시합니다.

03의 역할별 Tool은 Context ID를 기준으로 설비, 조달, 수급, 생산투입, 수익성, 재무통제, ERP 준비 근거를 읽습니다. Tool은 Team 선택이나 업무 순서를 결정하지 않으며, SQL·HANA 연결·쓰기 기능도 없습니다. 현재 노트북은 **로컬 CSV 스냅샷**을 근거로 사용하며, Tool 결과와 대화 로그에도 이 범위를 함께 남깁니다.

Tool 구현은 `src/agent_to_agent/tools/`에 업무 영역별로 분리되어 있습니다. Sub-agent별 사용 가능 Tool ID는 `catalog.py`에 선언하고, `tool_registry.py`는 schema와 실행 함수만 등록합니다. 따라서 Tool 권한은 명시적으로 검증하지만, Tool 선택·Team 선택·업무 순서는 LLM이 결정합니다.

스냅샷 원천 행은 `src/agent_to_agent/data/hana_raw/`의 UTF-8 CSV에서 관리합니다. Tool 응답의 `raw_csv_path`로 사용한 파일을 확인할 수 있으며, 포함된 `68` 행은 설비 부품 기준정보입니다.

재무·사업기획팀은 OPEX, 구매 승인 기준, Cost Center, 커밋먼트, 예산 이관 스냅샷을 근거로 검토합니다. 이 Tool은 실제 예산·승인·이관·전기를 조회하거나 변경하지 않습니다.

03을 실행하기 전에 별도 터미널에서 아래 명령으로 12개 loopback A2A Agent 서버를 시작하세요.

```bash
python3 4_agent_patterns/main.py fnb-a2a-local
```
