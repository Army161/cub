"""Parse human-friendly reminder times."""

from __future__ import annotations

import re
import time
from datetime import datetime

_DURATION_RE = re.compile(
    r"^\s*(?:in\s+)?(?P<value>\d+)\s*(?P<unit>s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\s*$",
    re.IGNORECASE,
)


_UNIT_TO_SECONDS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
}


def parse_when(spec: str, *, now: float | None = None) -> float:
    """Parse reminder time into UNIX timestamp seconds.

    Accepted formats:
    - duration: 5m, in 2 hours, 1d
    - ISO datetime: 2026-02-22T18:30
    """
    if not spec or not spec.strip():
        raise ValueError("time expression is empty")

    base_now = now if now is not None else time.time()
    raw = spec.strip()

    match = _DURATION_RE.match(raw)
    if match:
        value = int(match.group("value"))
        unit = match.group("unit").lower()
        seconds = value * _UNIT_TO_SECONDS[unit]
        return base_now + seconds

    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"unsupported time expression: {spec}") from exc

    ts = dt.timestamp()
    if ts <= base_now:
        raise ValueError("time must be in the future")
    return ts
