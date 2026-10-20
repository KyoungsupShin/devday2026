"""CLI entry points for the Gen AI Hub environment core."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "1_gen_ai_hub" / "src"), str(Path(__file__).resolve().parent)]

from lab_common.config import load_settings
from src.environment import deployment_status, environment_status
from src.litellm_adapter import chat_completion, litellm_connection_status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["status", "deployments", "litellm-status", "litellm-chat"],
        help="status commands are local-only; deployments and litellm-chat call their configured service",
    )
    parser.add_argument("message", nargs="?", default="안녕하세요. 한 문장으로 자기소개해줘.")
    parser.add_argument("--model", default=None, help="LiteLLM model override (litellm-chat only)")
    args = parser.parse_args()
    settings = load_settings()
    if args.command == "status":
        result = environment_status(settings)
    elif args.command == "deployments":
        result = deployment_status(settings)
    elif args.command == "litellm-status":
        result = litellm_connection_status()
    else:
        result = {
            "model": args.model or litellm_connection_status()["model"],
            "reply": chat_completion([{"role": "user", "content": args.message}], model=args.model),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
