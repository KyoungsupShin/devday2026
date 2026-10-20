# 4. Agent Patterns

동일한 F&B 도메인에서 workflow, tool calling, A2A, Advanced A2A를 비교합니다. 각 패턴이 Agent 수가 아니라 **제어 흐름·도구 권한·조직 경계**를 어떻게 다르게 다루는지 확인하는 실습입니다.

## 시작 전 준비

1~3단계에서 AI Core와 선택적 grounding을 설정한 뒤 [루트 README](../README.md#사전-준비와-설치)의 공통 환경을 사용하세요. 설치가 아직이면 저장소 루트에서 운영체제에 맞는 한 줄을 실행합니다.

**macOS/Linux**

```bash
python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip -r requirements.txt
```

**Windows PowerShell**

```powershell
py -m venv .venv && .\.venv\Scripts\python.exe -m pip install --upgrade pip -r requirements.txt
```

루트 `.env`에는 AI Core 기본값과 `LLM_MODEL`이 필요합니다. 03·04에서 매뉴얼 grounding이 필요하면 `GROUNDING_REPOSITORY_ID`를 설정합니다.

## 실습 순서

1. `notebooks/01_agent_workflow.ipynb` — 코드가 전이를 고정한 LLM-orchestrated workflow와 route 선택을 확인합니다.
2. `notebooks/02_agent_loop_mcp.ipynb` — Agent graph가 관찰·읽기 전용 tool calling·재관찰을 반복하는 흐름을 확인합니다. 별도 MCP 서버는 실행하지 않습니다.
3. `notebooks/03_agent_to_agent.ipynb` — F&B Team Agent가 A2A Protocol 1.0의 Message·Task·Artifact로 handoff합니다.
4. `notebooks/04_agent_to_agent_advanced.ipynb` — Advanced A2A Team과 선택적 Codex App Server/SQL Generator Agent를 확인합니다.

```bash
.venv/bin/python 4_agent_patterns/main.py --help
.venv/bin/python 4_agent_patterns/main.py workflow "재고를 분석해줘"
```

## A2A 서버 기동: 03·04 실습

JupyterLab을 실행한 터미널과 별도로, 저장소 루트에서 아래 명령을 실행한 뒤 노트북을 엽니다. 준비 메시지가 표시된 상태로 터미널을 유지하고, 종료할 때는 `Ctrl+C`를 누릅니다.

| 노트북 | 별도 터미널 명령 | 로컬 포트 |
| --- | --- | --- |
| 03 `agent_to_agent` | `.venv/bin/python 4_agent_patterns/main.py fnb-a2a-local` | 9111~9122 |
| 04 `agent_to_agent_advanced` | `.venv/bin/python 4_agent_patterns/main.py fnb-a2a-advanced-local` | 9211~9223 |

두 서버 묶음은 다른 포트를 사용하므로 동시에 실행할 수 있습니다. 포트가 이미 사용 중이면 이전 `fnb-a2a-local` 또는 `fnb-a2a-advanced-local` 프로세스를 종료한 뒤 다시 실행합니다. Windows에서는 각 명령의 `.venv/bin/python`을 `.\.venv\Scripts\python.exe`로 바꿉니다.

04의 Codex App Server 예제와 Codex SQL Generator Agent는 `codex` CLI 설치·로그인이 추가로 필요합니다. 이 Agent는 read-only sandbox에서 분석과 단일 읽기 전용 SQL 초안만 만들며 SQL을 실행하지 않습니다.

## 안전 경계

- 기본 core API와 Tool은 읽기 전용 로컬 CSV 스냅샷을 사용합니다. 실제 ERP, HANA, 예산, 승인 데이터를 변경하지 않습니다.
- Team·Sub-agent·Tool 선택은 LLM이 결정하지만, Tool 권한은 catalog와 registry로 명시적으로 제한합니다.
- Grounding 저장소가 비어 있거나 조회에 실패하면 이를 UI와 로그에 표시하며, 근거 없는 계속 실행으로 대체하지 않습니다.
- 03 UI의 Outlook 발송은 초안만 생성합니다. 사람이 수신자·제목·본문을 확인하고 `승인 후 Outlook 메일 발송`을 누른 경우에도, EAI 인증과 `ALLOW_WRITE_TOOLS=true`가 모두 있어야 외부 전송이 가능합니다.

## 확인

```bash
.venv/bin/python -m unittest discover -s 4_agent_patterns/tests -v
```
