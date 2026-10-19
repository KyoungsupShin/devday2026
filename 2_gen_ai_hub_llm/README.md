# 2. Gen AI Hub LLM

LLM 호출과 prompt 설계, embedding을 독립적으로 시험합니다.

- `notebooks/01_prompt_and_model.ipynb`: system/user prompt와 모델 응답 비교
- `notebooks/02_embeddings.ipynb`: embedding과 코사인 유사도
  - 실행 전 `.env`의 `EMBED_MODEL`을 현재 AI Core에 배포된 임베딩 모델명으로 설정합니다.
- `notebooks/04_business_embedding_cluster.ipynb`: 비즈니스 문의를 임베딩해 운영 큐 후보 cluster를 만들고, 라벨 사례로 domain adapter를 학습합니다.
  - hosted embedding 모델의 가중치는 이 프로젝트에서 직접 fine-tune하지 않습니다. 대신 `src/business_embedding/lab_core.py`의 `BusinessEmbeddingAdapter`가 동결된 벡터를 라벨별 분산에 따라 재가중하는 supervised metric-learning adapter를 학습합니다.
  - 이 adapter는 학습 데이터와 분리한 평가 데이터에서 검증해야 하며, 실제 분류/자동화 전에 저신뢰도 fallback과 사람 검토 단계를 연결해야 합니다.
- `notebooks/03_reranker_decision_model.ipynb`: 사례와 정책 후보를 rerank하여 승인/추가 검토/반려 **추천**을 만듭니다.
  - `src/reranker/lab_core.py`는 점수, 1·2위 간 margin, 사람 검토 필요 여부를 함께 반환합니다. 근거가 약하거나 후보가 비슷하면 항상 `manual-review`로 보수적으로 처리합니다.
  - AI Core를 사용할 때는 루트 `.env`의 `RERANK_MODEL`에 배포 모델명을 설정합니다. 노트북에서 별도 설정할 필요가 없습니다.
  - `RERANK_ENDPOINT`, `RERANK_API_KEY`도 설정하면 LiteLLM/Cohere 호환 `/rerank` endpoint를 사용합니다.
  - 예제의 승인/반려는 실제 업무 실행이 아닌 추천입니다. 운영 전에는 승인된 정책 문구, 라벨된 평가 데이터, 담당자 승인 단계를 연결해야 합니다.

다음 확장 실습은 structured output과 이미지 입력을 이 폴더에 추가하는 방식입니다.
