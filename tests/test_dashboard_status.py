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
    navigation_index = source.index("render_dashboard_navigation(")
    top_level_section = source[: source.index('if selected_view == "Health":')]
    navigation_section = source[
        source.index("DASHBOARD_VIEWS = [") : source.index('if selected_view == "Health":')
    ]

    assert "st.tabs(" not in top_level_section
    assert "st.radio(" not in top_level_section
    assert ".link_button(" not in navigation_section
    assert "render_dashboard_navigation(" in top_level_section
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


def test_dashboard_current_setup_does_not_look_like_latest_scan_when_stale():
    source = Path("dashboard/app.py").read_text(encoding="utf-8")
    priority_section = source[
        source.index("def prioritize_market_setups(") : source.index(
            "def latest_symbol_scan_entry("
        )
    ]
    override_section = source[
        source.index("def heartbeat_no_trade_overrides_setup(") : source.index(
            "def safe_latest_scan_heartbeat("
        )
    ]

    assert 'f"Setup created {format_datetime(row.get' in source
    assert 'f"Setup scan {format_datetime(row.get' not in source
    assert '["created_at", "_status_priority", "_confidence_sort"]' in priority_section
    assert 'status == "alert_ready"' not in override_section


def test_dashboard_refresh_status_button_refreshes_cached_health_data():
    source = Path("dashboard/app.py").read_text(encoding="utf-8")
    button_index = source.index('key="health_refresh_status"')
    next_button_index = source.index('key="health_send_telegram_test"', button_index)
    refresh_block = source[button_index:next_button_index]

    assert "st.cache_data.clear()" in refresh_block
    assert 'st.session_state["full_healthcheck_result"] = run_healthcheck(settings, store)' in refresh_block
    assert "status refreshed from live scanner, database, and watchdog state" in refresh_block


def test_performance_and_breakdowns_use_responsive_summary_cards():
    source = Path("dashboard/app.py").read_text(encoding="utf-8")
    performance_section = source[
        source.index('if selected_view == "Performance":') : source.index(
            'if selected_view == "Breakdowns":'
        )
    ]
    breakdowns_section = source[
        source.index('if selected_view == "Breakdowns":') : source.index(
            'if selected_view == "Paper":'
        )
    ]
    period_cards_section = source[
        source.index("def render_period_summary_cards(") : source.index(
            "def render_breakdown_metric_cards("
        )
    ]

    assert "render_period_summary_cards(" in performance_section
    assert "render_breakdown_metric_cards(" in breakdowns_section
    assert 'render_dashboard_section_header("Performance")' in performance_section
    assert 'render_dashboard_section_header("Breakdowns")' in breakdowns_section
    assert 'st.subheader("Performance")' not in performance_section
    assert 'st.subheader("Breakdown Analytics")' not in breakdowns_section
    assert "render_analytics_group_heading(period_name.title())" in period_cards_section
    assert "render_analytics_group_heading(" in breakdowns_section
    assert "show_table(" not in performance_section
    assert "show_table(" not in breakdowns_section
    assert 'if "total_pl" in breakdown_table.columns:' in breakdowns_section
    assert 'st.plotly_chart(fig, width="stretch")' not in performance_section
