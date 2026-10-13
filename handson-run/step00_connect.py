# -*- coding: utf-8 -*-
"""Step 0 · 연결 확인
실습자용 모듈 0에 해당. 토큰 발급 + 배포 조회로 '진짜 연결되는지' 확인한다.
실행: .venv/bin/python step00_connect.py
"""
import _env
_env.load()

import os
import requests

print("=" * 56)
print("Step 0 · 연결 확인")
print("=" * 56)

# 1) 연결 값이 환경에 들어왔는지 (secret 은 길이만)
print("\n[1] 연결 값 로드 확인")
print("  BASE_URL        :", os.getenv("AICORE_BASE_URL"))
print("  AUTH_URL        :", os.getenv("AICORE_AUTH_URL"))
print("  CLIENT_ID       :", (os.getenv("AICORE_CLIENT_ID") or "")[:18], "...")
print("  CLIENT_SECRET   :", "set (len=%d)" % len(os.getenv("AICORE_CLIENT_SECRET") or ""))
print("  RESOURCE_GROUP  :", os.getenv("AICORE_RESOURCE_GROUP"))

# 2) 토큰 발급 (실제 OAuth 호출)
print("\n[2] OAuth 토큰 발급")
h = _env.headers()
print("  토큰 발급 성공 ✅ (Authorization 헤더 준비됨)")

# 3) 배포 조회 — orchestration/foundation-models RUNNING 확인
print("\n[3] 배포(Deployment) 조회")
base = os.getenv("AICORE_BASE_URL").rstrip("/")
deps = requests.get(f"{base}/v2/lm/deployments?$top=200", headers=h, timeout=20).json()
running = [d for d in deps.get("resources", []) if d.get("status") == "RUNNING"]
print(f"  RUNNING 배포 {len(running)}개")
for d in sorted(running, key=lambda r: r.get("scenarioId", "")):
    sid = d.get("scenarioId")
    if sid in ("orchestration", "foundation-models"):
        print(f"    - {sid:18} RUNNING")

# 4) orchestration URL 자동 조회
print("\n[4] orchestration 배포 URL")
orch = _env.orchestration_url()
print("  URL 뒤 24자:", "..." + orch[-24:])

print("\n✅ 연결 확인 완료 — 이후 스텝 진행 가능")
