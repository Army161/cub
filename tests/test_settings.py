from pathlib import Path

import pytest

from cub.settings import Settings


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


def test_settings_default_dirs_from_cub_home(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))

    settings = Settings.from_env()

    assert settings.cub_home == (tmp_path / "cub-home").resolve()
    assert settings.telegram_connection_pool_size == 16
    assert settings.telegram_pool_timeout_seconds == 5.0
    assert settings.telegram_max_concurrent_updates == 8
    assert settings.telegram_drop_pending_updates is True
    assert settings.state_dir == (tmp_path / "cub-home" / "state").resolve()
    assert settings.mind_dir == (tmp_path / "cub-home" / "mind").resolve()
    assert settings.work_root == (tmp_path / "cub-home" / "work").resolve()
    assert settings.db_path == (tmp_path / "cub-home" / "state" / "assistant.db").resolve()
    assert settings.workspace_dir == (tmp_path / "cub-home" / "work").resolve()


def test_settings_front_assistant_tool_mode_defaults_for_claude_cli(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("FRONT_ASSISTANT_PROVIDER", "claude_cli")

    settings = Settings.from_env()

    assert settings.front_assistant_tool_mode == "read_only"
    assert settings.front_assistant_max_turns == 2


def test_settings_front_assistant_tool_mode_defaults_for_non_claude(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("FRONT_ASSISTANT_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    settings = Settings.from_env()

    assert settings.front_assistant_tool_mode == "none"
    assert settings.front_assistant_max_turns == 1


def test_settings_legacy_db_and_workspace_override(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("ASSISTANT_DB_PATH", str(tmp_path / "legacy" / "assistant.db"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "legacy-work"))

    settings = Settings.from_env()

    assert settings.db_path == (tmp_path / "legacy" / "assistant.db").resolve()
    assert settings.workspace_dir == (tmp_path / "legacy-work").resolve()


def test_settings_custom_state_mind_and_work_roots(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("CUB_STATE_DIR", str(tmp_path / "state-a"))
    monkeypatch.setenv("CUB_MIND_DIR", str(tmp_path / "mind-a"))
    monkeypatch.setenv("CUB_WORK_ROOT", str(tmp_path / "work-a"))

    settings = Settings.from_env()

    assert settings.state_dir == (tmp_path / "state-a").resolve()
    assert settings.mind_dir == (tmp_path / "mind-a").resolve()
    assert settings.work_root == (tmp_path / "work-a").resolve()
    assert settings.db_path == (tmp_path / "state-a" / "assistant.db").resolve()
    assert settings.workspace_dir == (tmp_path / "work-a").resolve()


def test_settings_blank_path_overrides_fall_back_to_defaults(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("CUB_STATE_DIR", "")
    monkeypatch.setenv("CUB_MIND_DIR", "")
    monkeypatch.setenv("CUB_WORK_ROOT", "")
    monkeypatch.setenv("WORKSPACE_DIR", "")

    settings = Settings.from_env()

    assert settings.state_dir == (tmp_path / "cub-home" / "state").resolve()
    assert settings.mind_dir == (tmp_path / "cub-home" / "mind").resolve()
    assert settings.work_root == (tmp_path / "cub-home" / "work").resolve()
    assert settings.workspace_dir == (tmp_path / "cub-home" / "work").resolve()


def test_settings_telegram_runtime_tuning(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("TELEGRAM_CONNECTION_POOL_SIZE", "24")
    monkeypatch.setenv("TELEGRAM_POOL_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("TELEGRAM_MAX_CONCURRENT_UPDATES", "12")
    monkeypatch.setenv("TELEGRAM_DROP_PENDING_UPDATES", "false")

    settings = Settings.from_env()

    assert settings.telegram_connection_pool_size == 24
    assert settings.telegram_pool_timeout_seconds == 7.5
    assert settings.telegram_max_concurrent_updates == 12
    assert settings.telegram_drop_pending_updates is False


def test_settings_invalid_max_concurrent_updates_raises(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("TELEGRAM_MAX_CONCURRENT_UPDATES", "0")

    with pytest.raises(ValueError, match="TELEGRAM_MAX_CONCURRENT_UPDATES must be >= 1"):
        Settings.from_env()


def test_settings_shell_args_support_quotes(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv(
        "CLAUDE_ARGS",
        '--dangerously-skip-permissions --allowed-tools "Bash(git:*) Edit"',
    )

    settings = Settings.from_env()

    assert settings.claude_args == (
        "--dangerously-skip-permissions",
        "--allowed-tools",
        "Bash(git:*) Edit",
    )


def test_settings_invalid_front_assistant_tool_mode_raises(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("FRONT_ASSISTANT_PROVIDER", "claude_cli")
    monkeypatch.setenv("FRONT_ASSISTANT_TOOL_MODE", "all_tools")

    with pytest.raises(ValueError, match="FRONT_ASSISTANT_TOOL_MODE"):
        Settings.from_env()


def test_settings_invalid_front_assistant_max_turns_raises(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("FRONT_ASSISTANT_PROVIDER", "claude_cli")
    monkeypatch.setenv("FRONT_ASSISTANT_MAX_TURNS", "0")

    with pytest.raises(ValueError, match="FRONT_ASSISTANT_MAX_TURNS must be >= 1"):
        Settings.from_env()


def test_settings_invalid_shell_args_raise(monkeypatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("CUB_HOME", str(tmp_path / "cub-home"))
    monkeypatch.setenv("CLAUDE_ARGS", '"unterminated')

    with pytest.raises(ValueError, match="invalid shell args"):
        Settings.from_env()
