# -*- coding: utf-8 -*-
"""AI Core 연결/설정 — service key 환경변수에서 읽고, orchestration 배포 URL 자동 조회."""
import os
import requests

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.6-sol")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
RESOURCE_GROUP = os.getenv("AICORE_RESOURCE_GROUP", "default")
GROUNDING_REPOSITORY_ID = os.getenv("GROUNDING_REPOSITORY_ID")  # 정책 문서 저장소(선택)

def _require(name):
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"환경변수 {name} 가 필요합니다 (service key).")
    return v

BASE_URL = _require("AICORE_BASE_URL").rstrip("/")
AUTH_URL = _require("AICORE_AUTH_URL").rstrip("/")
CLIENT_ID = _require("AICORE_CLIENT_ID")
CLIENT_SECRET = _require("AICORE_CLIENT_SECRET")

def get_token() -> str:
    r = requests.post(f"{AUTH_URL}/oauth/token",
                      data={"grant_type": "client_credentials"},
                      auth=(CLIENT_ID, CLIENT_SECRET), timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]

def _headers():
    return {"Authorization": f"Bearer {get_token()}", "AI-Resource-Group": RESOURCE_GROUP}

_ORCH_URL = os.getenv("AICORE_ORCHESTRATION_DEPLOYMENT_URL")

def orchestration_url() -> str:
    """RUNNING orchestration 배포 URL (env 우선, 없으면 자동 조회)."""
    global _ORCH_URL
    if _ORCH_URL:
        return _ORCH_URL
    deps = requests.get(f"{BASE_URL}/v2/lm/deployments?$top=200", headers=_headers(), timeout=20).json()
    for d in deps.get("resources", []):
        if d.get("scenarioId") == "orchestration" and d.get("status") == "RUNNING":
            _ORCH_URL = d["deploymentUrl"]
            return _ORCH_URL
    raise RuntimeError("RUNNING orchestration 배포를 찾지 못했습니다.")
