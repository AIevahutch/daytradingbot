from trading_bot.dashboard_refresh import (
    DEFAULT_NAVIGATION_PAUSE_SECONDS,
    DEFAULT_REFRESH_INTERVAL_SECONDS,
    is_fragment_rerun,
    refresh_interval_seconds,
    should_pause_auto_refresh,
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


def test_auto_refresh_pauses_after_recent_dashboard_navigation():
    state = {"last_nav": 100.0}

    assert should_pause_auto_refresh(
        state,
        "last_nav",
        DEFAULT_NAVIGATION_PAUSE_SECONDS,
        now=110.0,
    )
    assert not should_pause_auto_refresh(
        state,
        "last_nav",
        DEFAULT_NAVIGATION_PAUSE_SECONDS,
        now=116.0,
    )


def test_auto_refresh_does_not_pause_without_navigation_timestamp():
    assert not should_pause_auto_refresh({}, "missing", now=100.0)
    assert not should_pause_auto_refresh({"last_nav": "bad"}, "last_nav", now=100.0)
    assert not should_pause_auto_refresh({"last_nav": 100.0}, None, now=101.0)
