from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from trading_bot.models import utc_now
from trading_bot.runtime.scanner_process import DEFAULT_PID_FILE, read_pid


@dataclass(frozen=True)
class DashboardRuntimeStatus:
    status: str
    checked_at: str
    scanner_running: bool
    scanner_pid: Optional[int]
    scanner_message: str
    latest_heartbeat_completed_at: Optional[str]


def lightweight_dashboard_status(
    settings,
    store,
    *,
    pid_file: Path = DEFAULT_PID_FILE,
) -> DashboardRuntimeStatus:
    heartbeat = _safe_latest_heartbeat(store)
    pid = read_pid(pid_file)
    scanner_running = _pid_alive(pid)
    status = "ok" if scanner_running else "degraded"
    if heartbeat and heartbeat.get("status") == "failed":
        status = "degraded"
    return DashboardRuntimeStatus(
        status=status,
        checked_at=utc_now().isoformat(),
        scanner_running=scanner_running,
        scanner_pid=pid if scanner_running else None,
        scanner_message="scanner running" if scanner_running else "scanner not confirmed",
        latest_heartbeat_completed_at=heartbeat.get("completed_at") if heartbeat else None,
    )


def _safe_latest_heartbeat(store) -> Optional[dict]:
    try:
        return store.latest_scan_heartbeat()
    except Exception:
        return None


def _pid_alive(pid: Optional[int]) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
