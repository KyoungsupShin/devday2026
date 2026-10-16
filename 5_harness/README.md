# 5. Harness

외부 Harness 애플리케이션의 프롬프트, HANA override, reranker와 specialist routing 개념을 Jupyter에서 분리해 검증합니다.

| 노트북 | 내용 |
| --- | --- |
| `notebooks/01_reranker_routing.ipynb` | Chat/Work 및 specialist 후보 reranking |
| `notebooks/02_deepagents_optional.ipynb` | Harness 프롬프트 카탈로그, HANA snapshot, DeepAgents 연결 조건 |
| `notebooks/03_delegation_a2a.ipynb` | delegation, hands-off, 실행 가능한 in-memory A2A message trace와 검증 |

`prompts/`에는 원본 Harness 기본 프롬프트 7개가 있고, `fixtures/harness_prompt_overrides.json`에는 `SAP_HARNESS_PROMPTS`에서 읽기 전용으로 내보낸 override snapshot이 있습니다. 런타임 규칙은 Harness와 동일하게 **HANA override 우선, 기본 파일 후순위**입니다.

`src/reranker.py`는 기본으로 설명 가능한 로컬 lexical reranker를 사용합니다. 실제 LiteLLM/Cohere reranker는 `.env`의 `RERANK_ENDPOINT`, `RERANK_API_KEY`, `RERANK_MODEL`을 설정한 경우에만 호출합니다.

DeepAgents 실습은 선택 사항입니다. 다음을 별도 설치하고 외부 LiteLLM/MCP Registry 권한이 준비된 뒤에만 연결합니다.

```bash
python3 -m pip install -r 5_harness/requirements-deepagents.txt
```

설계 문서는 `docs/캡스톤-설계도.md`에 있습니다.

`03_delegation_a2a.ipynb`는 외부 endpoint를 호출하지 않습니다. 대신 `src/delegation_a2a.py`의 message bus가 orchestrator → researcher → analyst writer → user의 실제 handler dispatch를 수행하고, 경로·correlation ID·읽기 전용 제약을 검증합니다. 원격 A2A transport를 연결할 때도 같은 envelope와 권한 경계를 유지하세요.
