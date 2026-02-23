import asyncio
import sys
import time
from pathlib import Path

from cub.bot import TelegramAssistantBot
from cub.models import FINAL_STATUSES, TASK_COMPLETED, TASK_RUNNING
from cub.settings import Settings
from cub.store import TaskStore
from cub.task_runner import ClaudeTaskRunner


def _clear_env(monkeypatch) -> None:
    keys = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CONNECTION_POOL_SIZE",
        "TELEGRAM_POOL_TIMEOUT_SECONDS",
        "TELEGRAM_MAX_CONCURRENT_UPDATES",
        "TELEGRAM_DROP_PENDING_UPDATES",
        "TELEGRAM_RENDER_MODE",
        "ALLOWED_USER_IDS",
        "CUB_HOME",
        "CUB_STATE_DIR",
        "CUB_MIND_DIR",
        "CUB_WORK_ROOT",
        "ASSISTANT_DB_PATH",
        "WORKSPACE_DIR",
        "CLAUDE_COMMAND",
        "CLAUDE_ARGS",
        "FRONT_ASSISTANT_PROVIDER",
        "FRONT_ASSISTANT_MODEL",
        "FRONT_ASSISTANT_TIMEOUT_SECONDS",
        "FRONT_ASSISTANT_CONTEXT_MESSAGES",
        "FRONT_ASSISTANT_TOOL_MODE",
        "FRONT_ASSISTANT_MAX_TURNS",
        "FRONT_CLAUDE_COMMAND",
        "FRONT_CLAUDE_ARGS",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "LOG_LEVEL",
        "HTTP_LOG_LEVEL",
        "PROGRESS_UPDATE_SECONDS",
        "PROGRESS_FORMATTER",
        "TASK_RESULT_FORMATTER",
        "REMINDER_POLL_SECONDS",
        "MAX_EVENT_LINE_CHARS",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_bot_uses_configured_max_concurrent_updates(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("TELEGRAM_MAX_CONCURRENT_UPDATES", "11")
    settings = Settings.from_env()

    store = TaskStore(settings.db_path)
    try:
        bot = TelegramAssistantBot(settings, store)
        assert bot.app.update_processor.max_concurrent_updates == 11
    finally:
        store.close()


def test_task_runner_executes_delegated_tasks_concurrently(monkeypatch, tmp_path: Path) -> None:
    worker_script = tmp_path / "fake_claude.py"
    worker_script.write_text(
        "import time\n"
        "time.sleep(0.6)\n"
        "print('ok')\n",
        encoding="utf-8",
    )

    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("CLAUDE_COMMAND", sys.executable)
    monkeypatch.setenv("CLAUDE_ARGS", f"\"{worker_script}\"")
    monkeypatch.setenv("PROGRESS_UPDATE_SECONDS", "60")
    settings = Settings.from_env()
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)

    store = TaskStore(settings.db_path)

    async def send_message(_chat_id: int, _text: str) -> None:
        return None

    runner = ClaudeTaskRunner(store, settings, send_message)

    async def wait_final(task_id: str, timeout_seconds: float = 8.0) -> dict:
        deadline = time.monotonic() + timeout_seconds
        while True:
            task = store.get_task(task_id)
            if task and task["status"] in FINAL_STATUSES:
                return task
            if time.monotonic() > deadline:
                raise TimeoutError(f"timed out waiting for task {task_id}")
            await asyncio.sleep(0.03)

    async def scenario() -> tuple[dict, dict]:
        task1 = await runner.queue_task(
            chat_id=100,
            user_id=1,
            prompt="first",
            label="first",
        )
        task2 = await runner.queue_task(
            chat_id=100,
            user_id=1,
            prompt="second",
            label="second",
        )
        final1, final2 = await asyncio.gather(wait_final(task1["id"]), wait_final(task2["id"]))
        await runner.close()
        return final1, final2

    try:
        final1, final2 = asyncio.run(scenario())
    finally:
        store.close()

    assert final1["status"] == TASK_COMPLETED
    assert final2["status"] == TASK_COMPLETED
    assert final1["started_at"] is not None
    assert final2["started_at"] is not None

    start_delta = abs(float(final1["started_at"]) - float(final2["started_at"]))
    assert start_delta < 0.45


def test_task_runner_close_force_stops_stubborn_process(monkeypatch, tmp_path: Path) -> None:
    worker_script = tmp_path / "ignore_term.py"
    worker_script.write_text(
        "import signal\n"
        "import time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )

    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("CLAUDE_COMMAND", sys.executable)
    monkeypatch.setenv("CLAUDE_ARGS", f"\"{worker_script}\"")
    monkeypatch.setenv("PROGRESS_UPDATE_SECONDS", "60")
    settings = Settings.from_env()
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)

    store = TaskStore(settings.db_path)

    async def send_message(_chat_id: int, _text: str) -> None:
        return None

    runner = ClaudeTaskRunner(store, settings, send_message)

    async def wait_for_running(task_id: str, timeout_seconds: float = 4.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while True:
            task = store.get_task(task_id)
            if task and task["status"] == TASK_RUNNING:
                return
            if time.monotonic() > deadline:
                raise TimeoutError(f"timed out waiting for task {task_id} to start")
            await asyncio.sleep(0.03)

    async def scenario() -> None:
        task = await runner.queue_task(
            chat_id=101,
            user_id=1,
            prompt="long",
            label="long",
        )
        await wait_for_running(task["id"])
        await asyncio.wait_for(runner.close(), timeout=6.5)

    try:
        asyncio.run(scenario())
    finally:
        store.close()
