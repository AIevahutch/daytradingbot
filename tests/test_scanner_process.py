import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from trading_bot.runtime import scanner_process
from trading_bot.runtime.scanner_process import (
    is_pid_running,
    read_pid,
    recover_scanner_if_stale,
    reconcile_scanner_status,
    run_scan_once,
    scanner_status,
    start_scanner,
    start_watchdog,
    stop_scanner,
    watchdog_scanner_once,
    watchdog_status,
)


def test_scanner_process_start_stop(tmp_path):
    pid_file = tmp_path / "scanner.pid"
    log_file = tmp_path / "scanner.log"
    command = [sys.executable, "-c", "import time; time.sleep(60)"]

    started = start_scanner(
        command=command,
        pid_file=pid_file,
        log_file=log_file,
        cwd=Path.cwd(),
    )

    assert started.running
    assert read_pid(pid_file) == started.pid
    assert scanner_status(pid_file, log_file).running

    stopped = stop_scanner(pid_file, log_file, timeout_seconds=1)

    assert not stopped.running
    assert read_pid(pid_file) is None


def test_run_scan_once_uses_supplied_command():
    result = run_scan_once(
        command=[sys.executable, "-c", "print('scan-ok')"],
        cwd=Path.cwd(),
    )

    assert result.returncode == 0
    assert "scan-ok" in result.stdout


def test_watchdog_process_start_stop(tmp_path):
    pid_file = tmp_path / "watchdog.pid"
    log_file = tmp_path / "watchdog.log"
    command = [sys.executable, "-c", "import time; time.sleep(60)"]

    started = start_watchdog(
        command=command,
        pid_file=pid_file,
        log_file=log_file,
        cwd=Path.cwd(),
    )

    try:
        assert started.running
        assert read_pid(pid_file) == started.pid
        assert watchdog_status(pid_file, log_file).running
    finally:
        stopped = stop_scanner(pid_file, log_file, timeout_seconds=1)
        assert not stopped.running
        assert read_pid(pid_file) is None


def test_zombie_pid_is_not_considered_running(monkeypatch):
    monkeypatch.setattr(scanner_process, "_is_zombie_process", lambda pid: True)

    assert not is_pid_running(os.getpid())


def test_reconcile_keeps_running_pid_when_heartbeat_is_stale(tmp_path):
    pid_file = tmp_path / "scanner.pid"
    log_file = tmp_path / "scanner.log"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    stale_heartbeat = (datetime.utcnow() - timedelta(hours=1)).replace(microsecond=0)

    status = reconcile_scanner_status(
        stale_heartbeat.isoformat(),
        stale_after_seconds=60,
        pid_file=pid_file,
        log_file=log_file,
    )

    assert status.running
    assert read_pid(pid_file) == os.getpid()
    assert "scanner heartbeat stale" in status.message


def test_scanner_status_adopts_orphan_default_scanner(monkeypatch, tmp_path):
    pid_file = tmp_path / "scanner.pid"
    log_file = tmp_path / "scanner.log"
    orphan_pid = 12345

    monkeypatch.setattr(scanner_process, "DEFAULT_PID_FILE", pid_file)
    monkeypatch.setattr(scanner_process, "find_scanner_pids", lambda: [orphan_pid])

    status = scanner_status(pid_file, log_file)

    assert status.running
    assert status.pid == orphan_pid
    assert read_pid(pid_file) == orphan_pid
    assert "outside pid file" in status.message


def test_recover_scanner_restarts_stale_running_process(tmp_path):
    pid_file = tmp_path / "scanner.pid"
    log_file = tmp_path / "scanner.log"
    stale_heartbeat = (datetime.utcnow() - timedelta(hours=1)).replace(microsecond=0)
    command = [sys.executable, "-c", "import time; time.sleep(60)"]

    first = start_scanner(command=command, pid_file=pid_file, log_file=log_file, cwd=Path.cwd())

    recovered = recover_scanner_if_stale(
        stale_heartbeat.isoformat(),
        stale_after_seconds=60,
        pid_file=pid_file,
        log_file=log_file,
        cwd=Path.cwd(),
    )

    try:
        assert recovered.running
        assert recovered.pid != first.pid
        assert read_pid(pid_file) == recovered.pid
    finally:
        stop_scanner(pid_file, log_file, timeout_seconds=1)


def test_watchdog_starts_scanner_when_missing(tmp_path):
    pid_file = tmp_path / "scanner.pid"
    log_file = tmp_path / "scanner.log"
    command = [sys.executable, "-c", "import time; time.sleep(60)"]

    status = watchdog_scanner_once(
        latest_heartbeat_completed_at=None,
        stale_after_seconds=60,
        command=command,
        pid_file=pid_file,
        log_file=log_file,
        cwd=Path.cwd(),
    )

    try:
        assert status.ok
        assert status.action == "started"
        assert status.status.running
        assert read_pid(pid_file) == status.status.pid
    finally:
        stop_scanner(pid_file, log_file, timeout_seconds=1)


def test_watchdog_leaves_fresh_scanner_running(tmp_path):
    pid_file = tmp_path / "scanner.pid"
    log_file = tmp_path / "scanner.log"
    fresh_heartbeat = datetime.utcnow().replace(microsecond=0)
    command = [sys.executable, "-c", "import time; time.sleep(60)"]

    first = start_scanner(command=command, pid_file=pid_file, log_file=log_file, cwd=Path.cwd())
    status = watchdog_scanner_once(
        fresh_heartbeat.isoformat(),
        stale_after_seconds=60,
        command=command,
        pid_file=pid_file,
        log_file=log_file,
        cwd=Path.cwd(),
    )

    try:
        assert status.ok
        assert status.action == "ok"
        assert status.status.pid == first.pid
    finally:
        stop_scanner(pid_file, log_file, timeout_seconds=1)


def test_watchdog_restarts_stale_scanner(tmp_path):
    pid_file = tmp_path / "scanner.pid"
    log_file = tmp_path / "scanner.log"
    stale_heartbeat = (datetime.utcnow() - timedelta(hours=1)).replace(microsecond=0)
    command = [sys.executable, "-c", "import time; time.sleep(60)"]

    first = start_scanner(command=command, pid_file=pid_file, log_file=log_file, cwd=Path.cwd())
    status = watchdog_scanner_once(
        stale_heartbeat.isoformat(),
        stale_after_seconds=60,
        command=command,
        pid_file=pid_file,
        log_file=log_file,
        cwd=Path.cwd(),
    )

    try:
        assert status.ok
        assert status.action == "restarted"
        assert status.status.pid != first.pid
        assert read_pid(pid_file) == status.status.pid
    finally:
        stop_scanner(pid_file, log_file, timeout_seconds=1)
