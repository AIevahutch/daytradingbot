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
    tabs_index = source.index("st.tabs(")
    before_tabs = source[:tabs_index]

    assert "run_healthcheck(" not in before_tabs
    assert "recover_scanner_if_stale(" not in source
    assert "Run Full Healthcheck" in source
