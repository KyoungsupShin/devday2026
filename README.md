# Gen AI Hub Hands-on

SAP BTP AI Core와 Gen AI Hub의 LLM, Grounding, Agent 협업을 실습하는 저장소입니다.

> 각 노트북은 화면과 trace를 보여 주고, 실제 로직은 해당 단계의 `src/`에 있습니다.

### 🎬 Agent Patterns 미리보기

<strong>01 · 병렬 Agent Workflow</strong><br>
<img src="4_agent_patterns/assets/thumbnails/gifs/01_agent_workflow.gif" alt="병렬 Agent Workflow 미리보기" width="100%"><br>
병렬 실행 결과를 확인합니다.

<br>

<strong>02 · Agent-to-Agent 협업</strong><br>
<img src="4_agent_patterns/assets/thumbnails/gifs/03_agent_to_agent.gif" alt="Agent-to-Agent 협업 미리보기" width="100%"><br>
부서 간 협업 결과를 확인합니다.

<br>

<strong>03 · Agent-to-Agent 협업 with Expanding</strong><br>
<img src="4_agent_patterns/assets/thumbnails/gifs/04_agent_to_agent_advanced.gif" alt="Advanced Agent-to-Agent 협업과 Harness Labs 개선안 미리보기" width="100%"><br>
협업 결과와 개선 제안을 확인합니다.

---
<details>
<summary><strong>🧭 학습 흐름</strong></summary>


01부터 04까지 순서대로 진행합니다.

| 순서 | 아젠다 | 핵심 실습 | 완료 기준 |
| --- | --- | --- | --- |
| **01** | [Gen AI Hub와 BTP AI Core](1_gen_ai_hub/) | AI Core 인증, deployment 조회 | 비밀값 노출 없이 환경과 실행 중인 모델을 확인한다. |
| **02** | [Gen AI Hub LLM](2_gen_ai_hub_llm/) | Prompt, embedding, reranking | 모델 응답·유사도·추천 score를 근거와 함께 해석한다. |
| **03** | [Gen AI Hub Services](3_gen_ai_hub_services/) | Orchestration, masking, document grounding, Object Storage | 서비스 응답과 grounding 문서 근거를 구분해 확인한다. |
| **04** | [Agent Patterns](4_agent_patterns/) | Workflow, tool calling, A2A, Advanced A2A | 제어 흐름·도구 권한·조직 경계에 맞는 협업 방식을 비교한다. |

04의 A2A 실습은 별도 터미널에서 로컬 Agent 서버를 실행해야 합니다.

</details>

---
<details>
<summary><strong>🚀 시작하기</strong></summary>


### 1. 설치

저장소 루트에서 가상환경과 공통 의존성을 설치합니다.

**macOS / Linux**

```bash
python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip -r requirements.txt
```

**Windows PowerShell**

```powershell
py -m venv .venv && .\.venv\Scripts\python.exe -m pip install --upgrade pip -r requirements.txt
```

설치가 끝나면 아래 명령으로 Python과 주요 CLI 진입점을 확인합니다.

```bash
.venv/bin/python --version
.venv/bin/python 1_gen_ai_hub/main.py --help
.venv/bin/python 2_gen_ai_hub_llm/main.py --help
.venv/bin/python 3_gen_ai_hub_services/main.py --help
.venv/bin/python 4_agent_patterns/main.py --help
```

Windows PowerShell에서는 각 `.venv/bin/python`을 `./.venv/Scripts/python.exe`로 바꿉니다.

### 2. 환경 설정

`.env.example`을 복사한 뒤 AI Core service key와 모델명을 채웁니다. `.env`는 절대 Git에 커밋하지 않습니다.

```bash
cp .env.example .env
```

```powershell
Copy-Item .env.example .env
```

```dotenv
AICORE_BASE_URL=
AICORE_AUTH_URL=
AICORE_CLIENT_ID=
AICORE_CLIENT_SECRET=
AICORE_RESOURCE_GROUP=default
LLM_MODEL=
```

### 3. JupyterLab 실행

```bash
.venv/bin/python -m jupyterlab
```

Windows PowerShell에서는 `.venv/bin/python` 대신 `.\.venv\Scripts\python.exe`를 사용합니다.

### AI에게 설치 맡기기

