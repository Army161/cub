"""SQLite persistence for tasks, stream events, and reminders."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from cub.models import (
    ACTIVE_STATUSES,
    FINAL_STATUSES,
    TASK_CANCELED,
    TASK_FAILED,
    TASK_QUEUED,
    TASK_RUNNING,
)


class TaskStore:
    """Thread-safe SQLite store used by bot runtime."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    claude_session_id TEXT,
                    status TEXT NOT NULL,
                    command TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    updated_at REAL NOT NULL,
                    finished_at REAL,
                    pid INTEGER,
                    exit_code INTEGER,
                    error TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    ts REAL NOT NULL,
                    stream TEXT NOT NULL,
                    raw_line TEXT NOT NULL,
                    parsed_text TEXT,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id, id)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    due_at REAL NOT NULL,
                    note TEXT,
                    sent INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    sent_at REAL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(sent, due_at)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_id ON chat_messages(chat_id, id)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_preferences (
                    chat_id INTEGER PRIMARY KEY,
                    updates_muted INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    chat_id INTEGER PRIMARY KEY,
                    front_session_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._ensure_tasks_columns()
            self._conn.commit()

    def _ensure_tasks_columns(self) -> None:
        rows = self._conn.execute("PRAGMA table_info(tasks)").fetchall()
        names = {str(row["name"]) for row in rows}
        if "claude_session_id" not in names:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN claude_session_id TEXT")

    def mark_inflight_as_failed(self, reason: str = "Process interrupted") -> int:
        """Recover from restart by marking queued/running tasks as failed."""
        now = time.time()
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        params = [TASK_FAILED, reason, now, now, *sorted(ACTIVE_STATUSES)]
        with self._lock:
            cur = self._conn.execute(
                f"""
                UPDATE tasks
                SET status = ?, error = ?, finished_at = ?, updated_at = ?
                WHERE status IN ({placeholders})
                """,
                params,
            )
            self._conn.commit()
            return cur.rowcount

    def create_task(
        self,
        chat_id: int,
        user_id: int,
        prompt: str,
        label: str,
        command: str,
        cwd: str,
        claude_session_id: str | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        task_id = self._new_task_id()

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO tasks (
                    id, chat_id, user_id, label, prompt, claude_session_id, status, command, cwd,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    chat_id,
                    user_id,
                    label,
                    prompt,
                    claude_session_id,
                    TASK_QUEUED,
                    command,
                    cwd,
                    now,
                    now,
                ),
            )
            self._conn.commit()

        task = self.get_task(task_id)
        if not task:
            raise RuntimeError("failed to persist task")
        return task

    def _new_task_id(self) -> str:
        while True:
            value = uuid.uuid4().hex[:8]
            with self._lock:
                row = self._conn.execute("SELECT id FROM tasks WHERE id = ?", (value,)).fetchone()
            if not row:
                return value

    def set_task_running(self, task_id: str, pid: int | None) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                UPDATE tasks
                SET status = ?, pid = ?, started_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (TASK_RUNNING, pid, now, now, task_id),
            )
            self._conn.commit()

    def append_event(
        self,
        task_id: str,
        stream: str,
        raw_line: str,
        parsed_text: str | None,
        *,
        max_chars: int = 12000,
    ) -> None:
        now = time.time()
        trimmed_raw = raw_line[:max_chars]
        trimmed_parsed = (parsed_text or "")[:max_chars] or None

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO task_events (task_id, ts, stream, raw_line, parsed_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, now, stream, trimmed_raw, trimmed_parsed),
            )
            self._conn.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (now, task_id))
            self._conn.commit()

    def finish_task(
        self,
        task_id: str,
        *,
        status: str,
        exit_code: int | None,
        error: str | None,
    ) -> None:
        if status not in FINAL_STATUSES:
            raise ValueError(f"invalid final status: {status}")

        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                UPDATE tasks
                SET status = ?, exit_code = ?, error = ?, finished_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, exit_code, error, now, now, task_id),
            )
            self._conn.commit()

    def cancel_task(self, task_id: str, reason: str = "Canceled by user") -> bool:
        """Set task to canceled if not already final."""
        now = time.time()
        placeholders = ",".join("?" for _ in FINAL_STATUSES)
        params = [TASK_CANCELED, reason, now, now, task_id, *sorted(FINAL_STATUSES)]
        with self._lock:
            cur = self._conn.execute(
                f"""
                UPDATE tasks
                SET status = ?, error = ?, finished_at = ?, updated_at = ?
                WHERE id = ? AND status NOT IN ({placeholders})
                """,
                params,
            )
            self._conn.commit()
            return cur.rowcount > 0

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def latest_task_for_chat(self, chat_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE chat_id = ? ORDER BY created_at DESC LIMIT 1",
                (chat_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_tasks(self, chat_id: int, *, limit: int = 10, only_active: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM tasks WHERE chat_id = ?"
        params: list[Any] = [chat_id]

        if only_active:
            placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
            query += f" AND status IN ({placeholders})"
            params.extend(sorted(ACTIVE_STATUSES))

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def recent_events(self, task_id: str, *, limit: int = 12) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, ts, stream, raw_line, parsed_text
                FROM task_events
                WHERE task_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()

        events = [dict(row) for row in rows]
        events.reverse()
        return events

    def create_reminder(
        self,
        task_id: str,
        chat_id: int,
        user_id: int,
        due_at: float,
        note: str | None = None,
    ) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO reminders (task_id, chat_id, user_id, due_at, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, chat_id, user_id, due_at, note, now),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def due_reminders(self, *, now: float | None = None, limit: int = 30) -> list[dict[str, Any]]:
        target = now if now is not None else time.time()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM reminders
                WHERE sent = 0 AND due_at <= ?
                ORDER BY due_at ASC
                LIMIT ?
                """,
                (target, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_reminder_sent(self, reminder_id: int) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE reminders SET sent = 1, sent_at = ? WHERE id = ?",
                (now, reminder_id),
            )
            self._conn.commit()

    def append_chat_message(
        self,
        chat_id: int,
        role: str,
        content: str,
        *,
        max_chars: int = 8000,
    ) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")
        text = (content or "").strip()
        if not text:
            return

        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO chat_messages (chat_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, role, text[:max_chars], now),
            )
            self._conn.commit()

    def recent_chat_messages(self, chat_id: int, *, limit: int = 8) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, chat_id, role, content, created_at
                FROM chat_messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()

        items = [dict(row) for row in rows]
        items.reverse()
        return items

    def updates_muted(self, chat_id: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT updates_muted FROM chat_preferences WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if not row:
            return False
        return bool(row["updates_muted"])

    def set_updates_muted(self, chat_id: int, muted: bool) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO chat_preferences (chat_id, updates_muted, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id)
                DO UPDATE SET updates_muted = excluded.updates_muted, updated_at = excluded.updated_at
                """,
                (chat_id, 1 if muted else 0, now),
            )
            self._conn.commit()

    def get_or_create_front_session_id(self, chat_id: int) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT front_session_id FROM chat_sessions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if row:
                return str(row["front_session_id"])

            now = time.time()
            session_id = str(uuid.uuid4())
            self._conn.execute(
                """
                INSERT INTO chat_sessions (chat_id, front_session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, session_id, now, now),
            )
            self._conn.commit()
            return session_id

    def reset_front_session_id(self, chat_id: int) -> str:
        now = time.time()
        session_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO chat_sessions (chat_id, front_session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id)
                DO UPDATE SET front_session_id = excluded.front_session_id, updated_at = excluded.updated_at
                """,
                (chat_id, session_id, now, now),
            )
            self._conn.commit()
        return session_id
