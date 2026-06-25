from pathlib import Path

from trading_bot.dashboard_refresh import (
    MIN_REFRESH_INTERVAL_MS,
    auto_refresh_asset_path,
    refresh_interval_ms,
)


def test_refresh_interval_has_safe_minimum():
    assert refresh_interval_ms(1) == MIN_REFRESH_INTERVAL_MS
    assert refresh_interval_ms(60) == 60_000


def test_auto_refresh_component_uses_streamlit_value_protocol():
    html = Path(auto_refresh_asset_path(), "index.html").read_text()

    assert "streamlit:setComponentValue" in html
    assert "streamlit:componentReady" in html
    assert "userIsEditing" in html
    assert "location.replace" not in html
    assert "top.location" not in html
    assert "parent.location" not in html
