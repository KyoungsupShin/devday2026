"""CLI entry points for Orchestration and grounding core workflows."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "1_gen_ai_hub" / "src"), str(Path(__file__).resolve().parent)]

from lab_common.config import load_settings
from src.grounding.lab_core import run_help_grounded_query
from src.orchestration.lab_core import (
    run_orchestration,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    orchestration = commands.add_parser("orchestration", help="01: run prompt templating")
    orchestration.add_argument("query")
    grounding = commands.add_parser("grounding", help="02: ask SAP Help grounding")
    grounding.add_argument("query")
    args = parser.parse_args()
    settings = load_settings()

    if args.command == "orchestration":
        print(run_orchestration(args.query, settings))
    elif args.command == "grounding":
        print(run_help_grounded_query(args.query, settings))


if __name__ == "__main__":
    main()
