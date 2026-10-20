# 04 · Agent Patterns

동일한 F&B 도메인에서 workflow, tool calling, A2A, Advanced A2A를 비교합니다. Agent 수가 아니라 **제어 흐름·도구 권한·조직 경계**가 어떻게 달라지는지 확인하는 단계입니다.

> 공통 환경 설정과 JupyterLab 실행은 [루트 README](../README.md)에서 진행합니다. A2A 노트북은 별도 로컬 Agent 서버가 준비된 뒤 실행합니다.

---

<details>
<summary><strong>🔧 시작 전 확인</strong></summary>

| 실습 범위 | 필요한 준비 |
| --- | --- |
| 기본 workflow·tool calling | AI Core 인증 정보와 `LLM_MODEL` |
| 매뉴얼 grounding | 선택적으로 `GROUNDING_REPOSITORY_ID` |
| A2A 실습 | 03 또는 04에 맞는 로컬 A2A Agent 서버 |
| Codex App Server 예제 | 선택적으로 Codex CLI 설치 및 로그인 |

기본 도구는 읽기 전용 로컬 CSV 스냅샷을 사용합니다. 실제 ERP, HANA, 예산, 승인 데이터는 변경하지 않습니다.

</details>

---

<details>
<summary><strong>📓 노트북 안내</strong></summary>

| 노트북 | 협업 패턴 | 무엇을 확인하나요? |
| --- | --- | --- |
| [01_agent_workflow.ipynb](notebooks/01_agent_workflow.ipynb) | 고정 전이 workflow | 코드가 정한 순서 안에서 LLM이 route를 선택하는 흐름을 확인합니다. |
| [02_agent_loop_mcp.ipynb](notebooks/02_agent_loop_mcp.ipynb) | Tool calling loop | 관찰 → 읽기 전용 도구 호출 → 재관찰의 반복과 Agent graph를 확인합니다. 별도 MCP 서버는 필요하지 않습니다. |
| [03_agent_to_agent.ipynb](notebooks/03_agent_to_agent.ipynb) | A2A | F&B Team Agent가 A2A Protocol 1.0의 Message·Task·Artifact로 handoff하는 방식을 확인합니다. |
| [04_agent_to_agent_advanced.ipynb](notebooks/04_agent_to_agent_advanced.ipynb) | Advanced A2A | Team 단위 협업과 선택적 Codex App Server·SQL Generator Agent의 역할을 확인합니다. |

01부터 04까지 순서대로 실행하면, 단일 workflow에서 조직 경계를 넘는 Agent 협업까지 제어 범위가 확장되는 모습을 비교할 수 있습니다.

</details>

---

<details>
<summary><strong>🖥️ A2A 실습 준비</strong></summary>

03과 04는 JupyterLab과 별도의 터미널에서 각각의 로컬 A2A Agent 서버를 실행한 뒤 시작합니다. 03은 9111~9122, 04는 9211~9223 포트를 사용하므로 두 서버 묶음을 동시에 실행할 수 있습니다. 포트가 이미 사용 중이면 기존 프로세스를 종료한 뒤 다시 시작하세요.

구체적인 서버 실행 명령은 [루트 README](../README.md)의 Agent Patterns 안내를 따릅니다. 04의 Codex SQL Generator Agent는 읽기 전용 sandbox에서 단일 읽기 전용 SQL 초안만 만들며, SQL을 실행하지 않습니다.

</details>

---

<details>
<summary><strong>🔐 안전 경계</strong></summary>

- Team·Sub-agent·Tool 선택은 LLM이 결정해도, 도구 권한은 catalog와 registry로 명시적으로 제한합니다.
- Grounding 저장소가 비어 있거나 조회에 실패하면 UI와 로그에 그 상태를 표시하고 실행을 계속하지 않습니다.
- Outlook 기능은 초안만 생성합니다. 사람이 수신자·제목·본문을 확인하고 승인하더라도, 별도 인증과 `ALLOW_WRITE_TOOLS=true`가 모두 있어야 외부 전송이 가능합니다.

</details>

---

<details>
<summary><strong>✅ 이 단계의 완료 기준</strong></summary>

각 Agent 패턴이 제어 흐름, 도구 권한, 조직 경계를 어떻게 다르게 다루는지 설명할 수 있어야 합니다. 테스트와 실행 명령은 [루트 README](../README.md)를 따릅니다.

</details>
