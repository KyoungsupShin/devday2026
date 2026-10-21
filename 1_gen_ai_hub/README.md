# 01 · Gen AI Hub와 BTP AI Core

AI Core service key를 로컬 환경에 연결하고, 이후 실습에서 사용할 인증·deployment·LLM 호출 경로를 안전하게 확인하는 출발 단계입니다.

> 설치, 환경 파일 생성, JupyterLab 실행은 [루트 README](../README.md)에서 한 번만 진행하세요. 이 문서는 노트북에서 무엇을 확인하는지에 집중합니다.

---

<details>
<summary><strong>🔧 시작 전 확인</strong></summary>

| 확인 항목 | 내용 |
| --- | --- |
| AI Core 연결 | 루트 `.env`에 AI Core 인증 정보와 `LLM_MODEL`이 준비되어 있어야 합니다. |
| 비밀정보 보호 | service key와 API key는 출력·노트북 결과·Git에 남기지 않습니다. |
| 실행 환경 | 실습은 루트에서 준비한 Python 가상환경과 JupyterLab을 함께 사용합니다. |

</details>

---

<details>
<summary><strong>📓 노트북 안내</strong></summary>

| 노트북 | 무엇을 하나요? | 확인할 결과 |
| --- | --- | --- |
| [00_learning_roadmap.ipynb](notebooks/00_learning_roadmap.ipynb) | 전체 01~04 학습 흐름과 각 단계의 역할을 소개합니다. | 모델 연결부터 Agent 협업까지의 선후 관계를 설명할 수 있습니다. |
| [01_environment.ipynb](notebooks/01_environment.ipynb) | 카드형 설정 UI에서 연결 정보를 점검하고, 필요할 때만 로컬 `.env`에 저장한 뒤 실행 가능한 AI Core deployment를 조회합니다. | client secret을 다시 표시하지 않고 인증 준비 상태와 RUNNING deployment 상태를 확인합니다. |
| [02_openai_compatible_chat.ipynb](notebooks/02_openai_compatible_chat.ipynb) | AI Core의 LLM을 OpenAI-compatible 방식으로 호출합니다. | 모델명·입력 메시지·응답의 관계를 확인하고 기본 채팅 호출을 성공시킵니다. |

노트북은 위 순서대로 실행하세요. 설정 UI에서 빈 값은 기존 `.env` 값을 유지하며, client secret은 화면에 재표시하지 않습니다. 환경 상태가 준비되지 않은 경우에는 호출을 계속 진행하기보다 설정을 먼저 보완합니다.

</details>

---

<details>
<summary><strong>🧩 선택 기능: LiteLLM Proxy</strong></summary>

OpenAI SDK 형식의 별도 endpoint를 사용해야 할 때만 LiteLLM Proxy를 연결합니다. 이 기능은 기본 AI Core 실습에 필수는 아니며, Proxy 주소·API key·모델명이 준비된 경우에만 상태와 채팅 호출을 확인합니다.

</details>

---

<details>
<summary><strong>✅ 이 단계의 완료 기준</strong></summary>

- 환경 상태와 deployment 조회 결과를 비밀값 없이 설명할 수 있습니다.
- 실행 가능한 모델을 확인하고 기본 LLM 호출 결과를 해석할 수 있습니다.
- 설정 또는 deployment 조회가 실패하면 근거 없는 응답으로 대체하지 않고 원인을 확인합니다.

테스트와 실행 명령은 [루트 README](../README.md)의 검증 안내를 따르세요.

</details>
