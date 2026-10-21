# 01 · Gen AI Hub와 BTP AI Core

AI Core 연결과 기본 LLM 호출을 확인하는 단계입니다.

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

노트북은 위 순서대로 실행하세요.

</details>

---

<details>
<summary><strong>🧩 선택 기능: LiteLLM Proxy</strong></summary>

필요할 때만 LiteLLM Proxy를 연결합니다.

</details>

---

<details>
<summary><strong>✅ 이 단계의 완료 기준</strong></summary>

- 실행 가능한 deployment와 기본 LLM 응답을 확인합니다.

테스트와 실행 명령은 [루트 README](../README.md)의 검증 안내를 따르세요.

</details>
