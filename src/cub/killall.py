"""CLI helper to kill Claude Code processes on the local machine."""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Sequence

from cub.dotenv import load_dotenv
from cub.task_runner import cleanup_claude_processes, format_process_cleanup_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kill Claude Code processes on this machine")
    parser.add_argument(
        "--graceful",
        action="store_true",
        help="Only send SIGTERM (skip force SIGKILL escalation)",
    )
    return parser


def _resolve_commands_from_env() -> tuple[str, str]:
    claude_command = os.getenv("CLAUDE_COMMAND", "claude").strip() or "claude"
    front_claude_command = (
        os.getenv("FRONT_CLAUDE_COMMAND", claude_command).strip() or claude_command
    )
    return claude_command, front_claude_command


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    claude_command, front_claude_command = _resolve_commands_from_env()
    force = not args.graceful
    report = asyncio.run(
        cleanup_claude_processes(
            claude_command,
            front_claude_command,
            force=force,
            exclude_pids={os.getpid()},
        )
    )
    print(format_process_cleanup_report(report, force=force, canceled_tasks=0))
    return 0 if report.remaining == 0 else 1


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