Codex 또는 Claude를 저장소 루트에서 열고 아래 프롬프트를 그대로 붙여 넣으세요. 프롬프트는 `.env`의 비밀값을 생성·출력·커밋하지 않고, 설치와 로컬 검증까지만 수행하도록 제한합니다.

```text
현재 저장소 루트에서 이 프로젝트의 Python 실습 환경을 설정해 주세요.

1. README.md, requirements.txt, .env.example, .gitignore를 먼저 읽고 현재 OS와 기존 환경을 확인하세요.
2. 기존 .venv가 없으면 Python 3로 .venv를 만들고, 그 가상환경의 Python으로 pip를 최신화한 뒤 requirements.txt를 설치하세요. 이미 .venv가 있으면 재사용하세요.
3. .env가 없을 때만 .env.example을 .env로 복사하세요. AI Core 자격 증명, API 키, 토큰, 비밀값은 추측하거나 생성하거나 출력하지 마세요.
4. 가상환경의 Python으로 1_gen_ai_hub, 2_gen_ai_hub_llm, 3_gen_ai_hub_services, 4_agent_patterns의 main.py --help를 실행해 설치를 검증하세요. 외부 AI Core 호출, JupyterLab 서버 실행, Git 커밋은 하지 마세요.
5. 완료 후 실행한 명령, 검증 결과, 사용자가 .env에 직접 입력해야 할 항목과 막힌 원인만 간결하게 보고하세요. 추적 대상 파일은 수정하지 마세요.
```

</details>

---

<details>
<summary><strong>📚 아젠다별 실습</strong></summary>


필요한 아젠다를 펼쳐 상세 노트북과 실행 방법을 확인하세요.

<details>
<summary><strong>01 · Gen AI Hub와 BTP AI Core</strong> — 환경과 모델 연결</summary>


| 노트북 | 실습 내용 | 확인 포인트 |
| --- | --- | --- |
| `00_learning_roadmap.ipynb` | 전체 학습 흐름과 사전 준비 | 01~04 단계의 연결 관계를 이해한다. |
| `01_environment.ipynb` | 설정 누락과 RUNNING deployment 확인 | 비밀값 없이 인증·모델 상태를 점검한다. |

```bash
.venv/bin/python 1_gen_ai_hub/main.py status
.venv/bin/python 1_gen_ai_hub/main.py deployments
```

</details>

---

<details>
<summary><strong>02 · Gen AI Hub LLM</strong> — Prompt·Embedding·Reranking</summary>


| 노트북 | 실습 내용 | 확인 포인트 |
| --- | --- | --- |
| `01_prompt_and_model.ipynb` | 프롬프트와 모델 응답 비교 | Prompt 조건에 따른 응답을 확인한다. |
| `02_embeddings_model.ipynb` | embedding과 cosine similarity | 문장 간 유사도를 수치와 맥락으로 함께 해석한다. |
| `03_reranker_model.ipynb` | 정책 후보 reranking | 낮은 score 또는 작은 margin은 사람 검토로 보낸다. |

필요한 경우 `.env`에 `EMBED_MODEL`과 `RERANK_MODEL`을 설정합니다. score와 margin은 자동 승인·반려가 아닌 사람 검토 우선순위를 정하는 근거로만 사용합니다.

</details>

---

<details>
<summary><strong>03 · Gen AI Hub Services</strong> — Orchestration·Grounding</summary>


| 노트북 | 실습 내용 | 확인 포인트 |
| --- | --- | --- |
| `01_orchestration.ipynb` | Orchestration 호출, prompt templating, 필터·마스킹 | 등록된 서비스를 조회하고 호출 결과를 확인한다. |
| `02_grounding.ipynb` | 문서 chunk 기반 질의 | 답변과 함께 참조한 문서 근거를 확인한다. |
| `03_rpt_risk_classification.ipynb` | SAP RPT 교육용 holdout 평가·단건 분류 | feature·label만 전달하고, 지표·감사 집계를 사람 검토용으로 확인한다. |
| `04_rpt_decision.ipynb` | SAP RPT Decision API 기반 문의 분류 | 읽기 전용 API 호출의 분류 결과와 판단 근거를 확인한다. |

