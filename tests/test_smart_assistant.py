from cub.smart_assistant import (
    ClaudeCLIResult,
    _build_claude_cli_command,
    _build_fast_claude_cli_user_prompt,
    _build_router_user_prompt,
    _coerce_claude_cli_output,
    _compact_message_for_router,
    _contains_needs_tools_token,
    _extract_needs_tools_summary,
    _looks_like_tool_refusal,
    _prepare_recent_chat_for_router,
    parse_assistant_decision,
)


def test_parse_reply_decision() -> None:
    raw = '{"action":"reply","reply":"Here is a direct answer."}'
    d = parse_assistant_decision(raw, "hello")
    assert d.action == "reply"
    assert d.reply == "Here is a direct answer."


def test_parse_delegate_decision() -> None:
    raw = '{"action":"delegate","delegate_prompt":"implement feature","label":"feature work"}'
    d = parse_assistant_decision(raw, "original")
    assert d.action == "delegate"
    assert d.delegate_prompt == "implement feature"
    assert d.label == "feature work"


def test_parse_invalid_json_falls_back_delegate() -> None:
    d = parse_assistant_decision("not json", "original message")
    assert d.action == "delegate"
    assert d.delegate_prompt == "original message"


def test_parse_embedded_json_block() -> None:
    raw = 'Decision:\n{"action":"reply","reply":"ok"}\nThanks.'
    d = parse_assistant_decision(raw, "x")
    assert d.action == "reply"
    assert d.reply == "ok"


def test_parse_reply_without_reply_falls_back_delegate() -> None:
    raw = '{"action":"reply"}'
    d = parse_assistant_decision(raw, "fallback prompt")
    assert d.action == "delegate"
    assert d.delegate_prompt == "fallback prompt"


def test_parse_delegate_when_action_invalid() -> None:
    raw = '{"action":"unknown","reply":"x"}'
    d = parse_assistant_decision(raw, "fallback prompt")
    assert d.action == "delegate"
    assert d.delegate_prompt == "fallback prompt"


def test_router_prompt_includes_recent_chat_context() -> None:
    prompt = _build_router_user_prompt(
        recent_chat=[
            {"role": "user", "content": "What is 7 + 5?"},
            {"role": "assistant", "content": "7 + 5 = 12"},
        ],
        recent_tasks=[],
        user_message="add 2 to it",
    )

    assert "user: What is 7 + 5?" in prompt
    assert "assistant: 7 + 5 = 12" in prompt
    assert "Current user message:\nadd 2 to it" in prompt


def test_fast_claude_prompt_includes_chat_and_tasks_context() -> None:
    prompt = _build_fast_claude_cli_user_prompt(
        recent_chat=[
            {"role": "user", "content": "what is current directory?"},
            {
                "role": "assistant",
                "content": "Task 1234abcd completed. Exit code: 0 Output: /Users/maddy/codex-projects",
            },
        ],
        recent_tasks=[
            {
                "id": "1234abcd",
                "status": "completed",
                "label": "get current directory",
                "exit_code": 0,
                "claude_session_id": "sess-aaa",
            },
            {
                "id": "88ffee11",
                "status": "running",
                "label": "create react app",
                "exit_code": None,
                "claude_session_id": "sess-bbb",
            },
        ],
        user_message="what folders are there?",
    )

    assert "assistant: Task 1234abcd completed." in prompt
    assert "1234abcd | completed | exit=0 | get current directory" in prompt
    assert "88ffee11 | running | create react app" in prompt
    assert "session=sess-aaa" in prompt
    assert "session=sess-bbb" in prompt
    assert "Current user message:\nwhat folders are there?" in prompt
    assert "Use the context above." in prompt
    assert "NEEDS_TOOLS format" in prompt


