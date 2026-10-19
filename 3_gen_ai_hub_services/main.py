"""CLI entry points for Orchestration, grounding, and memory core workflows."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "shared"), str(Path(__file__).resolve().parent)]

from lab_common.config import load_settings
from src.documents.lab_core import configured_document_repository, run_document_grounded_query
from src.grounding.lab_core import run_help_grounded_query
from src.memory.lab_core import MemoryChatbot
from src.orchestration.lab_core import (
    delete_orchestration_config,
    get_orchestration_config,
    invoke_saved_orchestration_config,
    run_orchestration,
    save_orchestration_config,
)


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
    registry = commands.add_parser("orchestration-config", help="manage saved Prompt Registry configs")
    registry_commands = registry.add_subparsers(dest="registry_command", required=True)
    registry_save = registry_commands.add_parser("save", help="create or update a saved config")
    registry_save.add_argument("--name", required=True)
    registry_save.add_argument("--version", required=True)
    registry_save.add_argument("--scenario", required=True)
    registry_save.add_argument("--system-prompt", required=True)
    registry_save.add_argument("--user-prompt", default="{{?user_query}}")
    registry_save.add_argument("--model")
    registry_save.add_argument("--max-tokens", type=int, default=700)
    registry_get = registry_commands.add_parser("get", help="read one saved config")
    registry_get.add_argument("config_id")
    registry_invoke = registry_commands.add_parser("invoke", help="invoke a saved config by ID")
    registry_invoke.add_argument("config_id")
    registry_invoke.add_argument("query")
    registry_delete = registry_commands.add_parser("delete", help="permanently delete a saved config")
    registry_delete.add_argument("config_id")
    args = parser.parse_args()
    settings = load_settings()

    if args.command == "orchestration-config":
        if args.registry_command == "save":
            print(save_orchestration_config(
                settings, name=args.name, version=args.version, scenario=args.scenario,
                system_prompt=args.system_prompt, user_prompt=args.user_prompt,
                model=args.model, max_tokens=args.max_tokens,
            ))
        elif args.registry_command == "get":
            print(get_orchestration_config(args.config_id))
        elif args.registry_command == "invoke":
            print(invoke_saved_orchestration_config(args.query, settings, config_id=args.config_id))
        else:
            print(delete_orchestration_config(args.config_id))
    elif args.command == "orchestration":
        print(run_orchestration(args.query, settings))
    elif args.command == "grounding":
        print(run_help_grounded_query(args.query, settings))
    elif args.command == "documents":
        print(run_document_grounded_query(args.query, settings, repository_id=configured_document_repository()))
    else:
        bot = MemoryChatbot(settings)
        for message in args.messages:
            print(f"user: {message}\nassistant: {bot.chat(message)}\n")


if __name__ == "__main__":
    main()
