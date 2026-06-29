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
    navigation_index = source.index("selected_view = st.radio(")
    before_navigation = source[:navigation_index]

    assert "run_healthcheck(" not in before_navigation
    assert "recover_scanner_if_stale(" not in source
    assert "Run Full Healthcheck" in source


def test_dashboard_uses_lazy_top_level_navigation_instead_of_eager_tabs():
    source = Path("dashboard/app.py").read_text(encoding="utf-8")
    navigation_index = source.index("selected_view = st.radio(")
    top_level_section = source[: source.index('if selected_view == "Health":')]

    assert "st.tabs(" not in top_level_section
    assert 'if selected_view == "Market":' in source
    assert navigation_index < source.index('if selected_view == "Health":')
