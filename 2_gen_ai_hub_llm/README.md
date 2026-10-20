# 02 · Gen AI Hub LLM

LLM 호출을 Prompt·Embedding·Reranking·비즈니스 임베딩으로 확장하고, 모델 결과를 자동 결정이 아닌 **근거 있는 추천**으로 해석하는 단계입니다.

> 공통 설치와 JupyterLab 실행은 [루트 README](../README.md)에서 진행합니다. 이 문서는 각 노트북의 학습 목표와 결과 해석에 집중합니다.

---

<details>
<summary><strong>🔧 시작 전 확인</strong></summary>

| 실습 범위 | 필요한 준비 |
| --- | --- |
| 공통 LLM 호출 | AI Core 인증 정보와 `LLM_MODEL` |
| Embedding | 배포된 embedding 모델명 `EMBED_MODEL` |
| Reranking | `RERANK_MODEL` 또는 호환 endpoint 정보 |

1단계에서 AI Core 연결과 기본 LLM 호출을 먼저 확인한 뒤 진행하세요.

</details>

---

<details>
<summary><strong>📓 노트북 안내</strong></summary>

| 노트북 | 무엇을 하나요? | 확인할 결과 |
| --- | --- | --- |
| [01_prompt_and_model.ipynb](notebooks/01_prompt_and_model.ipynb) | system prompt와 user prompt를 바꾸며 응답을 비교합니다. | 지시 조건이 응답 형식·톤·근거 제시에 미치는 영향을 설명합니다. |
| [02_embeddings.ipynb](notebooks/02_embeddings.ipynb) | 텍스트를 벡터로 변환하고 cosine similarity를 계산합니다. | 유사도 수치와 문장 의미가 항상 일치하지 않을 수 있음을 확인합니다. |
| [03_reranker_decision_model.ipynb](notebooks/03_reranker_decision_model.ipynb) | 정책 후보를 다시 정렬하고 score·margin을 비교합니다. | 낮은 신뢰도 또는 작은 margin을 `manual-review`로 처리하는 기준을 이해합니다. |
| [04_business_embedding_cluster.ipynb](notebooks/04_business_embedding_cluster.ipynb) | 비즈니스 문의를 군집화하고 label-aware adapter를 적용합니다. | 라벨별 재가중이 도메인 분류 관점에 주는 영향을 확인합니다. |

각 노트북은 이전 결과를 전제로 하지 않지만, Prompt부터 Embedding, Reranking, 도메인 적용 순으로 보면 결과를 비교하기 쉽습니다.

</details>

---

<details>
<summary><strong>🔐 해석 원칙과 안전 경계</strong></summary>

- 유사도와 reranker score만으로 승인·반려를 자동화하지 않습니다.
- 낮은 점수와 작은 score 차이는 사람 검토가 필요한 신호입니다.
- `BusinessEmbeddingAdapter`는 hosted 모델을 fine-tune하지 않고, 동결된 벡터를 라벨별 분산으로 재가중합니다.
- 예제의 결과는 업무 실행이 아니라 추천이며, 운영 적용 전에는 검증 데이터와 사람 승인 단계를 둡니다.

</details>

---

<details>
<summary><strong>✅ 이 단계의 완료 기준</strong></summary>

Prompt 조건, similarity, reranker score가 각각 무엇을 의미하는지 구분해 설명할 수 있어야 합니다. 특히 불확실한 결과를 자동 결정으로 바꾸지 않고 검토 대상으로 넘기는 흐름을 확인하세요. 테스트와 실행 명령은 [루트 README](../README.md)를 따릅니다.

</details>
