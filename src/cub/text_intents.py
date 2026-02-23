"""Lightweight intent parsing for chat control messages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

TASK_ID_RE = re.compile(r"\b([0-9a-f]{8})\b", re.IGNORECASE)

_MUTE_RE = re.compile(
    r"\b(?:mute|quiet|silence|shut up|stop)\b.*\b(?:update|updates|progress|notifications?)\b",
    re.IGNORECASE,
)
_UNMUTE_RE = re.compile(
    r"\b(?:unmute|resume|enable|turn on)\b.*\b(?:update|updates|progress|notifications?)\b",
    re.IGNORECASE,
)
_CANCEL_SIMPLE_RE = re.compile(
    r"^(?:please\s+)?(?P<verb>cancel|stop|terminate|kill)(?:\s+(?:the\s+)?)?"
    r"(?:(?:current|running|latest)\s+)?(?:task)?(?:\s+(?P<id>[0-9a-f]{8}))?"
    r"(?:\s+(?:now|please))?\s*$",
    re.IGNORECASE,
)
_CANCEL_WITH_TASK_RE = re.compile(
    r"\b(?P<verb>cancel|stop|terminate|kill)\b[\s\S]*?\btask(?:\s+id)?\s*(?P<id>[0-9a-f]{8})?\b",
    re.IGNORECASE,
)
_PROBE_RE = re.compile(
    r"^(?:please\s+)?(?:can\s+you\s+)?"
    r"(?P<verb>probe|check(?:\s+on)?|follow\s*up(?:\s+on)?|continue|resume)\s+"
    r"(?:(?:the\s+)?task(?:\s+id)?\s*)?(?P<id>[0-9a-f]{8})?"
    r"(?:\s*[:,-]?\s*(?P<query>.+))?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TextIntent:
    """Detected control intent from plain-text message."""

    action: Literal["cancel_task", "mute_updates", "unmute_updates", "probe_task", "continue_task"]
    task_id: str | None = None
    force: bool = False
    query: str | None = None


def parse_control_intent(text: str) -> TextIntent | None:
    """Detect local control intents before router delegation."""
    raw = text.strip()
    if not raw:
        return None
    lowered = raw.lower()

    if _UNMUTE_RE.search(raw):
        return TextIntent(action="unmute_updates")

    if _MUTE_RE.search(raw):
        return TextIntent(action="mute_updates")

    simple = _CANCEL_SIMPLE_RE.match(raw)
    if simple:
        verb = (simple.group("verb") or "").lower()
        task_id = _normalize_task_id(simple.group("id"))
        force = verb in {"kill", "terminate"} or "force" in lowered
        return TextIntent(action="cancel_task", task_id=task_id, force=force)

    with_task = _CANCEL_WITH_TASK_RE.search(raw)
    if with_task:
        verb = (with_task.group("verb") or "").lower()
        task_id = _normalize_task_id(with_task.group("id"))
        force = verb in {"kill", "terminate"} or "force" in lowered
        return TextIntent(action="cancel_task", task_id=task_id, force=force)

    if lowered in {"cancel", "stop", "kill", "terminate"}:
        force = lowered in {"kill", "terminate"}
        return TextIntent(action="cancel_task", force=force)

    probe = _PROBE_RE.match(raw)
    if probe:
        verb = (probe.group("verb") or "").strip().lower()
        task_id = _normalize_task_id(probe.group("id"))
        query = _normalize_query(probe.group("query"))
        action = "continue_task" if verb in {"continue", "resume"} else "probe_task"
        return TextIntent(action=action, task_id=task_id, query=query)

    return None


def find_task_id(text: str) -> str | None:
    match = TASK_ID_RE.search(text)
    if not match:
        return None
    return match.group(1).lower()


def _normalize_task_id(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower() or None


def _normalize_query(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip() or None
