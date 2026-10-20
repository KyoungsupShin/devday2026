"""CLI entry points for the LLM notebooks; no Jupyter or UI is required."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "1_gen_ai_hub" / "src"), str(Path(__file__).resolve().parent)]

from lab_common.config import load_settings
from src.reranker.lab_core import run_decision_recommendation
from src.prompt_model.lab_core import compare_prompts, run_chat
from src.embeddings.lab_core import compare_embeddings
from src.business_embedding.lab_core import load_business_cases, run_business_embedding_lab


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prompt = commands.add_parser("prompt", help="01: compare baseline and constrained prompts")
    prompt.add_argument("question", nargs="?", default="LLM의 기본 아키텍처를 한 문장으로 설명해줘.")
    chat = commands.add_parser("chat", help="01 UI: send one chat turn through the core")
    chat.add_argument("message", nargs="?", default="LLM의 기본 아키텍처를 한 문장으로 설명해줘.")
    chat.add_argument("--system-prompt", default="너는 친절한 교육 보조자다. 한국어로 간결하게 답한다.")
    chat.add_argument("--model", default=None)
    embedding = commands.add_parser("embedding", help="02: compare embedding similarities")
    embedding.add_argument("texts", nargs="*", default=["apple", "orange", "phone"])
    embedding.add_argument("--model", default=None, help="Embedding model (defaults to EMBED_MODEL)")
    decision = commands.add_parser("decision", help="03: make a reranker recommendation")
    decision.add_argument("case", nargs="?", default="인증된 고객이 일반적인 단일 주문을 시도했다.")
    business_embedding = commands.add_parser("business-embedding", help="04: cluster cases and recommend a business queue")
    business_embedding.add_argument(
        "--ticket",
        default="운송장에는 배송 완료로 나오지만 고객이 물건을 받지 못했습니다.",
        help="New business ticket to recommend",
    )
    business_embedding.add_argument("--clusters", type=int, default=4, help="Number of exploratory clusters")
    business_embedding.add_argument("--model", default=None, help="Embedding model (defaults to EMBED_MODEL)")
    args = parser.parse_args()
    settings = load_settings()

    if args.command == "prompt":
        print(json.dumps(compare_prompts(args.question, settings), ensure_ascii=False, indent=2))
    elif args.command == "chat":
        print(json.dumps(
            run_chat(args.message, settings, system_prompt=args.system_prompt, model=args.model),
            ensure_ascii=False,
            indent=2,
        ))
    elif args.command == "embedding":
        print(json.dumps(compare_embeddings(args.texts, settings, model=args.model), ensure_ascii=False, indent=2))
    elif args.command == "decision":
        print(json.dumps(run_decision_recommendation(args.case, settings=settings), ensure_ascii=False, indent=2))
    else:
        cases = load_business_cases()
        outcome = run_business_embedding_lab(
            args.ticket,
            cases,
            settings,
            n_clusters=args.clusters,
            model=args.model,
        )
        print(json.dumps(outcome, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
