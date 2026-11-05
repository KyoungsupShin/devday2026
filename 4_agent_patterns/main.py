"""CLI entry points for the workflow lessons and local A2A Protocol servers."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PATTERN_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PATTERN_ROOT))

from src.agent_workflow.lesson_support.config import load_settings
from src.agent_loop_mcp.lab_core import run_food_mcp_loop
from src.agent_to_agent.catalog import AGENT_URLS, DEFAULT_REQUEST
from src.agent_to_agent.orchestration import run_handoff
from src.agent_to_agent_advanced.catalog import AGENT_URLS as ADVANCED_AGENT_URLS
from src.agent_workflow.lab_core import run_workflow


def _wait_for_cards(urls: dict[str, str], timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    remaining = set(urls)
    while remaining and time.monotonic() < deadline:
        for agent_id in list(remaining):
            try:
                with urlopen(
                    urls[agent_id] + "/.well-known/agent-card.json", timeout=1.0
                ) as response:
                    if response.status == 200:
                        remaining.remove(agent_id)
            except (URLError, TimeoutError):
                pass
        if remaining:
            time.sleep(0.15)
    if remaining:
        raise RuntimeError(
            "A2A Agent Card 준비 시간 초과: " + ", ".join(sorted(remaining))
        )


def _ensure_ports_available(urls: dict[str, str]) -> None:
    """Fail before spawning children when a previous local server owns a port."""
    occupied: list[str] = []
    for agent_id, url in urls.items():
        _, host_port = url.split("://", 1)
        host, port = host_port.rsplit(":", 1)
        try:
            with socket.create_connection((host, int(port)), timeout=0.2):
                occupied.append(f"{agent_id} ({host}:{port})")
        except OSError:
            pass
    if occupied:
        raise RuntimeError(
            "A2A Agent 포트가 이미 사용 중입니다. 이전 `fnb-a2a-local` 또는 개별 Agent 프로세스를 종료한 뒤 다시 실행하세요: "
            + ", ".join(occupied)
        )


def _run_local_a2a_servers(
    urls: dict[str, str] = AGENT_URLS, agent_command: str = "fnb-a2a-agent"
) -> None:
    """Start all F&B A2A server processes and clean them up on Ctrl+C."""
    processes: list[subprocess.Popen[str]] = []
    try:
        _ensure_ports_available(urls)
        for agent_id, url in urls.items():
            port = url.rsplit(":", 1)[1]
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        str(PATTERN_ROOT / "main.py"),
                        agent_command,
                        agent_id,
                        "--port",
                        port,
                    ],
                    cwd=ROOT,
                )
            )
        _wait_for_cards(urls)
        print("A2A Protocol 1.0 Agent 서버가 준비되었습니다. Ctrl+C로 모두 종료합니다.")
        for agent_id, url in urls.items():
            print(f"- {agent_id}: {url}/.well-known/agent-card.json")
        while all(process.poll() is None for process in processes):
            time.sleep(0.4)
        failed = [
            str(process.pid) for process in processes if process.poll() not in (None, 0)
        ]
        if failed:
            raise RuntimeError(
                "A2A Agent 서버가 비정상 종료했습니다: " + ", ".join(failed)
            )
    except KeyboardInterrupt:
        print("\nA2A Agent 서버를 종료합니다.")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def _run_single_fnb_a2a_agent(agent_id: str, host: str, port: int) -> None:
    import uvicorn
    from src.agent_to_agent.server import create_a2a_app

    uvicorn.run(create_a2a_app(agent_id, f"http://{host}:{port}"), host=host, port=port)


def _run_single_fnb_a2a_advanced_agent(agent_id: str, host: str, port: int) -> None:
    import uvicorn
    from src.agent_to_agent_advanced.server import create_a2a_app

    uvicorn.run(create_a2a_app(agent_id, f"http://{host}:{port}"), host=host, port=port)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    workflow_parser = commands.add_parser(
        "workflow", help="01: LLM-orchestrated food workflow"
    )
    workflow_parser.add_argument("request")
    workflow_parser.add_argument(
        "--min-margin",
        type=float,
        default=0.0,
        help="minimum score margin before a route is considered ambiguous",
    )
    loop_parser = commands.add_parser(
        "loop", help="02: LLM-orchestrated graph with specialist Tool Calling"
    )
    loop_parser.add_argument("request")
    fnb_handoff_parser = commands.add_parser(
        "fnb-a2a",
        help="03: F&B procurement, material/planning, Cost Center, and ERP-change handoff",
    )
    fnb_handoff_parser.add_argument(
        "request",
        nargs="?",
        default=DEFAULT_REQUEST,
        help="F&B 운영변경 또는 구매 검토 요청",
    )
    commands.add_parser(
        "fnb-a2a-local",
        help="start all local F&B A2A Agent servers",
    )
    commands.add_parser(
        "fnb-a2a-advanced-local",
        help="04: start independent Advanced A2A Agent servers",
    )
    fnb_agent_parser = commands.add_parser(
        "fnb-a2a-agent", help="start one F&B A2A Agent server"
    )
    fnb_agent_parser.add_argument("agent_id", choices=sorted(AGENT_URLS))
    fnb_agent_parser.add_argument("--host", default="127.0.0.1")
    fnb_agent_parser.add_argument("--port", type=int, required=True)
    fnb_advanced_agent_parser = commands.add_parser(
        "fnb-a2a-advanced-agent", help="start one Advanced A2A Agent server"
    )
    fnb_advanced_agent_parser.add_argument(
        "agent_id", choices=sorted(ADVANCED_AGENT_URLS)
    )
    fnb_advanced_agent_parser.add_argument("--host", default="127.0.0.1")
    fnb_advanced_agent_parser.add_argument("--port", type=int, required=True)

    args = parser.parse_args()
    if args.command == "workflow":
        result = run_workflow(
            args.request,
            load_settings(),
            min_margin=args.min_margin,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "loop":
        result = run_food_mcp_loop(args.request, load_settings())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "fnb-a2a":
        result = run_handoff(args.request, settings=load_settings())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "fnb-a2a-local":
        _run_local_a2a_servers()
    elif args.command == "fnb-a2a-advanced-local":
        _run_local_a2a_servers(
            ADVANCED_AGENT_URLS, agent_command="fnb-a2a-advanced-agent"
        )
    elif args.command == "fnb-a2a-agent":
        _run_single_fnb_a2a_agent(args.agent_id, args.host, args.port)
    elif args.command == "fnb-a2a-advanced-agent":
        _run_single_fnb_a2a_advanced_agent(args.agent_id, args.host, args.port)


if __name__ == "__main__":
    main()
