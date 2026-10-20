# 3. Gen AI Hub Services

AI Core Orchestration과 document grounding을 서비스 단위로 확인합니다. 문서 원본의 보관과 검색 근거는 분리되어 있으며, 모든 노트북은 루트 `.env`를 읽습니다.

## 시작 전 준비

1~2단계의 AI Core 연결을 마친 뒤 [루트 README](../README.md#사전-준비와-설치)의 공통 환경을 사용하세요. 설치가 아직이면 저장소 루트에서 운영체제에 맞는 한 줄을 실행합니다.

**macOS/Linux**

```bash
python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip -r requirements.txt
```

**Windows PowerShell**

```powershell
py -m venv .venv && .\.venv\Scripts\python.exe -m pip install --upgrade pip -r requirements.txt
```

기본 AI Core 값 외에 grounding 실습에는 `GROUNDING_REPOSITORY_ID`가 필요합니다. Orchestration deployment URL을 고정하려면 `AICORE_ORCHESTRATION_DEPLOYMENT_URL`도 설정합니다.

## 실습 순서

1. `notebooks/01_orchestration.ipynb` — 등록된 BTP Orchestration 조회·호출, prompt templating, 콘텐츠 필터, 데이터 마스킹을 확인합니다.
2. `notebooks/02_grounding.ipynb` — 인덱싱된 문서 chunk를 근거로 질의하고 답변을 확인합니다.

```bash
.venv/bin/python 3_gen_ai_hub_services/main.py --help
.venv/bin/python 3_gen_ai_hub_services/main.py orchestration "고객 문의를 요약해줘"
```

## 선택: Object Storage → Grounding

`02_grounding.ipynb`의 **Object Storage → Grounding** 탭은 UTF-8 `.md` 원본을 SAP BTP Object Storage(S3 호환)에 저장하고, 같은 텍스트를 선택한 vector repository에 인덱싱합니다. 질의는 Object Storage가 아니라 인덱싱된 vector chunk를 근거로 수행합니다.

다음 값을 `.env`에 설정하거나 Object Storage service binding을 `VCAP_SERVICES`로 제공합니다.

```dotenv
OBJECT_STORAGE_ENDPOINT=https://<object-storage-endpoint>
OBJECT_STORAGE_ACCESS_KEY_ID=
OBJECT_STORAGE_SECRET_ACCESS_KEY=
OBJECT_STORAGE_BUCKET=
OBJECT_STORAGE_REGION=
OBJECT_STORAGE_PREFIX=grounding
```

`OBJECT_STORAGE_PREFIX`의 기본값은 `grounding`입니다. Grounding UI에서 문서를 삭제해도 원본 object는 보존됩니다.

## 성공 기준과 확인

등록된 orchestration을 호출하고 grounding 응답이 참조한 근거를 확인합니다. 저장소 미설정·조회 실패 상태를 근거 없는 응답으로 대체하지 않습니다.

```bash
.venv/bin/python -m unittest discover -s 3_gen_ai_hub_services/tests -v
```
