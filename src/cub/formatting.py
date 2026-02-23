"""Formatting helpers for chat responses."""

from __future__ import annotations

import time
from typing import Any


def format_ts(ts: float | None) -> str:
    if not ts:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def summarize_events(events: list[dict[str, Any]], max_lines: int = 6) -> str:
    lines: list[str] = []
    for event in events:
        text = (event.get("parsed_text") or "").strip()
        if text:
            if lines and text == lines[-1]:
                continue
            if text in lines[-3:]:
                continue
            lines.append(text)

    if not lines:
        return "(no parsed output yet)"

    tail = lines[-max_lines:]
    return "\n".join(f"- {line}" for line in tail)


def format_task_status(task: dict[str, Any], events: list[dict[str, Any]]) -> str:
    task_id = task["id"]
    label = task.get("label") or task_id
    session_id = str(task.get("claude_session_id") or "").strip()
    status = task.get("status", "unknown")
    exit_code = task.get("exit_code")
    error = task.get("error")

    lines = [
        f"Task {task_id} ({label})",
        f"Status: {status}",
        f"Created: {format_ts(task.get('created_at'))}",
        f"Started: {format_ts(task.get('started_at'))}",
        f"Finished: {format_ts(task.get('finished_at'))}",
        f"Exit code: {exit_code if exit_code is not None else '-'}",
    ]
    if session_id:
        lines.append(f"Session id: {session_id}")

    if error:
        lines.append(f"Error: {error}")

    lines.append("Recent output:")
    lines.append(summarize_events(events))
    return "\n".join(lines)


def format_task_list(tasks: list[dict[str, Any]], *, title: str = "Recent tasks:") -> str:
    if not tasks:
        return "No tasks yet in this chat."

    lines = [title]
    for task in tasks:
        session_id = str(task.get("claude_session_id") or "").strip()
        session_part = f"session={session_id[:8]}" if session_id else "session=-"
        lines.append(
            f"- {task['id']} | {task['status']} | {task.get('label', task['id'])} | "
            f"{session_part} | {format_ts(task.get('created_at'))}"
        )
    return "\n".join(lines)
