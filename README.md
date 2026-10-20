# Gen AI Hub 핸즈온: 1~4단계

SAP BTP AI Core / Gen AI Hub를 이용해 모델 연결부터 LLM, 서비스, Agent 협업까지 단계적으로 실습하는 저장소입니다. 이 문서는 **1~4단계 핸즈온**의 공통 출발점입니다. 각 단계는 앞 단계의 환경을 재사용하지만, Python core와 노트북은 각각 독립적으로 확인할 수 있습니다.

## 학습 로드맵

| 순서 | 폴더 | 학습 내용 | 완료 기준 |
| --- | --- | --- | --- |
| 1 | [Gen AI Hub와 BTP AI Core](1_gen_ai_hub/) | AI Core 인증, 배포 모델 확인, OpenAI-compatible 호출 | 비밀값을 노출하지 않고 환경과 deployment 상태를 확인한다. |
| 2 | [Gen AI Hub LLM](2_gen_ai_hub_llm/) | Prompt, embedding, reranking, 비즈니스 임베딩 | 입력과 근거에 따라 모델 결과·유사도·추천을 해석한다. |
| 3 | [Gen AI Hub Services](3_gen_ai_hub_services/) | Orchestration, document grounding, Object Storage 연동 | 등록된 서비스와 grounding 근거를 분리해 확인한다. |
| 4 | [Agent Patterns](4_agent_patterns/) | Workflow, tool calling, A2A, Advanced A2A + Codex App Server | 문제에 맞는 Agent 협업 방식과 안전 경계를 설명한다. |

권장 순서는 1 → 2 → 3 → 4입니다. 4단계의 03·04 노트북은 로컬 A2A Agent 서버를 별도 터미널에서 실행해야 합니다.

## 사전 준비와 설치

- Python 3.11 이상
- SAP BTP AI Core service key 및 실행 중인 LLM deployment
- Git과 인터넷 연결

이 저장소의 의존성 기준은 루트 [requirements.txt](requirements.txt) 하나입니다. 폴더별 requirements 파일은 만들지 않습니다. 저장소 루트에서 운영체제에 맞는 한 줄을 실행하세요.

**macOS/Linux**

```bash
python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip -r requirements.txt
```

**Windows PowerShell**

```powershell
py -m venv .venv && .\.venv\Scripts\python.exe -m pip install --upgrade pip -r requirements.txt
```

설치 후 환경 파일을 만들고 service key를 채웁니다. `.env`는 Git에 추가하지 않습니다.

```bash
cp .env.example .env
```

Windows PowerShell에서는 `Copy-Item .env.example .env`를 사용합니다.

### `.env` 설정

1~4 공통으로 아래 AI Core 항목을 설정합니다.

```dotenv
AICORE_BASE_URL=
AICORE_AUTH_URL=
AICORE_CLIENT_ID=
AICORE_CLIENT_SECRET=
AICORE_RESOURCE_GROUP=default
LLM_MODEL=
```

필요한 실습에서만 다음 선택 항목을 추가합니다. 값의 전체 목록과 설명은 [.env.example](.env.example)을 기준으로 합니다.

| 기능 | 환경변수 | 사용 단계 |
| --- | --- | --- |
| 임베딩·reranker | `EMBED_MODEL`, `RERANK_MODEL` 또는 `RERANK_ENDPOINT`, `RERANK_API_KEY` | 2, 4 |
| Grounding | `GROUNDING_REPOSITORY_ID`, 선택적으로 `AICORE_ORCHESTRATION_DEPLOYMENT_URL` | 3, 4 |
| Object Storage | `OBJECT_STORAGE_ENDPOINT`, `OBJECT_STORAGE_ACCESS_KEY_ID`, `OBJECT_STORAGE_SECRET_ACCESS_KEY`, `OBJECT_STORAGE_BUCKET` | 3 |
| LiteLLM Proxy | `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LITELLM_MODEL` | 1 (선택) |
| Outlook 발송 | `ALLOW_WRITE_TOOLS=true`와 Graph/EAI 관련 값 | 4 (선택, 명시적 사람 승인 필요) |

## Jupyter 실행

루트에서 JupyterLab을 실행하고 각 단계의 `notebooks/`를 순서대로 엽니다.

```bash
.venv/bin/python -m jupyterlab
```

Windows PowerShell에서는 `.\.venv\Scripts\python.exe -m jupyterlab`을 사용합니다. 노트북은 core 함수를 호출해 결과와 trace를 보여 주며, 실제 로직은 각 단계의 `src/`에 있습니다.

## 단계별 빠른 확인

Jupyter를 열기 전에 CLI 도움말과 환경 상태를 확인할 수 있습니다.

```bash
.venv/bin/python 1_gen_ai_hub/main.py status
.venv/bin/python 2_gen_ai_hub_llm/main.py --help
.venv/bin/python 3_gen_ai_hub_services/main.py --help
.venv/bin/python 4_agent_patterns/main.py --help
```

각 단계별 실행 순서·성공 기준·선택 기능은 해당 폴더의 README를 따릅니다.

## 안전 경계

- `.env`, service key, API key, access key를 노트북 출력·로그·Git에 남기지 않습니다.
- 1~4의 기본 예제와 fixture 기반 Tool은 읽기 전용입니다.
- 4단계의 Outlook 발송은 사람이 UI에서 내용을 확인하고 승인한 경우에만, 별도 인증과 `ALLOW_WRITE_TOOLS=true`가 모두 설정되어야 실행됩니다.
- Grounding과 Object Storage에 넣는 문서는 실습 권한 범위의 데이터만 사용합니다.

## 검증

```bash
.venv/bin/python -m unittest discover -s 1_gen_ai_hub/tests -v
.venv/bin/python -m unittest discover -s 2_gen_ai_hub_llm/tests -v
.venv/bin/python -m unittest discover -s 3_gen_ai_hub_services/tests -v
.venv/bin/python -m unittest discover -s 4_agent_patterns/tests -v
```

5~7단계의 Harness 및 업무 캡스톤은 이 1~4단계 핸즈온 이후의 확장 실습입니다.
