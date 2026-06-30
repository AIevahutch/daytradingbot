from pathlib import Path

from trading_bot.dashboard_status import lightweight_dashboard_status


class FakeStore:
    def __init__(self, heartbeat=None, raises=False):
        self.heartbeat = heartbeat
        self.raises = raises

    def latest_scan_heartbeat(self):
        if self.raises:
            raise RuntimeError("database busy")
        return self.heartbeat


def test_lightweight_dashboard_status_does_not_require_full_healthcheck(tmp_path):
    pid_file = tmp_path / "scanner.pid"
    pid_file.write_text(str(999999), encoding="utf-8")

    status = lightweight_dashboard_status(
        object(),
        FakeStore({"completed_at": "2026-06-29T06:30:00", "status": "completed"}),
        pid_file=pid_file,
    )

    assert status.status == "degraded"
    assert status.scanner_running is False
    assert status.scanner_pid is None
    assert status.latest_heartbeat_completed_at == "2026-06-29T06:30:00"


def test_lightweight_dashboard_status_handles_busy_database(tmp_path):
    pid_file = tmp_path / "scanner.pid"

    status = lightweight_dashboard_status(
        object(),
        FakeStore(raises=True),
        pid_file=pid_file,
    )

    assert status.status == "degraded"
    assert status.latest_heartbeat_completed_at is None


def test_dashboard_does_not_run_full_healthcheck_during_global_render():
    source = Path("dashboard/app.py").read_text(encoding="utf-8")
    navigation_index = source.index("nav_cols = st.columns(")
    before_navigation = source[:navigation_index]

    assert "run_healthcheck(" not in before_navigation
    assert "recover_scanner_if_stale(" not in source
    assert "Run Full Healthcheck" in source


def test_dashboard_uses_lazy_top_level_navigation_instead_of_eager_tabs():
    source = Path("dashboard/app.py").read_text(encoding="utf-8")
    navigation_index = source.index("nav_cols = st.columns(")
    top_level_section = source[: source.index('if selected_view == "Health":')]

    assert "st.tabs(" not in top_level_section
    assert "st.radio(" not in top_level_section
    assert "link_button(" in top_level_section
    assert 'if selected_view == "Market":' in source
    assert navigation_index < source.index('if selected_view == "Health":')


def test_dashboard_startup_avoids_module_reloads_and_schema_initialization():
    source = Path("dashboard/app.py").read_text(encoding="utf-8")

    assert "importlib.reload(" not in source
    assert "initialize=False" in source
    assert "list_dashboard_rows(" in source


def test_dashboard_analytics_sections_use_fast_dashboard_reads():
    source = Path("dashboard/app.py").read_text(encoding="utf-8")

    assert "store.list_trades()" not in source
    assert "store.list_alerts()" not in source


def test_dashboard_market_uses_batched_fast_reads():
    source = Path("dashboard/app.py").read_text(encoding="utf-8")

    assert "dashboard_frames(" in source
    assert "latest_symbol_candles(" in source
    assert "lightweight_dashboard_status(settings, store)" not in source


def test_dashboard_refresh_status_button_refreshes_cached_health_data():
    source = Path("dashboard/app.py").read_text(encoding="utf-8")
    button_index = source.index('key="health_refresh_status"')
    next_button_index = source.index('key="health_send_telegram_test"', button_index)
    refresh_block = source[button_index:next_button_index]

    assert "st.cache_data.clear()" in refresh_block
    assert 'st.session_state["full_healthcheck_result"] = run_healthcheck(settings, store)' in refresh_block
    assert "status refreshed from live scanner, database, and watchdog state" in refresh_block
