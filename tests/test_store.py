import sqlite3
from pathlib import Path

from cub.models import TASK_CANCELED, TASK_COMPLETED, TASK_RUNNING
from cub.store import TaskStore


def test_task_lifecycle(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "assistant.db")
    try:
        task = store.create_task(
            chat_id=123,
            user_id=999,
            prompt="do work",
            label="do work",
            command="claude -p do work",
            cwd=str(tmp_path),
        )

        assert task["status"] == "queued"
        assert task["claude_session_id"] is None

        store.set_task_running(task["id"], pid=42)
        running = store.get_task(task["id"])
        assert running is not None
        assert running["status"] == TASK_RUNNING
        assert running["pid"] == 42

        store.append_event(task["id"], "stdout", '{"text":"hello"}', "hello")
        events = store.recent_events(task["id"], limit=5)
        assert len(events) == 1
        assert events[0]["parsed_text"] == "hello"

        store.finish_task(task["id"], status=TASK_COMPLETED, exit_code=0, error=None)
        done = store.get_task(task["id"])
        assert done is not None
        assert done["status"] == TASK_COMPLETED
        assert done["exit_code"] == 0
    finally:
        store.close()


def test_task_persists_claude_session_id(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "assistant.db")
    try:
        task = store.create_task(
            chat_id=4,
            user_id=9,
            prompt="probe status",
            label="probe status",
            command="claude --resume abc -p probe",
            cwd=str(tmp_path),
            claude_session_id="session-123",
        )
        assert task["claude_session_id"] == "session-123"
    finally:
        store.close()


def test_store_migrates_legacy_tasks_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "assistant.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                prompt TEXT NOT NULL,
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
        conn.commit()
    finally:
        conn.close()

    store = TaskStore(db_path)
    try:
        task = store.create_task(
            chat_id=12,
            user_id=34,
            prompt="do work",
            label="do work",
            command="claude -p do work",
            cwd=str(tmp_path),
            claude_session_id="session-migrated",
        )
        assert task["claude_session_id"] == "session-migrated"
    finally:
        store.close()


def test_list_tasks_only_active(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "assistant.db")
    try:
        active_task = store.create_task(
            chat_id=77,
            user_id=1,
            prompt="running task",
            label="running task",
            command="claude -p running task",
            cwd=str(tmp_path),
        )
        done_task = store.create_task(
            chat_id=77,
            user_id=1,
            prompt="done task",
            label="done task",
            command="claude -p done task",
            cwd=str(tmp_path),
        )
        canceled_task = store.create_task(
            chat_id=77,
            user_id=1,
            prompt="canceled task",
            label="canceled task",
            command="claude -p canceled task",
            cwd=str(tmp_path),
        )

        store.set_task_running(active_task["id"], pid=1234)
        store.finish_task(done_task["id"], status=TASK_COMPLETED, exit_code=0, error=None)
        store.finish_task(canceled_task["id"], status=TASK_CANCELED, exit_code=None, error="canceled")

        all_tasks = store.list_tasks(77, limit=10)
        active_only = store.list_tasks(77, limit=10, only_active=True)

        assert len(all_tasks) == 3
        assert len(active_only) == 1
        assert active_only[0]["id"] == active_task["id"]
        assert active_only[0]["status"] == TASK_RUNNING
    finally:
        store.close()


def test_reminder_due_flow(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "assistant.db")
    try:
        task = store.create_task(
            chat_id=1,
            user_id=2,
            prompt="x",
            label="x",
            command="claude -p x",
            cwd=str(tmp_path),
        )
        reminder_id = store.create_reminder(
            task_id=task["id"],
            chat_id=1,
            user_id=2,
            due_at=100.0,
            note="check",
        )

        due = store.due_reminders(now=101.0)
        assert len(due) == 1
        assert due[0]["id"] == reminder_id

        store.mark_reminder_sent(reminder_id)
        due_after = store.due_reminders(now=999.0)
        assert due_after == []
    finally:
        store.close()


def test_chat_message_history(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "assistant.db")
    try:
        store.append_chat_message(123, "user", "What is 7 + 5?")
        store.append_chat_message(123, "assistant", "7 + 5 = 12.")
        store.append_chat_message(123, "user", "add 2 to it")

        items = store.recent_chat_messages(123, limit=10)
        assert len(items) == 3
        assert [x["role"] for x in items] == ["user", "assistant", "user"]
        assert items[-1]["content"] == "add 2 to it"
    finally:
        store.close()


def test_chat_progress_mute_preference(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "assistant.db")
    try:
        chat_id = 987
        assert store.updates_muted(chat_id) is False

        store.set_updates_muted(chat_id, True)
        assert store.updates_muted(chat_id) is True

        store.set_updates_muted(chat_id, False)
        assert store.updates_muted(chat_id) is False
    finally:
        store.close()


def test_front_session_id_persistence_and_reset(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "assistant.db")
    try:
        chat_id = 55
        first = store.get_or_create_front_session_id(chat_id)
        second = store.get_or_create_front_session_id(chat_id)
        assert first == second

        replaced = store.reset_front_session_id(chat_id)
        assert replaced != first
        current = store.get_or_create_front_session_id(chat_id)
        assert current == replaced
    finally:
        store.close()
