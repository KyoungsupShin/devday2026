"""CLI entry point for the cross-team LLM core workflow."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "shared"), str(Path(__file__).resolve().parent)]

from lab_common.config import load_settings
from src.cross_team_chat import run_cross_team_chat


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help="operations request for both teams")
    args = parser.parse_args()
    print(json.dumps(run_cross_team_chat(args.request, settings=load_settings()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
