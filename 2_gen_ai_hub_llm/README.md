# 02 · Gen AI Hub LLM

Prompt, Embedding, Reranking 결과를 비교하는 단계입니다.

> 공통 설치와 JupyterLab 실행은 [루트 README](../README.md)에서 진행합니다. 이 문서는 각 노트북의 학습 목표와 결과 해석에 집중합니다.

---

<details>
<summary><strong>🔧 시작 전 확인</strong></summary>

| 실습 범위 | 필요한 준비 |
| --- | --- |
| 공통 LLM 호출 | AI Core 인증 정보와 `LLM_MODEL` |
| Embedding | 배포된 embedding 모델명 `EMBED_MODEL` |
| Reranking | `RERANK_MODEL` 또는 호환 endpoint 정보 |

1단계의 AI Core 연결을 먼저 확인하세요.

</details>

---

<details>
<summary><strong>📓 노트북 안내</strong></summary>

| 노트북 | 무엇을 하나요? | 확인할 결과 |
| --- | --- | --- |
| [01_prompt_and_model.ipynb](notebooks/01_prompt_and_model.ipynb) | system prompt와 user prompt를 바꾸며 응답을 비교합니다. | 지시 조건이 응답 형식·톤·근거 제시에 미치는 영향을 설명합니다. |
| [02_embeddings.ipynb](notebooks/02_embeddings.ipynb) | 텍스트를 벡터로 변환하고 cosine similarity를 계산합니다. | 유사도 수치와 문장 의미가 항상 일치하지 않을 수 있음을 확인합니다. |
| [03_embedding_advanced.ipynb](notebooks/03_embedding_advanced.ipynb) | 비즈니스 문의를 군집화하고 label-aware adapter를 적용합니다. | 라벨별 재가중이 도메인 분류 관점에 주는 영향을 확인합니다. |
| [04_reranker_decision_model.ipynb](notebooks/04_reranker_decision_model.ipynb) | 교육용 정책 후보를 다시 정렬하고 score·margin을 비교합니다. | 낮은 신뢰도 또는 작은 margin을 `manual-review`로 처리하는 기준과 개선안을 이해합니다. |

노트북은 Prompt, Embedding, Reranking 순으로 진행하세요.

</details>

---

<details>
<summary><strong>🔐 해석 원칙과 안전 경계</strong></summary>

- 점수는 참고값이며, 불확실한 결과는 사람이 검토합니다.

</details>

---

<details>
<summary><strong>✅ 이 단계의 완료 기준</strong></summary>

Prompt, similarity, reranker score의 차이를 확인합니다. 테스트와 실행 명령은 [루트 README](../README.md)를 따릅니다.

</details>
