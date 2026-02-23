"""Environment-driven runtime settings."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path


def _parse_user_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        ids.add(int(token))
    return ids


def _split_shell_args(raw: str) -> tuple[str, ...]:
    text = raw.strip()
    if not text:
        return ()
    try:
        return tuple(shlex.split(text))
    except ValueError as exc:
        raise ValueError(f"invalid shell args: {raw}") from exc


def _parse_log_level(name: str, default: str) -> str:
    level = os.getenv(name, default).strip().upper() or default
    allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if level not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(allowed))}")
    return level


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean: true/false, 1/0, yes/no, on/off")


def _path_from_env(name: str, default: Path | str) -> Path:
    raw = os.getenv(name, "").strip()
    value = raw or str(default)
    return Path(value).expanduser().resolve()


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from env vars."""

    cub_home: Path
    state_dir: Path
    mind_dir: Path
    work_root: Path
    telegram_bot_token: str
    telegram_connection_pool_size: int
    telegram_pool_timeout_seconds: float
    telegram_max_concurrent_updates: int
    telegram_drop_pending_updates: bool
    telegram_render_mode: str
    allowed_user_ids: set[int]
    db_path: Path
    workspace_dir: Path
    claude_command: str
    claude_args: tuple[str, ...]
    front_assistant_provider: str
    front_assistant_model: str
    front_assistant_timeout_seconds: float
    front_assistant_context_messages: int
    front_claude_command: str
    front_claude_args: tuple[str, ...]
    anthropic_api_key: str
    anthropic_base_url: str
    openrouter_api_key: str
    openrouter_base_url: str
    log_level: str
    http_log_level: str
    progress_update_seconds: int
    progress_formatter: str
    task_result_formatter: str
    reminder_poll_seconds: float
    max_line_chars: int

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        telegram_connection_pool_size = int(os.getenv("TELEGRAM_CONNECTION_POOL_SIZE", "16"))
        if telegram_connection_pool_size < 1:
            raise ValueError("TELEGRAM_CONNECTION_POOL_SIZE must be >= 1")
        telegram_pool_timeout_seconds = float(os.getenv("TELEGRAM_POOL_TIMEOUT_SECONDS", "5.0"))
        if telegram_pool_timeout_seconds <= 0:
            raise ValueError("TELEGRAM_POOL_TIMEOUT_SECONDS must be > 0")
        telegram_max_concurrent_updates = int(
            os.getenv("TELEGRAM_MAX_CONCURRENT_UPDATES", "8")
        )
        if telegram_max_concurrent_updates < 1:
            raise ValueError("TELEGRAM_MAX_CONCURRENT_UPDATES must be >= 1")
        telegram_drop_pending_updates = _parse_bool("TELEGRAM_DROP_PENDING_UPDATES", True)

        render_mode = os.getenv("TELEGRAM_RENDER_MODE", "markdown").strip().lower() or "markdown"
        if render_mode not in {"plain", "markdown"}:
            raise ValueError("TELEGRAM_RENDER_MODE must be either 'plain' or 'markdown'")

        allowed_raw = os.getenv("ALLOWED_USER_IDS", "").strip()
        allowed = _parse_user_ids(allowed_raw) if allowed_raw else set()

        cub_home = _path_from_env("CUB_HOME", "~/.cub")
        state_dir = _path_from_env("CUB_STATE_DIR", cub_home / "state")
        mind_dir = _path_from_env("CUB_MIND_DIR", cub_home / "mind")
        work_root = _path_from_env("CUB_WORK_ROOT", cub_home / "work")

        db_raw = os.getenv("ASSISTANT_DB_PATH", "").strip()
        if db_raw:
            db_path = Path(db_raw).expanduser().resolve()
        else:
            db_path = (state_dir / "assistant.db").resolve()

        workspace_raw = os.getenv("WORKSPACE_DIR", "").strip()
        if workspace_raw:
            workspace = Path(workspace_raw).expanduser().resolve()
        else:
            workspace = work_root

        claude_command = os.getenv("CLAUDE_COMMAND", "claude").strip() or "claude"
        claude_args = _split_shell_args(
            os.getenv("CLAUDE_ARGS", "--verbose --output-format stream-json")
        )

        provider = os.getenv("FRONT_ASSISTANT_PROVIDER", "none").strip().lower() or "none"
        allowed_providers = {"none", "anthropic", "openrouter", "claude_cli"}
        if provider not in allowed_providers:
            raise ValueError(
                f"FRONT_ASSISTANT_PROVIDER must be one of: {', '.join(sorted(allowed_providers))}"
            )

        if provider == "anthropic":
            front_model_default = "claude-3-5-haiku-latest"
        elif provider == "openrouter":
            front_model_default = "anthropic/claude-3.5-haiku"
        elif provider == "claude_cli":
            front_model_default = "haiku"
        else:
            front_model_default = "haiku"
        front_model = os.getenv("FRONT_ASSISTANT_MODEL", front_model_default).strip()
        front_timeout = float(os.getenv("FRONT_ASSISTANT_TIMEOUT_SECONDS", "4.0"))
        if front_timeout <= 0:
            raise ValueError("FRONT_ASSISTANT_TIMEOUT_SECONDS must be > 0")
        front_context_messages = int(os.getenv("FRONT_ASSISTANT_CONTEXT_MESSAGES", "80"))
        if front_context_messages < 10:
            raise ValueError("FRONT_ASSISTANT_CONTEXT_MESSAGES must be >= 10")
        front_claude_command = os.getenv("FRONT_CLAUDE_COMMAND", claude_command).strip() or claude_command
        front_claude_args = _split_shell_args(
            os.getenv("FRONT_CLAUDE_ARGS", "--dangerously-skip-permissions")
        )

        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        anthropic_base = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip()
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        openrouter_base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()

        if provider == "anthropic" and not anthropic_key:
            raise ValueError("ANTHROPIC_API_KEY is required when FRONT_ASSISTANT_PROVIDER=anthropic")
        if provider == "openrouter" and not openrouter_key:
            raise ValueError("OPENROUTER_API_KEY is required when FRONT_ASSISTANT_PROVIDER=openrouter")

        log_level = _parse_log_level("LOG_LEVEL", "INFO")
        http_log_level = _parse_log_level("HTTP_LOG_LEVEL", "WARNING")

        progress_seconds = int(os.getenv("PROGRESS_UPDATE_SECONDS", "8"))
        progress_formatter = os.getenv("PROGRESS_FORMATTER", "plain").strip().lower() or "plain"
        if progress_formatter not in {"plain", "assistant"}:
            raise ValueError("PROGRESS_FORMATTER must be either 'plain' or 'assistant'")
        task_result_formatter = (
            os.getenv("TASK_RESULT_FORMATTER", "assistant").strip().lower() or "assistant"
        )
        if task_result_formatter not in {"plain", "assistant"}:
            raise ValueError("TASK_RESULT_FORMATTER must be either 'plain' or 'assistant'")
        reminder_poll = float(os.getenv("REMINDER_POLL_SECONDS", "2"))
        max_line_chars = int(os.getenv("MAX_EVENT_LINE_CHARS", "12000"))

        if progress_seconds < 1:
            raise ValueError("PROGRESS_UPDATE_SECONDS must be >= 1")
        if reminder_poll <= 0:
            raise ValueError("REMINDER_POLL_SECONDS must be > 0")

        return cls(
            cub_home=cub_home,
            state_dir=state_dir,
            mind_dir=mind_dir,
            work_root=work_root,
            telegram_bot_token=token,
            telegram_connection_pool_size=telegram_connection_pool_size,
            telegram_pool_timeout_seconds=telegram_pool_timeout_seconds,
            telegram_max_concurrent_updates=telegram_max_concurrent_updates,
            telegram_drop_pending_updates=telegram_drop_pending_updates,
            telegram_render_mode=render_mode,
            allowed_user_ids=allowed,
            db_path=db_path,
            workspace_dir=workspace,
            claude_command=claude_command,
            claude_args=claude_args,
            front_assistant_provider=provider,
            front_assistant_model=front_model,
            front_assistant_timeout_seconds=front_timeout,
            front_assistant_context_messages=front_context_messages,
            front_claude_command=front_claude_command,
            front_claude_args=front_claude_args,
            anthropic_api_key=anthropic_key,
            anthropic_base_url=anthropic_base,
            openrouter_api_key=openrouter_key,
            openrouter_base_url=openrouter_base,
            log_level=log_level,
            http_log_level=http_log_level,
            progress_update_seconds=progress_seconds,
            progress_formatter=progress_formatter,
            task_result_formatter=task_result_formatter,
            reminder_poll_seconds=reminder_poll,
            max_line_chars=max_line_chars,
        )
