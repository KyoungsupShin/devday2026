# -*- coding: utf-8 -*-
"""handson-run 공통 로더.
  - 같은 폴더의 .env 를 읽어 환경변수로 세팅 (python-dotenv 없이 직접 파싱)
  - SDK(gen_ai_hub)가 쓰는 AICORE_* 환경변수를 확정
  - orchestration 배포 URL 자동 조회 헬퍼 제공
각 step 파일 맨 위에서 `import _env; _env.load()` 로 사용.
"""
import os
import pathlib
import requests

_HERE = pathlib.Path(__file__).resolve().parent
_ENV_FILE = _HERE / ".env"


def load() -> None:
    """.env 파일을 읽어 os.environ 에 반영 (이미 설정된 값은 유지)."""
    if not _ENV_FILE.exists():
        raise RuntimeError(f".env 가 없습니다: {_ENV_FILE}")
    for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        # 값에 '=' 가 들어가도(clientsecret) split("=",1) 로 안전
        os.environ.setdefault(key, val)


def _need(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"환경변수 {name} 필요 (.env 확인)")
    return v


def headers() -> dict:
    """OAuth 토큰 발급 후 AI Core REST 호출용 헤더."""
    auth = _need("AICORE_AUTH_URL").rstrip("/")
    cid, csec = _need("AICORE_CLIENT_ID"), _need("AICORE_CLIENT_SECRET")
    rg = os.getenv("AICORE_RESOURCE_GROUP", "default")
    tok = requests.post(f"{auth}/oauth/token",
                        data={"grant_type": "client_credentials"},
                        auth=(cid, csec), timeout=20).json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "AI-Resource-Group": rg,
            "Content-Type": "application/json"}


def orchestration_url() -> str:
    """RUNNING orchestration 배포 URL (env 우선, 없으면 자동 조회)."""
    u = os.getenv("AICORE_ORCHESTRATION_DEPLOYMENT_URL")
    if u:
        return u
    base = _need("AICORE_BASE_URL").rstrip("/")
    deps = requests.get(f"{base}/v2/lm/deployments?$top=200",
                        headers=headers(), timeout=20).json()
    for d in deps.get("resources", []):
        if d.get("scenarioId") == "orchestration" and d.get("status") == "RUNNING":
            url = d["deploymentUrl"]
            os.environ["AICORE_ORCHESTRATION_DEPLOYMENT_URL"] = url
            return url
    raise RuntimeError("RUNNING orchestration 배포를 찾지 못했습니다.")
