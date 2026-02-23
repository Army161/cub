"""Reminder scheduler loop built on top of persisted reminder rows."""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from cub.formatting import format_task_status
from cub.store import TaskStore

SendMessage = Callable[[int, str], Awaitable[None]]


class ReminderService:
    """Polls due reminders and pushes task status updates to Telegram."""

    def __init__(self, store: TaskStore, send_message: SendMessage, poll_seconds: float):
        self.store = store
        self.send_message = send_message
        self.poll_seconds = poll_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    def schedule_reminder(
        self,
        *,
        task_id: str,
        chat_id: int,
        user_id: int,
        due_at: float,
        note: str | None,
    ) -> int:
        return self.store.create_reminder(
            task_id=task_id,
            chat_id=chat_id,
            user_id=user_id,
            due_at=due_at,
            note=note,
        )

    async def _run_loop(self) -> None:
        while True:
            now = time.time()
            due = self.store.due_reminders(now=now)
            for reminder in due:
                await self._handle_due(reminder)
            await asyncio.sleep(self.poll_seconds)

    async def _handle_due(self, reminder: dict) -> None:
        task_id = reminder["task_id"]
        chat_id = int(reminder["chat_id"])
        note = (reminder.get("note") or "").strip()

        task = self.store.get_task(task_id)
        if not task:
            await self.send_message(chat_id, f"Reminder: task {task_id} no longer exists")
            self.store.mark_reminder_sent(int(reminder["id"]))
            return

        events = self.store.recent_events(task_id, limit=10)
        status_text = format_task_status(task, events)
        header = f"Reminder for task {task_id}"
        if note:
            header += f" ({note})"

        await self.send_message(chat_id, f"{header}\n\n{status_text}")
        self.store.mark_reminder_sent(int(reminder["id"]))
