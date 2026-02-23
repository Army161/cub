from datetime import datetime, timedelta

import pytest

from cub.timeparse import parse_when


def test_parse_duration_minutes() -> None:
    due = parse_when("5m", now=100.0)
    assert due == pytest.approx(400.0)


def test_parse_duration_with_in_prefix() -> None:
    due = parse_when("in 2 hours", now=10.0)
    assert due == pytest.approx(10.0 + 7200)


def test_parse_iso_datetime_future() -> None:
    base = datetime(2026, 2, 22, 12, 0, 0)
    future = base + timedelta(minutes=30)
    due = parse_when(future.isoformat(), now=base.timestamp())
    assert due == pytest.approx(future.timestamp())


def test_parse_when_rejects_past_datetime() -> None:
    now = datetime(2026, 2, 22, 12, 0, 0)
    past = now - timedelta(minutes=1)
    with pytest.raises(ValueError, match="future"):
        parse_when(past.isoformat(), now=now.timestamp())


def test_parse_when_rejects_unknown_format() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        parse_when("later this afternoon", now=1.0)
