"""CLI entry points for workflow, agent-loop, and A2A core demonstrations."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "shared"), str(Path(__file__).resolve().parent)]

from lab_common.config import load_settings
from src.a2a import run_food_handoff
from src.agent_loop import run_food_mcp_loop
from src.workflow import run_workflow


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (("workflow", "01: fixed food workflow"), ("loop", "02: fixed graph with specialist Tool Calling"), ("a2a", "03: Food Researcher to Launch Advisor handoff")):
        item = commands.add_parser(command, help=help_text)
        item.add_argument("request")
        if command == "workflow":
            item.add_argument("--min-margin", type=float, default=0.0, help="minimum score margin before a route is considered ambiguous")
    args = parser.parse_args()
    if args.command == "workflow":
        result = run_workflow(args.request, load_settings(), min_margin=args.min_margin)
    elif args.command == "loop":
        result = run_food_mcp_loop(args.request, load_settings())
    else:
        result = run_food_handoff(args.request, load_settings())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
