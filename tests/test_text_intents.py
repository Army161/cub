from cub.text_intents import parse_control_intent


def test_cancel_intent_with_task_id() -> None:
    intent = parse_control_intent("cancel task ab12cd34")
    assert intent is not None
    assert intent.action == "cancel_task"
    assert intent.task_id == "ab12cd34"
    assert intent.force is False


def test_cancel_intent_force_kill() -> None:
    intent = parse_control_intent("kill task deadbeef")
    assert intent is not None
    assert intent.action == "cancel_task"
    assert intent.task_id == "deadbeef"
    assert intent.force is True


def test_cancel_intent_latest_without_task_id() -> None:
    intent = parse_control_intent("cancel")
    assert intent is not None
    assert intent.action == "cancel_task"
    assert intent.task_id is None


def test_mute_and_unmute_intents() -> None:
    mute = parse_control_intent("mute updates")
    unmute = parse_control_intent("unmute updates")
    assert mute is not None and mute.action == "mute_updates"
    assert unmute is not None and unmute.action == "unmute_updates"


def test_probe_intent_with_task_and_query() -> None:
    intent = parse_control_intent("check on task ab12cd34 summarize blockers")
    assert intent is not None
    assert intent.action == "probe_task"
    assert intent.task_id == "ab12cd34"
    assert intent.query == "summarize blockers"


def test_probe_intent_without_task_uses_latest() -> None:
    intent = parse_control_intent("probe task")
    assert intent is not None
    assert intent.action == "probe_task"
    assert intent.task_id is None


def test_continue_intent_with_task_and_query() -> None:
    intent = parse_control_intent("continue task ab12cd34 add e2e tests")
    assert intent is not None
    assert intent.action == "continue_task"
    assert intent.task_id == "ab12cd34"
    assert intent.query == "add e2e tests"


def test_continue_intent_with_can_you_prefix() -> None:
    intent = parse_control_intent("can you continue task deadbeef add auth and tests")
    assert intent is not None
    assert intent.action == "continue_task"
    assert intent.task_id == "deadbeef"
    assert intent.query == "add auth and tests"


def test_unrelated_text_has_no_control_intent() -> None:
    assert parse_control_intent("What is 7 + 5?") is None
