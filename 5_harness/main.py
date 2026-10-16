"""CLI entry points for the Harness core demonstrations."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "shared"), str(Path(__file__).resolve().parent)]

from src.deepagents import deepagents_readiness, make_agent_plan
from src.delegation_a2a import run_delegation_a2a
from src.reranker import FAST_ROUTE_CANDIDATES, SPECIALIST_CANDIDATES, decide


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    route = commands.add_parser("route", help="01: locally test routing")
    route.add_argument("request")
    plan = commands.add_parser("deepagents", help="02: inspect plan and local readiness")
    plan.add_argument("request")
    delegation = commands.add_parser("delegation", help="03: run in-memory A2A delegation")
    delegation.add_argument("request")
    args = parser.parse_args()
    if args.command == "route":
        result = {"fast_route": decide(args.request, FAST_ROUTE_CANDIDATES).__dict__, "specialist": decide(args.request, SPECIALIST_CANDIDATES).__dict__}
    elif args.command == "deepagents":
        result = {"readiness": deepagents_readiness(), "plan": make_agent_plan(args.request)}
    else:
        result = run_delegation_a2a(args.request)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
