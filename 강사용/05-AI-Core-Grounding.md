# 모듈 5 · 내 문서 그라운딩 (AI Core Grounding) (강사용)

🎯 **목표**: 관리형 그라운딩을 **내 문서**로 확장. 모듈 4(공개)와 대비해 "소스만 바꾸면 된다"를 체득.
⏱️ **시간**: 35분 (설명 10분 + 실습 25분)
📓 기반: 노트북 07(Grounding Management, 수집) + 09(SDK 소비)

---

## 🧑‍🏫 강사 노트 — 왜 HANA가 아니라 AI Core Grounding인가

이전 버전은 HANA Vector Engine으로 직접 RAG를 짰지만, **단일 공유 AI Core + SDK 중심** 전제에선 별도 HANA가 군더더기입니다. 대신 **AI Core가 관리하는 벡터 저장소(Document Grounding)** 에 문서를 넣고, 모듈 4와 **똑같은 SDK 코드에서 필터만** 내 저장소로 바꿉니다.

핵심 메시지: **"소스는 필터 한 줄."** 모듈 4에서 `help.sap.com` 이던 걸 `vector` + 내 저장소 id로 바꾸면 끝. 모델 교체가 한 줄이었듯, **지식 소스 교체도 한 줄**임을 보여주세요.

### 역할 분담 (중요)

- **수집(ingestion)은 SDK 일급 API가 아닙니다.** AI Core Grounding의 저장소 생성·문서 적재는 **Grounding Management(UI)** 또는 **Grounding REST API**로 합니다. `ai_core_sdk` 의 "repository"는 Git 저장소(ML ops)라 무관합니다.
- 그래서 **참가자 실습 = 질의(SDK)** 에 집중시키고, **수집은 강사가 사전에** 처리합니다.

## 🧑‍🏫 사전 준비 — 공유 벡터 저장소 1개 (강사 1회)

단일 공유 AI Core에 가장 깔끔한 구성:

**권장 — 스크립트 1회 실행**: 저장소 폴더의 **`ingest_documents.py`** 를 쓰면 저장소 생성 → PDF 청킹 → 수집 → 검색 확인까지 자동입니다.

```bash
# service key 값을 환경변수로 (AICORE_CLIENT_ID/SECRET/AUTH_URL/BASE_URL)
export AICORE_RESOURCE_GROUP=default
python ingest_documents.py --embedding-model text-embedding-3-small
# → 마지막 줄의 GROUNDING_REPOSITORY_ID 를 참가자에게 공유
```

이 스크립트는 공식 best-practice(`sap-btp-ai-best-practices` 의 Document_Grounding_Vector_API)의 흐름을 따릅니다. REST 엔드포인트:

```
POST /v2/lm/document-grounding/vector/collections                 # 저장소 생성
POST /v2/lm/document-grounding/vector/collections/{id}/documents  # 수집(JSONL)
POST /v2/lm/document-grounding/retrieval/search                   # 검색 확인
```

(대안: Launchpad **Grounding Management UI** 로도 동일하게 생성·수집 가능)

수집이 잘 됐는지 **코드로 확인**:
```bash
python inspect_aicore.py collections                       # 저장소·문서 수
python inspect_aicore.py search <repo-id> "data masking"   # 검색되는 청크 확인
```

> 참가자별 저장소를 만들 수도 있지만, **읽기 전용 질의**라 하나를 공유해도 안전합니다(공개 help.sap.com과 같은 구도). 공유 저장소 1개 = 가장 단순.

🎬 수집 과정을 **라이브 데모**(화면 공유)로 1~2분 보여주면 "뒤에서 뭐가 일어나는지" 이해가 올라갑니다. 참가자는 따라 만들 필요 없이 id만 받습니다.

## Part B. SDK 질의 — 필터만 교체 (참가자 실습)

실습자용의 코드를 함께 실행. 설명 포인트:

```python
filters = [DocumentGroundingFilter(
    id="MyDocs",
    data_repository_type="vector",              # help.sap.com → vector
    data_repositories=[GROUNDING_REPOSITORY_ID] # 내 저장소 id
)]
```

💬 **이렇게 말하세요**: "모듈 4랑 뭐가 달라졌나요? 딱 두 가지예요 — `data_repository_type` 이 `vector` 가 됐고, `data_repositories` 에 우리 저장소 id가 들어갔죠. 나머지 그라운딩·템플릿·실행 코드는 전부 똑같습니다. **소스 교체 = 필터 한 줄.**"

🧑‍🏫 API 근거(검증됨, orchestration_v2 5.11.0): `DataRepositoryType` 은 `vector` / `help.sap.com`. `DocumentGroundingFilter` 는 `id`, `data_repository_type`, `data_repositories`(검색할 저장소 id 목록), 메타데이터 필터를 받습니다. `data_repositories` 를 비우면 해당 타입 전체 검색.

## 직접 바꿔보기 (실험)

- ⭐ **공개 vs 내 문서 비교**: 같은 질문을 모듈 4(help.sap.com)와 이 모듈(내 저장소)로. 소스에 따라 답이 어떻게 달라지는지 — 이게 이 모듈의 결론.
- 질문을 `documents/` PDF 내용(Orchestration/Grounding SDK)에 맞춰 던져 "내 문서라서 정확한" 답 확인.
- `max_document_count`(vector 전용)로 검색 범위 조절.

## 🧑‍🏫 (심화) 수집을 코드로 — `ingest_documents.py`

수집 과정을 보여주고 싶으면 위 사전 준비의 `ingest_documents.py` 를 라이브로 돌려주세요. 내부는 Vector API(REST) 호출이며(SDK 전용 클라이언트는 없음), 공식 best-practice(`sap-btp-ai-best-practices`)의 흐름을 그대로 따릅니다. 참가자가 "내 문서로 직접 해보고 싶다"면 이 스크립트의 PDF 폴더만 바꿔 실행하게 하면 됩니다.

## ❓ 예상 질문 & 답

- **"HANA는 이제 안 쓰나요?"** → 이 과정에선 불필요. AI Core Grounding이 저장·검색을 관리. HANA 직접 RAG는 더 세밀한 제어가 필요할 때의 별도 선택지.
- **"수집도 SDK로 안 되나요?"** → 질의는 SDK, 수집은 UI/REST. SDK에 수집 전용 클라이언트는 아직 없음.
- **"내 저장소 vs help.sap.com 동시에?"** → `filters` 리스트에 둘 다 넣으면 복수 소스 검색 가능.
- **"문서 업데이트하면 자동 반영?"** → 파이프라인 재실행/재수집 필요. 운영에선 수집 주기를 설계.

## ⚠️ 흔한 실수

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| 빈 답 | 저장소 id 오타/미지정 | `data_repositories` 의 id 확인 |
| 엉뚱한 답 | 수집 미완/검색 실패 | Run Search로 검색되는지 먼저 확인 |
| 타입 오류 | `data_repository_type` 오타 | `"vector"` 정확히 |
| placeholder 불일치 | 템플릿 변수명 | `input`/`output` 과 `{{?...}}` 일치 |

## ⏭️ 전환 멘트

> "소스 교체가 필터 한 줄이라는 걸 봤습니다. 공개 문서든 우리 문서든 코드는 같죠. 마지막으로, 지금까지는 단발 질문이었습니다. 실제 챗봇은 대화를 기억해야 하죠 — 다음 모듈에서 메모리를 붙입니다."
