# 1. Gen AI Hub와 BTP AI Core

## Core 직접 검증

노트북을 이관하기 전에는 아래 명령으로 환경 core를 확인합니다.

    python3 1_gen_ai_hub/main.py status
    python3 -m unittest discover -s 1_gen_ai_hub/tests -v

AI Core 인증이 준비된 경우에만 RUNNING deployment를 조회합니다.

    python3 1_gen_ai_hub/main.py deployments

AI Core service key를 `.env`로 매핑하고 XSUAA 인증, RUNNING deployment 조회, Gen AI Hub SDK 연결을 확인합니다.

- Jupyter:
  - `notebooks/00_environment.ipynb` — AI Core 환경과 RUNNING deployment 확인
  - `notebooks/01_openai_compatible_chat.ipynb` — gpt-5.6-luna 채팅 및 선택적 LiteLLM Proxy 호출

성공 기준은 비밀값을 출력하지 않은 채 모델 및 orchestration deployment를 조회하는 것입니다.

## LiteLLM Proxy를 OpenAI-compatible하게 연결하기

LiteLLM Proxy URL(/v1 포함)과 gateway에서 발급한 AI Secret Key를 루트 .env에 설정하면, 공식 OpenAI SDK 문법으로 LiteLLM을 호출할 수 있습니다. 키는 출력하거나 Git에 추가하지 않습니다. AI_SECRET_KEY는 기존 환경변수 호환용 별칭이고 새 설정에는 LITELLM_API_KEY를 권장합니다.

~~~dotenv
LITELLM_BASE_URL=https://your-litellm.example/v1
LITELLM_API_KEY=your-ai-secret-key
LITELLM_MODEL=your-proxy-model-name
~~~

설정과 실제 호출은 다음으로 확인합니다.

~~~bash
python3 1_gen_ai_hub/main.py litellm-status
python3 1_gen_ai_hub/main.py litellm-chat "한국어로 한 문장만 답해줘."
~~~

애플리케이션 코드에서는 src/litellm_adapter.py의 openai_client() 또는 chat_completion()을 사용합니다. openai_client()가 OpenAI(base_url=LITELLM_BASE_URL, api_key=LITELLM_API_KEY)를 만들어 주므로 호출 형식은 OpenAI Chat Completions와 같습니다.
