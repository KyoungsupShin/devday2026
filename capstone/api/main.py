# -*- coding: utf-8 -*-
"""FastAPI — 에이전트 두 모드를 REST로 노출. React 화면이 호출한다."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # capstone/ 를 path에

import json as _json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from agent import core, config, advanced

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

app = FastAPI(title="재고 에이전트 캡스톤", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class TaskReq(BaseModel):
    task: str = "재고를 점검하고 발주가 필요한 품목과 권장 수량을 정리해줘."

class GoalReq(BaseModel):
    goal: str

@app.get("/api/health")
def health():
    return {"ok": True, "model": config.LLM_MODEL,
            "policy_repo": bool(config.GROUNDING_REPOSITORY_ID)}

@app.post("/api/mode-a")
def mode_a(req: TaskReq):
    """제한형: LLM이 도구를 한 번 선택(반복 없음) → 결과 정리."""
    return core.mode_a_bounded(req.task)

@app.post("/api/mode-b")
def mode_b(req: GoalReq):
    """자율형: 목표만 주면 도구를 스스로 써서 달성. trace(도구 호출 내역) 포함."""
    return core.mode_b_autonomous(req.goal)

@app.post("/api/mode-b/stream")
def mode_b_stream(req: GoalReq):
    """자율형 스트리밍(SSE) — 루프/도구 진행 이벤트를 실시간으로 흘려보낸다(진행바용)."""
    def gen():
        for ev in core.mode_b_stream(req.goal):
            yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ─────────────────────────── 심화 데모 (본편 미사용 Orchestration 기능 4종) ───────────────────────────
class RFReq(BaseModel):
    req: str = "A 품목이 안전재고 미만이라 S1에서 긴급 발주해야 함"

class StreamReq(BaseModel):
    topic: str = "재고 자율 에이전트의 장점"

class TransReq(BaseModel):
    topic: str = "benefits of an autonomous inventory agent"

@app.post("/api/adv/response-format")
def adv_response_format(req: RFReq):
    """자유 텍스트 vs JSON 스키마 강제(구조화 출력)."""
    return advanced.demo_response_format(req.req)

@app.post("/api/adv/stream")
def adv_stream(req: StreamReq):
    """토큰 스트리밍(SSE) — 조각(delta)을 실시간으로 흘려보냄."""
    def gen():
        for d in advanced.demo_stream(req.topic):
            yield f"data: {_json.dumps({'delta': d}, ensure_ascii=False)}\n\n"
        yield "data: {\"done\": true}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/api/adv/translation")
def adv_translation(req: TransReq):
    """영문 응답 → Orchestration 번역 모듈로 한국어 변환."""
    return advanced.demo_translation(req.topic)

@app.post("/api/adv/multimodal")
def adv_multimodal():
    """송장 이미지를 '보고' 품목/수량/금액을 구조화 JSON으로 추출."""
    return advanced.demo_multimodal()

@app.get("/api/adv/invoice")
def adv_invoice():
    """멀티모달 데모가 입력으로 쓰는 샘플 송장 이미지."""
    return FileResponse(advanced.INVOICE_PATH, media_type="image/png")

# 정적 UI (React 단일 파일) — API 라우트 뒤에 마운트해야 함
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
