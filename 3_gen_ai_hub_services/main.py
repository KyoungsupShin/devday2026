"""CLI entry points for Orchestration, grounding, and memory core workflows."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "shared"), str(Path(__file__).resolve().parent)]

from lab_common.config import load_settings
from src.service_core import MemoryChatbot, configured_document_repository, run_grounded_query, run_orchestration


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    orchestration = commands.add_parser("orchestration", help="01: run prompt templating")
    orchestration.add_argument("query")
    grounding = commands.add_parser("grounding", help="02: ask SAP Help grounding")
    grounding.add_argument("query")
    documents = commands.add_parser("documents", help="03: ask configured vector grounding")
    documents.add_argument("query")
    memory = commands.add_parser("memory", help="04: run a sequence with memory")
    memory.add_argument("messages", nargs="+", help="messages to send in order")
    args = parser.parse_args()
    settings = load_settings()

    if args.command == "orchestration":
        print(run_orchestration(args.query, settings))
    elif args.command == "grounding":
        print(run_grounded_query(args.query, settings))
    elif args.command == "documents":
        print(run_grounded_query(args.query, settings, repository_type="vector", repository_id=configured_document_repository()))
    else:
        bot = MemoryChatbot(settings)
        for message in args.messages:
            print(f"user: {message}\nassistant: {bot.chat(message)}\n")


if __name__ == "__main__":
    main()
