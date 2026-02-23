# Developer Guide

This guide is for contributors building features on top of Cub.

## Goals

Cub is a Telegram-first personal assistant with two paths:

- Fast path: quick replies through front assistant routing.
- Slow path: delegated Claude CLI tasks running in the background.

The design target is responsiveness first, with durable task tracking.

## Repository Layout

- `src/cub/main.py`: startup wiring.
- `src/cub/bot.py`: Telegram handlers, routing, chat UX.
- `src/cub/smart_assistant.py`: front assistant decision logic and formatting.
- `src/cub/task_runner.py`: background delegated task runtime.
- `src/cub/store.py`: SQLite persistence and schema migration.
- `src/cub/reminders.py`: reminder scheduler.
- `src/cub/stream_parse.py`: Claude stream-json parsing to user snippets.
- `src/cub/settings.py`: env configuration parsing and defaults.
- `src/cub/state_reset.py`: local state reset utility.
- `tests/`: unit tests.

## Runtime Model

### 1) Chat Context

Cub keeps chat memory in `chat_messages` (SQLite), keyed by Telegram `chat_id`.

### 2) Front Assistant Session

When `FRONT_ASSISTANT_PROVIDER=claude_cli`, Cub keeps a persistent per-chat
front session id (`chat_sessions.front_session_id`) and resumes it for fast replies.

### 3) Delegated Task Sessions

Each delegated task stores `claude_session_id` in `tasks`.
This enables follow-up probing via `/probe` or natural-language probe intents.

## Request Flow

1. Telegram update enters `bot.py:on_text` or command handler.
2. Control intents (`cancel`, `mute`, `probe`) are handled locally.
3. Otherwise, front assistant decides `reply` vs `delegate`.
4. Delegate path creates a task row and launches Claude CLI subprocess.
5. Progress/final events stream back to chat and are persisted.

## Adding Features

### Add a new bot command

1. Implement handler method in `src/cub/bot.py`.
2. Register in `_register_handlers()`.
3. Add a `BotCommand` in `_post_init()`.
4. Add or update tests.

### Add a new control intent

1. Extend `TextIntent` and regex/parser logic in `src/cub/text_intents.py`.
2. Handle action in `TelegramAssistantBot._handle_control_intent`.
3. Add tests in `tests/test_text_intents.py`.

### Add new persistence fields

1. Update table definition in `TaskStore._init_schema`.
2. Add migration in a guarded `_ensure_*_columns` helper.
3. Cover migration path in tests (legacy schema setup + open store).

## Safety and Reliability Rules

- Do not run destructive shell commands by default.
- Keep delegated tasks cancellable.
- Keep progress output low-noise for end users.
- Treat invalid/failed front assistant decisions as delegate fallback.
- Avoid relying only on in-memory state for task identity/status.

## Local Development

```bash
make setup
make lint
make test
make run
```

Run the reset utility when you need a clean local state:

```bash
uv run cub-reset --yes
```

Preview only:

```bash
uv run cub-reset --dry-run
```

## Configuration Notes

- Workspace target for delegated tasks:
  - `WORKSPACE_DIR` if set and non-empty.
  - else `CUB_WORK_ROOT`.
  - else `$CUB_HOME/work`.
- Keep `.env.example` in sync with `Settings.from_env()`.

## Open Source Readiness Checklist

- `uv run ruff check src tests` passes.
- `uv run pytest -q` passes.
- README reflects command/env behavior.
- New features include tests and migration coverage if schema changed.
- No secrets or machine-local paths committed.
