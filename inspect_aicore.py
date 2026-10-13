#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
조회(inspection) 유틸 — UI 없이 코드로 AI Core 상태를 확인한다.

Launchpad에서 보던 것들을 터미널에서 바로 확인:
  - 배포(Deployments): orchestration/LLM/임베딩이 RUNNING인지, URL이 뭔지
  - 그라운딩 저장소(Collections): 내 저장소 목록
  - 저장소 문서(Documents): 저장소에 문서가 들어갔는지
  - 검색(Search): 질문에 대해 "어떤 청크가 검색되는지" (답변 생성 전 단계)

사용법 (service key 환경변수 설정 후):
  python inspect.py                          # 배포 + 저장소 요약
  python inspect.py deployments              # 배포 목록
  python inspect.py collections              # 그라운딩 저장소 목록
  python inspect.py documents <collection>   # 저장소의 문서 목록
  python inspect.py search <collection> "질문"  # 검색된 청크 보기

필요 환경변수: AICORE_CLIENT_ID/SECRET/AUTH_URL/BASE_URL (+ AICORE_RESOURCE_GROUP, 기본 default)
"""
import os, sys, json, requests

RG = os.getenv("AICORE_RESOURCE_GROUP", "default")
def need(n):
    v = os.getenv(n)
    if not v: sys.exit(f"[ERROR] 환경변수 {n} 필요")
    return v
BASE = need("AICORE_BASE_URL").rstrip("/")
AUTH = need("AICORE_AUTH_URL").rstrip("/")
CID, CSEC = need("AICORE_CLIENT_ID"), need("AICORE_CLIENT_SECRET")
DG = f"{BASE}/v2/lm/document-grounding"

def H():
    tok = requests.post(f"{AUTH}/oauth/token", data={"grant_type":"client_credentials"}, auth=(CID, CSEC)).json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "AI-Resource-Group": RG, "Content-Type":"application/json"}

def deployments(h):
    d = requests.get(f"{BASE}/v2/lm/deployments?$top=200", headers=h).json().get("resources", [])
    print(f"\n[배포] resource group={RG} · {len(d)}개")
    want = ("orchestration","foundation-models")
    for x in sorted(d, key=lambda r: r.get("scenarioId","")):
        sid = x.get("scenarioId"); st = x.get("status")
        det = (x.get("details",{}) or {}).get("resources",{}) or {}
        model = ((det.get("backend_details",{}) or {}).get("model",{}) or {}).get("name") if isinstance(det,dict) else None
        if sid in want and st == "RUNNING":
            tag = f" model={model}" if model else ""
            print(f"  {sid:18} {st:8}{tag}")
            if sid == "orchestration":
                print(f"       URL={x.get('deploymentUrl')}")

def collections(h):
    c = requests.get(f"{DG}/vector/collections", headers=h).json().get("resources", [])
    print(f"\n[그라운딩 저장소] {len(c)}개")
    for x in c:
        cid = x.get("id")
        n = requests.get(f"{DG}/vector/collections/{cid}/documents", headers=h).json().get("count","?")
        print(f"  title={x.get('title'):30} docs={n}  id={cid}")

def documents(h, cid):
    r = requests.get(f"{DG}/vector/collections/{cid}/documents", headers=h).json()
    print(f"\n[문서] collection={cid} · count={r.get('count')}")
    for d in r.get("resources", []):
        meta = {m['key']: m['value'] for m in d.get("metadata", [])}
        print(f"  id={d.get('id')}  meta={meta}")

def search(h, cid, query):
    body = {"query": query, "filters":[{"id":"f","dataRepositoryType":"vector","dataRepositories":[cid]}]}
    r = requests.post(f"{DG}/retrieval/search", headers=h, json=body).json()
    print(f"\n[검색] '{query}' → collection={cid}")
    found = 0
    for res in r.get("results", []):
        for rr in res.get("results", []):
            for doc in rr.get("dataRepository", {}).get("documents", []):
                for ch in doc.get("chunks", []):
                    found += 1
                    score = ch.get("searchScores",{}).get("aggregatedScore",{}).get("value")
                    print(f"  [{found}] score={score:.3f}  {ch.get('content','')[:120]}")
    if not found:
        print("  (검색된 청크 없음 — 수집/인덱싱 확인)")

def main():
    h = H()
    a = sys.argv[1:]
    if not a:
        deployments(h); collections(h); return
    cmd = a[0]
    if cmd == "deployments": deployments(h)
    elif cmd == "collections": collections(h)
    elif cmd == "documents" and len(a) >= 2: documents(h, a[1])
    elif cmd == "search" and len(a) >= 3: search(h, a[1], a[2])
    else:
        print("사용법: python inspect.py [deployments|collections|documents <id>|search <id> \"질문\"]")

if __name__ == "__main__":
    main()
