# 트러블슈팅 & FAQ (강사용)

핸즈온 중 자주 나오는 문제와 조치입니다. 모듈 0에서 미리 공유해두면 좋습니다.

---

## 연결 / 인증

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| ID/URL이 `None` 출력 | `variables.py` 미입력 | 값 채우고 커널 재시작 |
| `401 Unauthorized` / `403` | 자격증명 누락·만료 | `~/.aicore/config.json` 또는 환경변수 확인 |
| `404` / deployment not found | 배포 URL 오타 또는 미완료 | `AICORE_ORCHESTRATION_DEPLOYMENT_URL` 확인, 배포 RUNNING 대기 |
| 변경이 반영 안 됨 | 모듈 캐시 | `importlib.reload(variables)` 또는 커널 재시작 |

## SDK / import

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| `ImportError: orchestration...` | 구버전 네임스페이스 사용 | `gen_ai_hub.orchestration_v2` 로 import |
| `ModuleNotFoundError` | venv 미활성/설치 실패 | `.venv` 활성, `pip install -r requirements.txt` 재실행 |
| 패키지명이 문서와 다름 | SDK 재편(`sap-ai-sdk-*`) | import는 `gen_ai_hub.*` 로 한다고 안내 |

## 모델

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| 모델명 오류 | 미배포 모델 지정 | Launchpad의 배포된 모델명만 사용 |
| 멀티모달 입력 에러 | 비멀티모달 모델 | `gpt-5.6-sol` 등 멀티모달 모델로 |
| `400 ... temperature=0` | GPT-5 계열(`gpt-5.6-sol`)은 `temperature=0` 미지원 | `params` 에서 temperature 생략 또는 0.2 이상 |
| `name=""` 관련 에러 | 노트북 원본 빈 값 | 배포된 모델명 입력 |

## Orchestration / 필터 / 그라운딩

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| 셀이 에러로 멈춤(필터) | 차단이 예외로 발생 | `try/except OrchestrationError` 로 감싸기 |
| 필터가 안 먹음 | 임계값 `ALLOW_ALL` | 더 엄격한 `AzureThreshold` |
| 그라운딩 빈/엉뚱한 답 | placeholder 이름 불일치 | `input`/`output` 과 템플릿 `{{?...}}` 일치 |
| 그라운딩 무시 | `grounding=...` 누락 | `ModuleConfig` 에 포함 확인 |
| 스트리밍 출력 없음 | stream 옵션 누락 | `GlobalStreamOptions(enabled=True)` |

## 내 문서 그라운딩 (모듈 5)

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| 빈 답 | `GROUNDING_REPOSITORY_ID` 오타/미입력 | `data_repositories` 의 id 확인 |
| 엉뚱한 답 | 수집 미완/검색 실패 | 강사가 Run Search로 검색되는지 사전 확인 |
| 타입 오류 | `data_repository_type` 오타 | `"vector"` 정확히 |
| placeholder 불일치 | 템플릿 변수명 | `input`/`output` 과 `{{?...}}` 일치 |
| 저장소에 문서 없음 | 수집(ingest) 누락 | Grounding Management에서 수집 완료 확인 |

---

## 자주 나오는 질문 (개념)

- **"GPT를 쓰면 데이터가 OpenAI로 가나요?"** → SAP AI Core를 경유하며, SAP의 데이터 처리 정책 하에서 호출됩니다. 구체 보장 범위는 SAP 계약/문서 기준으로 안내.
- **"비용은 어떻게 과금되나요?"** → 모델별 토큰 기반. 필터·그라운딩 등 추가 모듈은 추가 호출/지연 유발. 정확한 과금은 환경·계약 확인.
- **"프로덕션에 바로 쓸 수 있나요?"** → 개념 실습용. 프로덕션은 에러 처리, 비용·속도, 보안(마스킹·필터), 평가·모니터링을 추가 설계해야 함.
- **"orchestration_v2의 전체 API는 어디서 보나요?"** → `exercises/documents/` 의 SDK PDF 및 SAP Help의 Generative AI Hub SDK 레퍼런스.

## 시간이 모자랄 때 (강사 판단)

우선순위: **모듈 1(환각) → 3(Orchestration) → 4(그라운딩, 수미상관)** 는 서사의 핵심이라 유지. 밀리면:

1. 모듈 2는 임베딩 생성만 보여주고 유사도 실험은 생략
2. 모듈 5는 공개 vs 내 문서 비교만 데모로
3. 모듈 6은 메모리 데모만, 종합 과제는 "집에서 해보기"로

## 시간이 남을 때

보너스 3(메모리+그라운딩) → 보너스 2(복수 소스 그라운딩) → 각자 vibe coding 순으로 채우세요.
