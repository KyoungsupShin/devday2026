#!/usr/bin/env bash
#
# 핸즈온 라이브 검증 실행 (생성 → 검증 → 삭제)
#
# 사용법:
#   ./run_validation.sh <service-key.json> [pdf_dir]
#
#   <service-key.json>  AI Core 서비스 키 파일 (clientid/clientsecret/url/serviceurls.AI_API_URL 포함)
#   [pdf_dir]           모듈 5 수집용 PDF 폴더 (기본: documents/ — codejam exercises/documents 경로)
#
# 하는 일:
#   1) 서비스 키에서 자격증명을 읽어 환경변수 설정
#   2) 전용 venv(.venv-validate) 생성 + 필요한 패키지 설치
#   3) validate_handson.py 실행 → 저장소 생성→전 시나리오 검증→저장소 삭제
#
# 권장 Python: 3.10 ~ 3.13
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY="${1:-}"
PDF_DIR="${2:-documents/}"

if [[ -z "$KEY" || ! -f "$KEY" ]]; then
  echo "사용법: $0 <service-key.json> [pdf_dir]" >&2
  echo "  예:   $0 ./ai-core-key.json ../generative-ai-codejam/exercises/documents" >&2
  exit 1
fi

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "python3 를 찾을 수 없습니다. PYTHON=... 로 지정하세요." >&2; exit 1; }

echo "== 1) 서비스 키에서 자격증명 읽기 =="
# 비밀값은 화면에 출력하지 않고 환경변수로만 설정
eval "$("$PY" - "$KEY" <<'PYEOF'
import json, sys, shlex
k = json.load(open(sys.argv[1]))
def g(*path):
    v = k
    for p in path: v = v[p]
    return v
pairs = {
    "AICORE_CLIENT_ID":     g("clientid"),
    "AICORE_CLIENT_SECRET": g("clientsecret"),
    "AICORE_AUTH_URL":      g("url").rstrip("/"),
    "AICORE_BASE_URL":      g("serviceurls","AI_API_URL").rstrip("/"),
}
for key, val in pairs.items():
    print(f"export {key}={shlex.quote(val)}")
PYEOF
)"
export AICORE_RESOURCE_GROUP="${AICORE_RESOURCE_GROUP:-default}"
export DG_PDF_DIR="$PDF_DIR"
export LLM_MODEL="${LLM_MODEL:-gpt-5.6-sol}"
export EMBED_MODEL="${EMBED_MODEL:-text-embedding-3-small}"
echo "   resource group = $AICORE_RESOURCE_GROUP, model = $LLM_MODEL"

if [[ ! -d "$DG_PDF_DIR" ]] || ! ls "$DG_PDF_DIR"/*.pdf >/dev/null 2>&1; then
  echo "경고: '$DG_PDF_DIR' 에 PDF가 없습니다. 두 번째 인자로 PDF 폴더를 지정하세요." >&2
  echo "      예: $0 $KEY ../generative-ai-codejam/exercises/documents" >&2
  exit 1
fi

echo "== 2) venv 생성 + 패키지 설치 (.venv-validate) =="
VENV="$SCRIPT_DIR/.venv-validate"
if [[ ! -d "$VENV" ]]; then
  "$PY" -m venv "$VENV"
fi
VPY="$VENV/bin/python"
"$VPY" -m pip install -q --upgrade pip >/dev/null
# 검증에 필요한 최소 의존성 (참가자와 동일한 orchestration_v2 = sap-ai-sdk-gen)
"$VPY" -m pip install -q "sap-ai-sdk-gen==5.11.0" scipy pypdf langchain-text-splitters requests
echo "   설치 완료"

echo "== 3) 검증 실행 (생성 → 검증 → 삭제) =="
cd "$SCRIPT_DIR"
set +e
"$VPY" validate_handson.py
RC=$?
set -e

echo ""
if [[ $RC -eq 0 ]]; then
  echo "✅ 전 시나리오 PASS — 상세: $SCRIPT_DIR/validation_results.json"
else
  echo "⚠️  일부 FAIL — $SCRIPT_DIR/validation_results.json 에서 상세 확인"
fi
exit $RC
