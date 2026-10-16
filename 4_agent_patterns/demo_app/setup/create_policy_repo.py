# -*- coding: utf-8 -*-
"""
정책 그라운딩 저장소 생성 + 정책 문서 수집 (1회).
출력된 GROUNDING_REPOSITORY_ID 를 에이전트 환경변수로 설정하면 search_policy 도구가 동작한다.

사용:  (service key 환경변수 설정 후)  python setup/create_policy_repo.py
"""
import os, sys, json, requests

HERE = os.path.dirname(os.path.abspath(__file__))
TITLE = os.getenv("POLICY_COLLECTION_TITLE", "capstone-procurement-policy")
EMBED = os.getenv("EMBED_MODEL", "text-embedding-3-small")

def need(n):
    v = os.getenv(n);
    if not v: sys.exit(f"[ERROR] {n} 필요")
    return v

BASE = need("AICORE_BASE_URL").rstrip("/"); AUTH = need("AICORE_AUTH_URL").rstrip("/")
CID, CSEC = need("AICORE_CLIENT_ID"), need("AICORE_CLIENT_SECRET")
RG = os.getenv("AICORE_RESOURCE_GROUP", "default")
DG = f"{BASE}/v2/lm/document-grounding"

tok = requests.post(f"{AUTH}/oauth/token", data={"grant_type":"client_credentials"}, auth=(CID,CSEC)).json()["access_token"]
H = {"Authorization": f"Bearer {tok}", "AI-Resource-Group": RG, "Content-Type":"application/json"}

# 1) 저장소 생성(이미 있으면 재사용)
requests.post(f"{DG}/vector/collections", headers=H, json={"title":TITLE,"embeddingConfig":{"modelName":EMBED}})
cols = requests.get(f"{DG}/vector/collections", headers=H).json().get("resources", [])
cid = next((c["id"] for c in cols if c["title"] == TITLE), None)
assert cid, "collection id 조회 실패"

# 2) 정책 문서 → 섹션별 청크로 수집
text = open(os.path.join(HERE, "procurement_policy.md"), encoding="utf-8").read()
sections = [s.strip() for s in text.split("\n## ") if s.strip()]
chunks = [{"content": ("## " + s if not s.startswith("#") else s),
           "metadata":[{"key":"index","value":[str(i)]}]} for i, s in enumerate(sections, 1)]
entry = {"documents":[{"metadata":[{"key":"id","value":["procurement_policy.md"]}], "chunks": chunks}]}
requests.post(f"{DG}/vector/collections/{cid}/documents", headers=H, json=entry)

print("정책 저장소 준비 완료")
print(f"GROUNDING_REPOSITORY_ID={cid}")
