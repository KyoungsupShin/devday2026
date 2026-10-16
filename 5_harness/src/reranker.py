"""Reranking adapter with a deterministic local fallback for hands-on work."""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

import requests

from lab_common.config import Settings
from .harness_prompts import rerank_document
from lab_common.models import Candidate, RankedCandidate, RouteDecision

TOKEN = re.compile(r"[가-힣A-Za-z0-9]+")

FAST_ROUTE_CANDIDATES = [
    Candidate("chat", "Conversation Responder", "인사, 개념 설명, 간단한 대화형 질문에 답변한다. 도구나 업무 실행은 하지 않는다."),
    Candidate("work", "Deep Orchestrator", "조사, 분석, 시스템 조회, 문서 생성, 업무 실행이 필요한 요청을 처리한다."),
]
SPECIALIST_CANDIDATES = [
    Candidate("researcher", "Researcher", rerank_document("rerank.specialist_dispatch.researcher", "근거 수집, 시장/제품/문서 조사와 출처 정리를 담당한다.")),
    Candidate("business-agent", "Business Agent", rerank_document("rerank.specialist_dispatch.business-agent", "매출, 재고, 주문, 고객 등 비즈니스 데이터를 분석하고 권고안을 만든다.")),
    Candidate("app-agent", "App Agent", rerank_document("rerank.specialist_dispatch.app-agent", "앱 생성, UI, API, 배포, 코드 변경을 담당한다.")),
    Candidate("writer", "Analyst Writer", "이미 수집된 사실을 요약하고 보고서, 메일, 발표문으로 작성한다."),
]


def _tokens(text: str) -> Counter[str]:
    return Counter(token.lower() for token in TOKEN.findall(text))


def local_rank(query: str, candidates: Iterable[Candidate]) -> list[RankedCandidate]:
    """Explainable lexical baseline, not a substitute for Cohere semantic reranking."""
    query_terms = _tokens(query)
    result: list[RankedCandidate] = []
    for candidate in candidates:
        terms = _tokens(candidate.label + " " + candidate.description)
        overlap = sum(min(query_terms[word], terms[word]) for word in query_terms)
        boosts = {
            "chat": ("안녕", "설명", "무엇", "차이"),
            "work": ("조사", "분석", "만들", "조회", "작성", "보고서", "재고"),
            "researcher": ("조사", "근거", "시장", "출처", "문서"),
            "business-agent": ("매출", "재고", "주문", "고객", "분석"),
            "app-agent": ("앱", "ui", "api", "코드", "배포"),
            "writer": ("요약", "보고서", "메일", "발표", "작성"),
        }
        overlap += sum(1 for word in boosts.get(candidate.id, ()) if word in query.lower())
        result.append(RankedCandidate(candidate, float(overlap)))
    return sorted(result, key=lambda item: (-item.score, item.candidate.id))


def _remote_rank(query: str, candidates: list[Candidate], settings: Settings) -> list[RankedCandidate]:
    headers = {"Content-Type": "application/json"}
    if settings.rerank_api_key:
        headers["Authorization"] = f"Bearer {settings.rerank_api_key}"
    response = requests.post(
        settings.rerank_endpoint,
        headers=headers,
        json={"model": settings.rerank_model, "query": query, "documents": [candidate.description for candidate in candidates], "top_n": len(candidates)},
        timeout=15,
    )
    response.raise_for_status()
    by_index = {int(item["index"]): float(item["relevance_score"]) for item in response.json()["results"]}
    return sorted((RankedCandidate(candidate, by_index.get(index, 0.0)) for index, candidate in enumerate(candidates)), key=lambda item: -item.score)


def decide(query: str, candidates: list[Candidate], settings: Settings | None = None, min_margin: float = 0.25) -> RouteDecision:
    """Return selected candidate plus margin; tie/remote failures become explicit fallback."""
    engine = "local_lexical"
    try:
        if settings and settings.rerank_endpoint:
            ranked = _remote_rank(query, candidates, settings)
            engine = "litellm_rerank"
        else:
            ranked = local_rank(query, candidates)
    except (requests.RequestException, KeyError, TypeError, ValueError):
        ranked = local_rank(query, candidates)
        engine = "local_lexical_fallback"
    margin = ranked[0].score - ranked[1].score if len(ranked) > 1 else ranked[0].score
    scores = {item.candidate.id: item.score for item in ranked}
    return RouteDecision(selected=ranked[0].candidate.id, scores=scores, margin=margin, engine=engine, fallback=margin < min_margin)

