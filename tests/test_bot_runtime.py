import signal

from cub.bot import _iter_supported_signals


def test_iter_supported_signals_includes_sigint() -> None:
    signals = _iter_supported_signals()
    assert signal.SIGINT in signals


def test_iter_supported_signals_has_no_duplicates() -> None:
    signals = _iter_supported_signals()
    assert len(signals) == len(set(signals))
