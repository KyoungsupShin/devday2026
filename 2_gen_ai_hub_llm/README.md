# 2. Gen AI Hub LLM

LLM 호출을 프롬프트·임베딩·reranking·비즈니스 임베딩으로 확장하고, 모델 결과를 업무 판단의 **추천**으로 안전하게 해석하는 단계입니다.

## 시작 전 준비

1단계에서 AI Core 연결을 확인한 뒤 [루트 README](../README.md#사전-준비와-설치)의 공통 설치를 완료하세요. 설치가 아직이면 저장소 루트에서 운영체제에 맞는 한 줄을 실행합니다.

**macOS/Linux**

```bash
python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip -r requirements.txt
```

**Windows PowerShell**

```powershell
py -m venv .venv && .\.venv\Scripts\python.exe -m pip install --upgrade pip -r requirements.txt
```

루트 `.env`에는 기본 AI Core 값과 `LLM_MODEL`이 필요합니다. 임베딩 실습에는 배포된 모델명으로 `EMBED_MODEL`을 설정합니다. Reranker는 `RERANK_MODEL`을 사용하며, 필요하면 `RERANK_ENDPOINT`, `RERANK_API_KEY`로 LiteLLM/Cohere 호환 endpoint를 연결합니다.

## 실습 순서

1. `notebooks/01_prompt_and_model.ipynb` — system/user prompt와 모델 응답을 비교합니다.
2. `notebooks/02_embeddings.ipynb` — embedding과 cosine similarity를 확인합니다.
3. `notebooks/03_reranker_decision_model.ipynb` — 정책 후보를 rerank하고 score·margin·사람 검토 게이트를 해석합니다.
4. `notebooks/04_business_embedding_cluster.ipynb` — 비즈니스 문의 cluster와 label-aware domain adapter를 만듭니다.

CLI는 노트북 없이 core API를 점검하는 보조 수단입니다.

```bash
.venv/bin/python 2_gen_ai_hub_llm/main.py --help
.venv/bin/python 2_gen_ai_hub_llm/main.py prompt "정책 요약을 작성해줘"
```

## 성공 기준과 안전 경계

- Prompt 조건이 응답 형식과 근거 제시에 미치는 영향을 설명할 수 있습니다.
- 유사도와 reranker score만으로 자동 승인하지 않고, 낮은 신뢰도 또는 작은 margin은 `manual-review`로 처리합니다.
- `BusinessEmbeddingAdapter`는 hosted embedding 모델을 fine-tune하지 않고 동결된 벡터를 라벨별 분산으로 재가중합니다. 학습·평가 데이터는 분리합니다.
- 예제의 승인·반려는 실제 업무 실행이 아닌 추천입니다. 운영 자동화 전에는 검증 데이터와 사람 승인 단계를 추가합니다.

## 확인

```bash
.venv/bin/python -m unittest discover -s 2_gen_ai_hub_llm/tests -v
```
