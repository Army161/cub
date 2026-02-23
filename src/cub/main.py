"""CLI entrypoint for the Telegram assistant."""

from __future__ import annotations

import logging
import sys

from cub.bot import TelegramAssistantBot
from cub.dotenv import load_dotenv
from cub.reminders import ReminderService
from cub.settings import Settings
from cub.smart_assistant import SmartAssistant
from cub.store import TaskStore
from cub.task_runner import ClaudeTaskRunner


def main() -> None:
    load_dotenv()

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    for path in (settings.cub_home, settings.state_dir, settings.mind_dir, settings.workspace_dir):
        path.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    http_level = getattr(logging, settings.http_log_level)
    logging.getLogger("httpx").setLevel(http_level)
    logging.getLogger("httpcore").setLevel(http_level)

    store = TaskStore(settings.db_path)
    recovered = store.mark_inflight_as_failed()
    if recovered:
        logging.info("Recovered %s in-flight task(s) from previous run", recovered)

    bot = TelegramAssistantBot(settings, store)
    runner = ClaudeTaskRunner(store, settings, bot.send_text)
    reminders = ReminderService(store, bot.send_text, poll_seconds=settings.reminder_poll_seconds)
    assistant = SmartAssistant(settings, store)
    bot.bind_services(runner, reminders, assistant)

    try:
        bot.run()
    except KeyboardInterrupt:
        logging.info("Interrupted by user. Shutting down...")
    finally:
        store.close()


if __name__ == "__main__":
    main()
