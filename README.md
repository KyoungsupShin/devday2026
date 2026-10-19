# Gen AI Hub 실습 저장소

BTP AI Core / Gen AI Hub를 이용해 모델 연결부터 LLM·임베딩·서비스·Agent·Harness·업무 캡스톤까지 순서대로 실습하는 Python core + Jupyter 실습 저장소입니다. 각 단계는 앞 단계의 결과를 재사용하되, 개별 노트북만으로도 독립적으로 확인할 수 있습니다.

<!-- THUMBNAIL START: 준비된 이미지를 아래 placeholder 전체와 교체하세요. -->

<div align="center">
  <br>
  <strong>🖼️ Repository thumbnail placeholder</strong><br>
  <sub>나중에 대표 이미지를 여기에 넣으세요. 권장 경로: <code>docs/assets/gen-ai-hub-overview.png</code></sub>
  <br><br><br>
</div>

<!-- THUMBNAIL END -->

## 시작하기

```bash
python3 -m pip install --user -r requirements.txt
cp .env.example .env
python3 -m jupyterlab
```

`.env`에는 AI Core service key와 배포 모델명을 설정합니다. 비밀값은 Git에 올리거나 노트북 출력에 남기지 마세요. 첫 실행에서는 1번 환경 노트북에서 RUNNING deployment를 확인한 뒤 순서대로 진행하는 것을 권장합니다.

## 개발 방식: Python core 먼저

기능 변경은 노트북 셀에서 시작하지 않습니다. 각 단계의 src/에 입력·출력 계약이 명확한 순수 Python 함수로 구현하고 테스트를 먼저 갱신한 뒤, 노트북에서는 fixture를 불러 그 공개 함수를 호출해 결과·trace·UI만 보여줍니다.

1. src/에 정책, 계산, 외부 adapter, 실행 entry point를 구현합니다.
2. tests/에서 정상·경계·승인 게이트를 검증합니다.
3. notebooks/는 import → fixture/입력 선택 → 함수 호출 → 결과 표시 순서만 유지합니다.

