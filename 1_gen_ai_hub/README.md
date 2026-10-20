# 1. Gen AI Hub와 BTP AI Core

AI Core service key를 로컬 `.env`에 연결하고, SDK가 사용할 인증 정보와 실행 중인 deployment를 안전하게 확인합니다. 이 단계가 이후 LLM·서비스·Agent 실습의 공통 환경입니다.

## 시작 전 준비

공통 설치와 `.env` 생성은 [루트 README](../README.md#사전-준비와-설치)를 먼저 따르세요. 설치가 아직이면 저장소 루트에서 운영체제에 맞는 한 줄을 실행합니다.

**macOS/Linux**

```bash
python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip -r requirements.txt
```

**Windows PowerShell**

```powershell
py -m venv .venv && .\.venv\Scripts\python.exe -m pip install --upgrade pip -r requirements.txt
```

루트 `.env`에 `AICORE_BASE_URL`, `AICORE_AUTH_URL`, `AICORE_CLIENT_ID`, `AICORE_CLIENT_SECRET`, `AICORE_RESOURCE_GROUP`, `LLM_MODEL`을 설정합니다. 실제 비밀값을 출력하거나 Git에 커밋하지 마세요.

## 실습 순서

1. [notebooks/00_learning_roadmap.ipynb](notebooks/00_learning_roadmap.ipynb)에서 전체 1~4단계 학습 흐름과 사전 준비를 확인합니다.
2. [notebooks/00_environment.ipynb](notebooks/00_environment.ipynb)에서 설정 누락 여부와 RUNNING deployment를 확인합니다.
3. [notebooks/01_openai_compatible_chat.ipynb](notebooks/01_openai_compatible_chat.ipynb)에서 AI Core LLM 호출을 확인합니다.
4. 필요할 때만 LiteLLM Proxy를 OpenAI SDK 문법으로 호출합니다.

CLI로 노트북 시작 전 환경을 점검할 수 있습니다.

```bash
.venv/bin/python 1_gen_ai_hub/main.py status
.venv/bin/python 1_gen_ai_hub/main.py deployments
```

성공 기준은 비밀값 없이 환경 상태를 확인하고, AI Core 인증이 준비된 경우 RUNNING 모델 또는 orchestration deployment를 조회하는 것입니다.

## 선택: LiteLLM Proxy

루트 `.env`에 아래 값을 설정하면 OpenAI-compatible endpoint를 사용할 수 있습니다. `AI_SECRET_KEY`는 기존 설정 호환용 별칭이며, 새 설정은 `LITELLM_API_KEY`를 권장합니다.

```dotenv
LITELLM_BASE_URL=https://your-litellm.example/v1
LITELLM_API_KEY=your-ai-secret-key
LITELLM_MODEL=your-proxy-model-name
```

```bash
.venv/bin/python 1_gen_ai_hub/main.py litellm-status
.venv/bin/python 1_gen_ai_hub/main.py litellm-chat "한국어로 한 문장만 답해줘."
```

애플리케이션 코드에서는 `src/litellm_adapter.py`의 `openai_client()` 또는 `chat_completion()`을 사용합니다.

## 확인

```bash
.venv/bin/python -m unittest discover -s 1_gen_ai_hub/tests -v
```
