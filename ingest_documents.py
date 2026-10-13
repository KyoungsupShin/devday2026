#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
모듈 5 사전 수집 스크립트 — AI Core Document Grounding (Vector API)

강사가 핸즈온 전에 **한 번** 실행해 공유 벡터 저장소를 만들고 문서를 수집합니다.
출력되는 collection id 를 참가자에게 `GROUNDING_REPOSITORY_ID` 로 공유하세요.

근거: SAP-samples/sap-btp-ai-best-practices
      best-practices/generative-ai/document-grounding/python/Document_Grounding_Vector_API.ipynb

흐름: 토큰 발급 → 저장소(collection) 생성 → PDF 청킹 → JSONL → 수집 → 검색 확인

필요 환경변수 (service key 기준):
  AICORE_CLIENT_ID, AICORE_CLIENT_SECRET, AICORE_AUTH_URL, AICORE_BASE_URL
  (AICORE_BASE_URL = service key 의 AI API URL, 예: https://api.ai.prod.<region>.aws.ml.hana.ondemand.com)
선택:
  AICORE_RESOURCE_GROUP (기본 default), DG_PDF_DIR (기본 documents/), DG_COLLECTION_TITLE

의존성: requests, pypdf, langchain-text-splitters, tqdm  (codejam requirements 에 포함)
"""
import os, sys, json, argparse
import requests
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tqdm import tqdm

def env(name, default=None, required=False):
    v = os.getenv(name, default)
    if required and not v:
        sys.exit(f"[ERROR] 환경변수 {name} 가 필요합니다.")
    return v

def get_token(client_id, client_secret, auth_url):
    r = requests.post(auth_url, data={"grant_type": "client_credentials"},
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      auth=(client_id, client_secret))
    r.raise_for_status()
    return r.json()["access_token"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedding-model", default="text-embedding-3-small",
                    help="저장소 임베딩 모델명 (배포된 것)")
    args = ap.parse_args()

    client_id = env("AICORE_CLIENT_ID", required=True)
    client_secret = env("AICORE_CLIENT_SECRET", required=True)
    auth_url = env("AICORE_AUTH_URL", required=True)
    api_url = env("AICORE_BASE_URL", required=True).rstrip("/")
    rg = env("AICORE_RESOURCE_GROUP", "default")
    pdf_dir = env("DG_PDF_DIR", "documents/")
    title = env("DG_COLLECTION_TITLE", "skt-genai-hub-handson")

    base = f"{api_url}/v2/lm/document-grounding"
    token = get_token(client_id, client_secret, auth_url)
    H = {"Authorization": f"Bearer {token}", "AI-Resource-Group": rg,
         "Content-Type": "application/json"}
    print(f"[1/4] 토큰 발급 완료 · resource group={rg}")

    # ---- 저장소(collection) 생성 ----
    body = {"title": title, "embeddingConfig": {"modelName": args.embedding_model}}
    requests.post(f"{base}/vector/collections", headers=H, json=body)  # 201/409(이미 존재)
    # 제목으로 collection id 조회 (생성 응답이 비동기/헤더형일 수 있어 조회가 안전)
    lst = requests.get(f"{base}/vector/collections", headers=H)
    lst.raise_for_status()
    cols = lst.json().get("resources", lst.json()) if isinstance(lst.json(), dict) else lst.json()
    cid = None
    for c in cols:
        if c.get("title") == title:
            cid = c.get("id") or c.get("collectionId")
            break
    if not cid:
        sys.exit(f"[ERROR] collection id 를 찾지 못했습니다. 응답: {lst.text[:500]}")
    print(f"[2/4] 저장소 준비 완료 · collection id = {cid}")

    # ---- PDF → 청킹 → JSONL ----
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    pdfs = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
    if not pdfs:
        sys.exit(f"[ERROR] {pdf_dir} 에 PDF가 없습니다.")
    entries = []
    for pdf in pdfs:
        text = "".join((p.extract_text() or "") for p in PdfReader(os.path.join(pdf_dir, pdf)).pages)
        chunks = splitter.split_text(text)
        entries.append({"documents": [{
            "metadata": [{"key": "id", "value": [pdf]},
                         {"key": "source", "value": [pdf]}],
            "chunks": [{"content": ch, "metadata": [{"key": "index", "value": [str(i)]}]}
                       for i, ch in enumerate(chunks, 1)]
        }]})
    print(f"[3/4] 청킹 완료 · PDF {len(pdfs)}개 → 문서 {len(entries)}건")

    # ---- 수집(ingest) ----
    url = f"{base}/vector/collections/{cid}/documents"
    for e in tqdm(entries, desc="Uploading"):
        r = requests.post(url, headers=H, json=e)
        if r.status_code >= 300:
            print(f"\n[WARN] 업로드 실패 {r.status_code}: {r.text[:200]}")
    print("[4/4] 수집 완료")

    # ---- 검색 확인 ----
    sr = requests.post(f"{base}/retrieval/search", headers=H, json={
        "query": "What is data masking in the orchestration service?",
        "filters": [{"id": "f", "dataRepositoryType": "vector", "dataRepositories": [cid]}],
    })
    print("검색 테스트 status:", sr.status_code)
    print("\n================ 참가자에게 공유할 값 ================")
    print(f"GROUNDING_REPOSITORY_ID = {cid}")
    print("====================================================")

if __name__ == "__main__":
    main()
