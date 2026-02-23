import cub.killall as killall_module
from cub.task_runner import ProcessCleanupReport, format_process_cleanup_report


def test_format_process_cleanup_report_with_no_matches() -> None:
    report = ProcessCleanupReport(
        matched=0,
        stopped=0,
        force_kill_attempts=0,
        permission_denied=0,
        remaining=0,
        term_signals_sent=0,
    )
    text = format_process_cleanup_report(report, force=True)
    assert text == "No Claude Code processes found."


def test_format_process_cleanup_report_with_summary_lines() -> None:
    report = ProcessCleanupReport(
        matched=4,
        stopped=3,
        force_kill_attempts=1,
        permission_denied=0,
        remaining=1,
        term_signals_sent=4,
    )
    text = format_process_cleanup_report(report, force=True, canceled_tasks=2)
    assert "Claude process cleanup complete." in text
    assert "- Matched: 4" in text
    assert "- Stopped: 3" in text
    assert "- Runner tasks canceled: 2" in text
    assert "- Force-kill attempts: 1" in text
    assert "- Still running: 1" in text


def test_killall_main_uses_graceful_mode(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CLAUDE_COMMAND", "claude")
    monkeypatch.setenv("FRONT_CLAUDE_COMMAND", "claude")

    called: dict[str, object] = {}

    async def fake_cleanup(
        claude_command: str,
        front_claude_command: str,
        *,
        force: bool,
        exclude_pids: set[int] | None = None,
    ) -> ProcessCleanupReport:
        called["claude_command"] = claude_command
        called["front_claude_command"] = front_claude_command
        called["force"] = force
        called["exclude_pids"] = exclude_pids
        return ProcessCleanupReport(
            matched=2,
            stopped=2,
            force_kill_attempts=0,
            permission_denied=0,
            remaining=0,
            term_signals_sent=2,
        )

    monkeypatch.setattr(killall_module, "cleanup_claude_processes", fake_cleanup)
    rc = killall_module.main(["--graceful"])
    out = capsys.readouterr().out

    assert rc == 0
    assert called["claude_command"] == "claude"
    assert called["front_claude_command"] == "claude"
    assert called["force"] is False
    assert isinstance(called["exclude_pids"], set)
    assert "Claude process cleanup complete." in out


def test_killall_main_returns_non_zero_when_processes_remain(monkeypatch) -> None:
    async def fake_cleanup(
        claude_command: str,
        front_claude_command: str,
        *,
        force: bool,
        exclude_pids: set[int] | None = None,
    ) -> ProcessCleanupReport:
        del claude_command, front_claude_command, force, exclude_pids
        return ProcessCleanupReport(
            matched=1,
            stopped=0,
            force_kill_attempts=0,
            permission_denied=1,
            remaining=1,
            term_signals_sent=0,
        )

    monkeypatch.setattr(killall_module, "cleanup_claude_processes", fake_cleanup)
    rc = killall_module.main([])
    assert rc == 1
