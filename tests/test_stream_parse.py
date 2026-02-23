import json

from cub.stream_parse import extract_text_snippet


def test_filters_rate_limit_noise() -> None:
    line = json.dumps({"type": "rate_limit_event", "message": "ignored"})
    assert extract_text_snippet(line) is None


def test_extracts_bash_tool_use_command() -> None:
    line = json.dumps(
        {"type": "tool_use", "name": "Bash", "input": {"command": "npx create-react-app mytodo"}}
    )
    assert extract_text_snippet(line) == "Running bash: npx create-react-app mytodo"


def test_normalizes_approval_prompt() -> None:
    line = json.dumps(
        {"type": "tool_result", "content": [{"type": "text", "text": "This command requires approval"}]}
    )
    assert extract_text_snippet(line) == "Waiting for command approval to continue."


def test_suppresses_ask_user_question_tool_use_noise() -> None:
    line = json.dumps({"type": "tool_use", "name": "AskUserQuestion", "input": {"question": "Answer?"}})
    assert extract_text_snippet(line) is None


def test_suppresses_ask_user_question_result_noise() -> None:
    line = json.dumps(
        {"type": "tool_result", "content": [{"type": "text", "text": "Answer questions?"}]}
    )
    assert extract_text_snippet(line) is None
