from cub.task_runner import (
    _append_shell_transcript,
    _build_claude_process_targets,
    _build_shell_transcript,
    _matches_target_tokens,
    _result_includes_shell_transcript,
    _split_command_line_tokens,
)


def test_build_shell_transcript_includes_command_and_output() -> None:
    transcript = _build_shell_transcript(
        [
            "Running bash: ls -d workspace2/*",
            "mytodoapp/",
            "Here are the folders in workspace2: mytodoapp/",
        ]
    )
    assert transcript is not None
    assert "$ ls -d workspace2/*" in transcript
    assert "mytodoapp/" in transcript


def test_result_includes_shell_transcript_checks_output_presence() -> None:
    transcript = "$ ls -d workspace2/*\nmytodoapp/"
    assert _result_includes_shell_transcript(
        "Done.\n\n```shell\n$ ls -d workspace2/*\nmytodoapp/\n```",
        transcript,
    )
    assert not _result_includes_shell_transcript(
        "Done.\n\n```shell\n$ ls -d workspace2/*\n```",
        transcript,
    )


def test_append_shell_transcript_wraps_shell_block() -> None:
    appended = _append_shell_transcript("Task completed.", "$ pwd\n/tmp")
    assert "```shell" in appended
    assert "$ pwd" in appended
    assert "/tmp" in appended


def test_build_claude_process_targets_prefers_configured_claude_names() -> None:
    names, paths = _build_claude_process_targets(
        "/tmp/fake-claude-bin",
        "/opt/another-claude",
    )
    assert "fake-claude-bin" in names
    assert "another-claude" in names
    assert paths


def test_build_claude_process_targets_falls_back_to_default() -> None:
    names, paths = _build_claude_process_targets("python", "node")
    assert names == {"claude"}
    assert paths == set()


def test_split_command_line_tokens_handles_invalid_quotes() -> None:
    tokens = _split_command_line_tokens('python -c "bad')
    assert tokens == ["python", "-c", '"bad']


def test_matches_target_tokens_checks_name_and_path() -> None:
    target_names = {"fake-claude-bin"}
    target_paths = {"/tmp/fake-claude-bin"}
    assert _matches_target_tokens(
        ["/tmp/fake-claude-bin", "--verbose"],
        target_names=target_names,
        target_paths=target_paths,
    )
    assert not _matches_target_tokens(
        ["/usr/bin/python", "app.py"],
        target_names=target_names,
        target_paths=target_paths,
    )
