"""Command-line entry point for the independent 02 Agent Loop lab."""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

from .lab_core import run_food_mcp_loop


def build_parser() -> argparse.ArgumentParser:
    """Build the small read-only CLI for the public 02 runtime API."""
    parser = argparse.ArgumentParser(description="Run the 02 Agent Loop with local read-only Tool Calling.")
    parser.add_argument("request", help="Food-business request for the Agent Loop")
    parser.add_argument(
        "--min-margin",
        type=float,
        default=0.0,
        help="Minimum router confidence margin before requesting clarification (default: 0.0)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    """Run the public loop API and print its JSON-friendly result."""
    args = build_parser().parse_args(argv)
    result = run_food_mcp_loop(args.request, min_margin=args.min_margin)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return result


if __name__ == "__main__":
    main()
