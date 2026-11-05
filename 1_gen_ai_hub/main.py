"""CLI entry points for the Gen AI Hub environment core."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.environment.lesson_support.config import load_settings
from src.environment.lab_core import deployment_status, environment_status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["status", "deployments"],
        help="status is local-only; deployments calls the configured AI Core service",
    )
    args = parser.parse_args()
    settings = load_settings()
    if args.command == "status":
        result = environment_status(settings)
    elif args.command == "deployments":
        result = deployment_status(settings)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