따라서 로직을 고칠 때는 ipynb가 아니라 해당 src/*.py를 수정합니다. 노트북에서 재사용할 수 있는 함수는 solve_*, run_*, build_*처럼 명시적인 공개 entry point를 제공하고, 노트북에 같은 계산 함수나 정책 상수를 복제하지 않습니다.

## Core 직접 실행

노트북을 열기 전에 각 단계의 core를 터미널에서 확인할 수 있습니다. 아래 main.py는 UI를 만들거나 Jupyter를 실행하지 않습니다.

    python3 2_gen_ai_hub_llm/main.py --help
    python3 3_gen_ai_hub_services/main.py --help
    python3 4_agent_patterns/main.py workflow "재고를 분석해줘"
    python3 5_harness/main.py delegation "재고를 조사해줘"
    python3 6_Business_issue/main.py seizure-aml
    python3 7_Business_Operation_Harness/main.py --help

2, 3, 7의 실제 scenario 실행은 AI Core 인증과 실행 중인 deployment가 필요합니다. 4, 5, 6의 기본 CLI scenario는 로컬 fixture와 mock으로도 검증할 수 있습니다.

## 실습 로드맵

### 1. [Gen AI Hub와 BTP AI Core](1_gen_ai_hub/)

- 목적: AI Core service key를 로컬 환경변수로 연결하고, SDK가 사용할 인증·resource group·deployment 상태를 확인합니다.
- 핵심 실습: XSUAA 인증, RUNNING deployment 조회, 로컬 `.env` 설정 상태 점검
- 시작점: [00_environment.ipynb](1_gen_ai_hub/notebooks/00_environment.ipynb)
- 채팅 실습: [01_openai_compatible_chat.ipynb](1_gen_ai_hub/notebooks/01_openai_compatible_chat.ipynb) — gpt-5.6-luna와 선택적 LiteLLM Proxy 호출
- 확인 결과: 비밀값을 노출하지 않은 채 모델 및 orchestration deployment를 조회합니다.

### 2. [Gen AI Hub LLM](2_gen_ai_hub_llm/)

- 목적: LLM 호출, 프롬프트 설계, 임베딩 기반 검색·분류·결정 추천의 기본 흐름을 만듭니다.
- 주요 노트북:
  - [01_prompt_and_model.ipynb](2_gen_ai_hub_llm/notebooks/01_prompt_and_model.ipynb) — system/user prompt와 모델 응답 비교
  - [02_embeddings.ipynb](2_gen_ai_hub_llm/notebooks/02_embeddings.ipynb) — 벡터와 cosine similarity
  - [03_reranker_decision_model.ipynb](2_gen_ai_hub_llm/notebooks/03_reranker_decision_model.ipynb) — 정책 후보 reranking, margin, 사람 검토 게이트
  - [04_business_embedding_cluster.ipynb](2_gen_ai_hub_llm/notebooks/04_business_embedding_cluster.ipynb) — 업무 문의 clustering과 label-aware embedding adapter
- 산출물: `src/reranker/lab_core.py`, `src/business_embeddings.py`의 재사용 가능한 추천·임베딩 도구
- 주의: 예제의 승인/반려는 상태를 바꾸지 않는 추천이며, 불확실한 사례는 `manual-review`로 처리합니다.

### 3. [Gen AI Hub Services](3_gen_ai_hub_services/)

- 목적: AI Core Orchestration과 grounding 기능을 서비스 수준에서 분리해 실험합니다.
- 주요 노트북:
  - [01_orchestration.ipynb](3_gen_ai_hub_services/notebooks/01_orchestration.ipynb) — prompt templating, 콘텐츠 필터, 데이터 마스킹
  - [02_grounding.ipynb](3_gen_ai_hub_services/notebooks/02_grounding.ipynb) — 문서 grounding 질의
  - [03_my_documents.ipynb](3_gen_ai_hub_services/notebooks/03_my_documents.ipynb) — 개인·공유 문서 저장소 질의
  - [04_memory_chatbot.ipynb](3_gen_ai_hub_services/notebooks/04_memory_chatbot.ipynb) — 대화 history와 memory 전달
- 준비: grounding 실습에는 `.env`의 `GROUNDING_REPOSITORY_ID`가 필요할 수 있습니다.

### 4. [Agent Patterns](4_agent_patterns/)

- 목적: workflow, agent loop, MCP, A2A가 서로 다른 문제를 해결한다는 점을 코드와 trace로 확인합니다.
- 주요 노트북:
  - [01_agent_workflow.ipynb](4_agent_patterns/notebooks/01_agent_workflow.ipynb) — 코드가 전이를 고정한 workflow와 router 분기
  - [02_agent_loop_mcp.ipynb](4_agent_patterns/notebooks/02_agent_loop_mcp.ipynb) — 관찰·도구 호출·재관찰과 승인 게이트
  - [03_agent_to_agent.ipynb](4_agent_patterns/notebooks/03_agent_to_agent.ipynb) — researcher → analyst handoff artifact
- 구성: `src/`에는 노트북별 workflow·agent loop·A2A core와 UI 어댑터가 있습니다.
- 안전성: 기본 mock 도구는 외부 시스템을 변경하지 않습니다.

### 5. [Harness](5_harness/)

- 목적: 외부 Harness의 prompt catalog, HANA override, reranker routing, specialist dispatch를 독립적으로 검증합니다.
- 주요 노트북:
  - [01_reranker_routing.ipynb](5_harness/notebooks/01_reranker_routing.ipynb) — Chat/Work 및 specialist 후보 reranking
  - [02_deepagents_optional.ipynb](5_harness/notebooks/02_deepagents_optional.ipynb) — prompt catalog, HANA snapshot, DeepAgents 연결 조건
  - [03_delegation_a2a.ipynb](5_harness/notebooks/03_delegation_a2a.ipynb) — in-memory A2A delegation과 message trace
- 구성: `prompts/`는 기본 프롬프트, `fixtures/`는 읽기 전용 override snapshot, `src/reranker.py`는 로컬 fallback과 원격 reranker adapter를 제공합니다.
- 선택 확장: DeepAgents는 별도 의존성과 외부 LiteLLM/MCP Registry 권한이 준비된 경우에만 연결합니다.

### 6. [Business Issue 캡스톤](6_Business_issue/)

- 목적: Harness를 실제 업무 판단 보조에 적용하고, 근거 수집·결정론적 계산·설명 생성·사람 승인의 경계를 확인합니다.
- 주요 시나리오:
  - [재고·발주](6_Business_issue/notebooks/01_inventory_replenishment_case.ipynb) — 안전재고, MOQ, 할인, 예산을 반영한 발주 초안
  - [KYC 검토](6_Business_issue/notebooks/02_kyc_review_case.ipynb) — 증빙·스크리닝에 따른 강화심사/차단/승인 권고
  - [채권 RA](6_Business_issue/notebooks/03_receivables_risk_assessment.ipynb) — 여신한도·연체·신규 주문 기반의 조건부 출고 권고
  - [압류·AML Multi-Agent](6_Business_issue/notebooks/04_seizure_aml_multiagent.ipynb) — 병렬 분석, 동적 위임, 재계획, 근거 기반 보고서 초안
- 안전성: fixture는 모두 합성 데이터이며, 예제는 읽기 전용입니다. ERP 발주, 신용한도 변경, 계정 개설은 사람 승인 뒤 별도 write tool로만 연결해야 합니다.

## 공통 구성

- [shared/lab_common/](shared/lab_common/) — AI Core 설정, SDK adapter, telemetry, Gradio UI 공통 코드
- [.env.example](.env.example) — 필요한 환경변수의 안전한 예시
- [requirements.txt](requirements.txt) — 기본 Jupyter·SDK·데이터 처리 의존성

## Gradio UI

노트북의 **UI 실행** 셀을 실행하면 브라우저 공유 링크 없이 현재 Jupyter session 안에서 로컬 Gradio 화면을 엽니다. 공통 구현은 [shared/lab_common/gradio_ui.py](shared/lab_common/gradio_ui.py)에 있습니다.

- 환경 설정과 RUNNING deployment 확인
- LLM prompt chatbot
- embedding similarity 비교
- reranker decision recommendation playground

## 검증

각 폴더의 테스트는 독립 실행할 수 있습니다.

```bash
python3 -m unittest discover -s 2_gen_ai_hub_llm/tests -v
python3 -m unittest discover -s 4_agent_patterns/tests -v
python3 -m unittest discover -s 5_harness/tests -v
python3 -m unittest discover -s 6_Business_issue/tests -v
```