def test_prepare_recent_chat_filters_progress_noise() -> None:
    filtered = _prepare_recent_chat_for_router(
        [
            {"role": "user", "content": "what is current directory?"},
            {"role": "assistant", "content": "Queued task 1234abcd (get current directory)."},
            {"role": "assistant", "content": "Task 1234abcd in progress:\n- Running bash: pwd"},
            {
                "role": "assistant",
                "content": (
                    "Task 1234abcd completed.\nExit code: 0\nRecent output:\n"
                    "- Running bash: pwd\n"
                    "- /Users/maddy/codex-projects/claude-telegram-assistant\n"
                    "- The current working directory is /Users/maddy/codex-projects/claude-telegram-assistant.\n"
                ),
            },
        ],
        max_messages=20,
    )

    assert len(filtered) == 2
    assert filtered[0]["role"] == "user"
    assert "what is current directory?" in filtered[0]["content"]
    assert filtered[1]["role"] == "assistant"
    assert "Task 1234abcd completed." in filtered[1]["content"]
    assert "Output:" in filtered[1]["content"]


def test_compact_message_for_router_dedupes_repeated_lines() -> None:
    text = (
        "Task 9999ffff completed.\nExit code: 0\nRecent output:\n"
        "- data/ src/ tests/\n"
        "- data/ src/ tests/\n"
        "- The current directory contains three folders: data/ src/ tests/\n"
    )
    compact = _compact_message_for_router(text)
    assert "Task 9999ffff completed." in compact
    assert compact.count("Output:") == 1
    assert "The current directory contains three folders: data/ src/ tests/" in compact


def test_build_claude_cli_command_with_persistent_session() -> None:
    cmd = _build_claude_cli_command(
        claude_command="claude",
        claude_args=("--dangerously-skip-permissions",),
        model="haiku",
        system_prompt="router prompt",
        user_prompt="hello",
        output_format="text",
        json_schema=None,
        resume_session_id=None,
        session_id="f26d5328-31ca-418e-96e0-6ff66a6d7491",
        persist_session=True,
    )
    assert cmd[0] == "claude"
    assert "--session-id" in cmd
    assert "f26d5328-31ca-418e-96e0-6ff66a6d7491" in cmd
    assert "--tools" in cmd
    assert "" in cmd
    assert "--no-session-persistence" not in cmd


def test_build_claude_cli_command_without_persistence() -> None:
    cmd = _build_claude_cli_command(
        claude_command="claude",
        claude_args=(),
        model="haiku",
        system_prompt="router prompt",
        user_prompt="hello",
        output_format="text",
        json_schema=None,
        resume_session_id=None,
        session_id=None,
        persist_session=False,
    )
    assert "--no-session-persistence" in cmd
    assert "--session-id" not in cmd


def test_build_claude_cli_command_with_resume_and_json_schema() -> None:
    schema = {"type": "object", "properties": {"action": {"type": "string"}}}
    cmd = _build_claude_cli_command(
        claude_command="claude",
        claude_args=(),
        model="haiku",
        system_prompt="router prompt",
        user_prompt="hello",
        output_format="json",
        json_schema=schema,
        resume_session_id="f26d5328-31ca-418e-96e0-6ff66a6d7491",
        session_id=None,
        persist_session=True,
    )
    assert "--resume" in cmd
    assert "f26d5328-31ca-418e-96e0-6ff66a6d7491" in cmd
    assert "--session-id" not in cmd
    assert "--output-format" in cmd
    assert "json" in cmd
    assert "--json-schema" in cmd


def test_coerce_claude_cli_output_uses_structured_output_field() -> None:
    result = ClaudeCLIResult(
        returncode=0,
        stdout_text='{"type":"result","structured_output":{"action":"reply","reply":"15"}}',
        stderr_text="",
    )
    text = _coerce_claude_cli_output(result, {"type": "object"})
    assert text == '{"action":"reply","reply":"15"}'


def test_extract_needs_tools_summary() -> None:
    text = "NEEDS_TOOLS\nCheck current directory"
    assert _extract_needs_tools_summary(text) == "Check current directory"
    assert _extract_needs_tools_summary("Hello") is None


def test_contains_needs_tools_token_detects_embedded_token() -> None:
    text = "I responded with NEEDS_TOOLS - meaning tools are required."
    assert _contains_needs_tools_token(text) is True


def test_looks_like_tool_refusal_matches_manual_execution_response() -> None:
    text = (
        "I cannot create it because I lack the ability to write files. "
        "Would you like all the code so you can do it manually on your machine?"
    )
    assert _looks_like_tool_refusal(text) is True
