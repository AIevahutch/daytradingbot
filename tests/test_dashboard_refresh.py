from trading_bot.dashboard_refresh import (
    DEFAULT_REFRESH_INTERVAL_SECONDS,
    is_fragment_rerun,
    refresh_interval_seconds,
)


class FakeContext:
    def __init__(self, fragment_ids_this_run):
        self.fragment_ids_this_run = fragment_ids_this_run


def test_refresh_interval_has_safe_minimum():
    assert refresh_interval_seconds(1) == 10
    assert refresh_interval_seconds(60) == DEFAULT_REFRESH_INTERVAL_SECONDS


def test_fragment_rerun_detection():
    assert is_fragment_rerun(None) is False
    assert is_fragment_rerun(FakeContext(None)) is False
    assert is_fragment_rerun(FakeContext([])) is False
    assert is_fragment_rerun(FakeContext(["fragment-id"])) is True
