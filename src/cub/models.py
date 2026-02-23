"""Shared data models and constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

TASK_QUEUED: Final[str] = "queued"
TASK_RUNNING: Final[str] = "running"
TASK_COMPLETED: Final[str] = "completed"
TASK_FAILED: Final[str] = "failed"
TASK_CANCELED: Final[str] = "canceled"

ACTIVE_STATUSES: Final[set[str]] = {TASK_QUEUED, TASK_RUNNING}
FINAL_STATUSES: Final[set[str]] = {TASK_COMPLETED, TASK_FAILED, TASK_CANCELED}


@dataclass(frozen=True)
class TaskStatusView:
    """Convenient subset of task fields for rendering status."""

    id: str
    status: str
    label: str
    created_at: float
    started_at: float | None
    finished_at: float | None
    exit_code: int | None
    error: str | None
