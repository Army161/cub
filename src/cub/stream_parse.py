"""Best-effort extraction of human-readable snippets from Claude stream-json lines."""

from __future__ import annotations

import json
from typing import Any

_NOISE_EVENT_TYPES = {"rate_limit_event"}
_APPROVAL_MARKERS = (
    "requires approval",
    "needs your approval",
    "could you approve",
    "please approve",
)
_ASK_USER_QUESTION_TOOL_NAMES = {
    "askuserquestion",
    "ask_user_question",
    "ask-user-question",
}
_ASK_USER_QUESTION_MARKERS = (
    "answer questions?",
    "running askuserquestion",
    "running ask user question",
)
_GENERIC_TOOL_SUCCESS_MARKERS = (
    "todos have been modified successfully",
    "please proceed with the current tasks if applicable",
)

def extract_text_snippet(line: str, max_chars: int = 240) -> str | None:
    """Return a compact, user-facing snippet from a JSON line if possible."""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None

    snippet = _extract_snippet(payload, depth=0)
    if not snippet:
        return None

    compact = " ".join(snippet.split())
    if not compact:
        return None
    return compact[:max_chars]


def _extract_snippet(value: Any, depth: int) -> str | None:
    if depth > 5:
        return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        lowered = text.lower()
        if any(marker in lowered for marker in _ASK_USER_QUESTION_MARKERS):
            return None
        if any(marker in lowered for marker in _APPROVAL_MARKERS):
            return "Waiting for command approval to continue."
        if any(marker in lowered for marker in _GENERIC_TOOL_SUCCESS_MARKERS):
            return None
        return text

    if isinstance(value, list):
        snippets: list[str] = []
        for item in value[:8]:
            extracted = _extract_snippet(item, depth + 1)
            if extracted and extracted not in snippets:
                snippets.append(extracted)
            if len(snippets) >= 2:
                break
        if not snippets:
            return None
        return " | ".join(snippets)

    if not isinstance(value, dict):
        return None

    event_type = str(value.get("type") or "").strip().lower()
    if event_type in _NOISE_EVENT_TYPES:
        return None

    if event_type == "tool_use":
        return _extract_tool_use(value, depth + 1)

    if event_type == "tool_result":
        return _extract_tool_result(value, depth + 1)

    if event_type == "text":
        return _extract_snippet(value.get("text"), depth + 1)

    if event_type in {"error", "warning"}:
        detail = _extract_snippet(value.get("message") or value.get("error"), depth + 1)
        if detail:
            prefix = "Warning" if event_type == "warning" else "Error"
            return f"{prefix}: {detail}"

    content = value.get("content")
    extracted_content = _extract_snippet(content, depth + 1)
    if extracted_content:
        return extracted_content

    for key in ("output_text", "message", "delta", "error", "result", "text"):
        extracted = _extract_snippet(value.get(key), depth + 1)
        if extracted:
            return extracted

    for nested_key in ("payload", "data", "event"):
        extracted = _extract_snippet(value.get(nested_key), depth + 1)
        if extracted:
            return extracted

    return None


def _extract_tool_use(value: dict[str, Any], depth: int) -> str | None:
    tool_name = str(value.get("name") or value.get("tool") or "tool").strip()
    tool_lower = tool_name.lower()
    tool_input = value.get("input") or value.get("arguments")

    if tool_lower in _ASK_USER_QUESTION_TOOL_NAMES:
        return None

    if tool_lower == "bash":
        command = _extract_bash_command(tool_input, depth + 1)
        if command:
            return f"Running bash: {command}"
        return "Running bash command."

    if tool_lower in {"edit", "str_replace_editor"}:
        return "Editing files."

    if tool_lower:
        return f"Running {tool_name}."
    return "Running tool."


def _extract_tool_result(value: dict[str, Any], depth: int) -> str | None:
    content = value.get("content")
    text = _extract_snippet(content, depth + 1)
    if not text:
        return

    lowered = text.lower()
    if any(marker in lowered for marker in _APPROVAL_MARKERS):
        return "Waiting for command approval to continue."
    if any(marker in lowered for marker in _GENERIC_TOOL_SUCCESS_MARKERS):
        return None
    return text


def _extract_bash_command(tool_input: Any, depth: int) -> str | None:
    if not isinstance(tool_input, dict):
        return _extract_snippet(tool_input, depth)

    for key in ("command", "cmd", "bash", "script"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    nested = _extract_snippet(tool_input, depth + 1)
    if not nested:
        return None
    return nested