Grounding에는 `GROUNDING_REPOSITORY_ID`가 필요합니다. Object Storage 연계는 선택 사항이며, 원본 문서는 Storage에 보관되고 질의는 인덱싱된 vector chunk를 근거로 수행합니다. RPT 실습은 RUNNING foundation-model deployment에 읽기 전용 예측만 요청하며, 학습 실행·deployment 생성·자동 신용 의사결정은 수행하지 않습니다.

```bash
.venv/bin/python 3_gen_ai_hub_services/main.py rpt-evaluate
```

</details>

---

<details>
<summary><strong>04 · Agent Patterns</strong> — Workflow·Tool Calling·A2A</summary>

<p align="right">
  <a href="4_agent_patterns/notebooks/04_agent_to_agent_advanced.ipynb">
    <img src="4_agent_patterns/assets/thumbnails/04_agent_to_agent_advanced_workflow.svg" alt="Advanced A2A workflow" width="460">
  </a>
</p>

| 노트북 | 협업 패턴 | 확인 포인트 |
| --- | --- | --- |
| `01_agent_workflow.ipynb` | 고정 전이 workflow | 코드가 제어하는 LLM workflow와 route 선택을 확인한다. |
| `02_agent_loop_mcp.ipynb` | Tool calling loop | 도구 호출과 재관찰 흐름을 확인한다. |
| `03_agent_to_agent.ipynb` | A2A | Message·Task·Artifact 기반 handoff를 확인한다. |
| `04_agent_to_agent_advanced.ipynb` | Advanced A2A | Team 협업과 Codex SQL Agent를 확인한다. |
| `05_build_your_harness.ipynb` | Build your harness | SAP BTP 기반 Harness의 실행·도구·Agent·거버넌스 아키텍처와 구현 순서를 설계한다. |

04 Advanced A2A는 실행 trace를 Harness Labs에서 분석해 개선안을 제시하고, 사람이 선택한 revision만 세션의 runtime overlay로 반영합니다. 반영 전·후의 실행 흐름은 비교할 수 있으며 원본 Prompt·Tool·SOP는 변경하지 않습니다.

03·04를 실행하기 전에 JupyterLab과 별도의 터미널에서 아래 서버를 시작합니다.

| 노트북 | 실행 명령 | 포트 |
| --- | --- | --- |
| 03 `agent_to_agent` | `.venv/bin/python 4_agent_patterns/main.py fnb-a2a-local` | 9111~9122 |
| 04 `agent_to_agent_advanced` | `.venv/bin/python 4_agent_patterns/main.py fnb-a2a-advanced-local` | 9211~9223 |

</details>

</details>

---

<details>
<summary><strong>🔐 환경변수와 안전 경계</strong></summary>


| 기능 | 추가 환경변수 | 사용 단계 |
| --- | --- | --- |
| 임베딩·reranker | `EMBED_MODEL`, `RERANK_MODEL` | 02, 04 |
| SAP RPT risk classification | `RPT_MODEL`, 선택적으로 `AICORE_RPT_DEPLOYMENT_ID` | 03 |
| SAP RPT Decision API | `SAP_RPT_API_KEY` | 03 |
| Grounding | `GROUNDING_REPOSITORY_ID`, 선택적으로 `AICORE_ORCHESTRATION_DEPLOYMENT_URL` | 03, 04 |
| Object Storage | `OBJECT_STORAGE_ENDPOINT`, `OBJECT_STORAGE_ACCESS_KEY_ID`, `OBJECT_STORAGE_SECRET_ACCESS_KEY`, `OBJECT_STORAGE_BUCKET` | 03 |
| Outlook 발송 | `ALLOW_WRITE_TOOLS=true` 및 연동 설정 | 04 (선택) |

- service key, API key, access key는 노트북 출력·로그·Git에 남기지 않습니다.
- 기본 예제와 fixture 기반 Tool은 읽기 전용입니다.
- SAP RPT 예측에는 교육용 feature·label만 전달하며, 식별자와 감사 속성은 로컬 검토 범위에 둡니다.
- Outlook 발송은 UI에서 사람이 내용을 확인·승인하고, 별도 인증과 `ALLOW_WRITE_TOOLS=true`가 모두 설정된 경우에만 가능합니다.
- Grounding과 Object Storage에는 실습 권한 범위의 문서만 사용합니다.

</details>

---
