from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from trading_bot.settings import PROJECT_ROOT


DEFAULT_PID_FILE = PROJECT_ROOT / "data" / "scanner.pid"
DEFAULT_LOG_FILE = PROJECT_ROOT / "logs" / "scanner_process.log"
DEFAULT_WATCHDOG_PID_FILE = PROJECT_ROOT / "data" / "scanner_watchdog.pid"
DEFAULT_WATCHDOG_LOG_FILE = PROJECT_ROOT / "logs" / "scanner_watchdog.log"


@dataclass
class ScannerProcessStatus:
    running: bool
    pid: Optional[int] = None
    message: str = ""
    pid_file: Path = DEFAULT_PID_FILE
    log_file: Path = DEFAULT_LOG_FILE


@dataclass
class ScannerWatchdogResult:
    ok: bool
    action: str
    status: ScannerProcessStatus
    stale_after_seconds: float
    latest_heartbeat_completed_at: Optional[str] = None

    @property
    def message(self) -> str:
        return self.status.message


@dataclass(frozen=True)
class ScanRunSummary:
    success: bool
    status_message: str
    stdout: str = ""
    diagnostics: str = ""


def default_scanner_command() -> List[str]:
    return [sys.executable, "-m", "trading_bot", "scan"]


def default_watchdog_command() -> List[str]:
    return [sys.executable, "-m", "trading_bot", "watchdog"]


def read_pid(pid_file: Path = DEFAULT_PID_FILE) -> Optional[int]:
    try:
        raw = pid_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return not _is_zombie_process(pid)


def scanner_status(
    pid_file: Path = DEFAULT_PID_FILE,
    log_file: Path = DEFAULT_LOG_FILE,
    clean_stale: bool = True,
) -> ScannerProcessStatus:
    pid = read_pid(pid_file)
    if pid is None:
        if pid_file == DEFAULT_PID_FILE:
            orphan_pids = find_scanner_pids()
            if orphan_pids:
                adopted_pid = orphan_pids[0]
                try:
                    pid_file.parent.mkdir(parents=True, exist_ok=True)
                    pid_file.write_text(str(adopted_pid), encoding="utf-8")
                except OSError:
                    pass
                return ScannerProcessStatus(
                    True,
                    adopted_pid,
                    "scanner is running outside pid file",
                    pid_file,
                    log_file,
                )
        return ScannerProcessStatus(False, None, "scanner is not running", pid_file, log_file)
    if is_pid_running(pid):
        return ScannerProcessStatus(True, pid, "scanner is running", pid_file, log_file)
    if clean_stale:
        clear_pid(pid_file)
    return ScannerProcessStatus(False, pid, "stale scanner pid file removed", pid_file, log_file)


def reconcile_scanner_status(
    latest_heartbeat_completed_at: Optional[str],
    stale_after_seconds: float,
    pid_file: Path = DEFAULT_PID_FILE,
    log_file: Path = DEFAULT_LOG_FILE,
) -> ScannerProcessStatus:
    status = scanner_status(pid_file, log_file)
    if not status.running or not latest_heartbeat_completed_at:
        return status
    try:
        heartbeat_at = datetime.fromisoformat(latest_heartbeat_completed_at)
    except ValueError:
        return status
    age_seconds = max((datetime.utcnow().replace(microsecond=0) - heartbeat_at).total_seconds(), 0)
    if age_seconds <= stale_after_seconds:
        return status
    return ScannerProcessStatus(
        True,
        status.pid,
        f"scanner heartbeat stale; last heartbeat {age_seconds / 60.0:.1f} minutes old",
        pid_file,
        log_file,
    )


def clear_pid(pid_file: Path = DEFAULT_PID_FILE) -> None:
    try:
        pid_file.unlink()
    except FileNotFoundError:
        return


def start_scanner(
    command: Optional[List[str]] = None,
    pid_file: Path = DEFAULT_PID_FILE,
    log_file: Path = DEFAULT_LOG_FILE,
    cwd: Path = PROJECT_ROOT,
) -> ScannerProcessStatus:
    existing = scanner_status(pid_file, log_file)
    if existing.running:
        if "outside pid file" in existing.message:
            existing.message = "scanner is already running outside pid file"
        else:
            existing.message = "scanner is already running"
        return existing
    if command is None and pid_file == DEFAULT_PID_FILE:
        orphan_pids = find_scanner_pids()
        if orphan_pids:
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(str(orphan_pids[0]), encoding="utf-8")
            return ScannerProcessStatus(
                True,
                orphan_pids[0],
                "scanner is already running outside pid file",
                pid_file,
                log_file,
            )

    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = command or default_scanner_command()
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"\n--- starting scanner: {' '.join(cmd)} ---\n")
        handle.flush()
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file.write_text(str(process.pid), encoding="utf-8")
    return ScannerProcessStatus(True, process.pid, "scanner started", pid_file, log_file)


def watchdog_status(
    pid_file: Path = DEFAULT_WATCHDOG_PID_FILE,
    log_file: Path = DEFAULT_WATCHDOG_LOG_FILE,
    clean_stale: bool = True,
) -> ScannerProcessStatus:
    pid = read_pid(pid_file)
    if pid is None:
        if pid_file == DEFAULT_WATCHDOG_PID_FILE:
            orphan_pids = find_watchdog_pids()
            if orphan_pids:
                adopted_pid = orphan_pids[0]
                try:
                    pid_file.parent.mkdir(parents=True, exist_ok=True)
                    pid_file.write_text(str(adopted_pid), encoding="utf-8")
                except OSError:
                    pass
                return ScannerProcessStatus(
                    True,
                    adopted_pid,
                    "scanner watchdog is running outside pid file",
                    pid_file,
                    log_file,
                )
        return ScannerProcessStatus(False, None, "scanner watchdog is not running", pid_file, log_file)
    if is_pid_running(pid):
        return ScannerProcessStatus(True, pid, "scanner watchdog is running", pid_file, log_file)
    if clean_stale:
        clear_pid(pid_file)
    return ScannerProcessStatus(False, pid, "stale scanner watchdog pid file removed", pid_file, log_file)


def start_watchdog(
    command: Optional[List[str]] = None,
    pid_file: Path = DEFAULT_WATCHDOG_PID_FILE,
    log_file: Path = DEFAULT_WATCHDOG_LOG_FILE,
    cwd: Path = PROJECT_ROOT,
) -> ScannerProcessStatus:
    existing = watchdog_status(pid_file, log_file)
    if existing.running:
        if "outside pid file" in existing.message:
            existing.message = "scanner watchdog is already running outside pid file"
        else:
            existing.message = "scanner watchdog is already running"
        return existing
    if command is None and pid_file == DEFAULT_WATCHDOG_PID_FILE:
        orphan_pids = find_watchdog_pids()
        if orphan_pids:
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(str(orphan_pids[0]), encoding="utf-8")
            return ScannerProcessStatus(
                True,
                orphan_pids[0],
                "scanner watchdog is already running outside pid file",
                pid_file,
                log_file,
            )

    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = command or default_watchdog_command()
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"\n--- starting scanner watchdog: {' '.join(cmd)} ---\n")
        handle.flush()
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file.write_text(str(process.pid), encoding="utf-8")
    return ScannerProcessStatus(True, process.pid, "scanner watchdog started", pid_file, log_file)


def recover_scanner_if_stale(
    latest_heartbeat_completed_at: Optional[str],
    stale_after_seconds: float,
    pid_file: Path = DEFAULT_PID_FILE,
    log_file: Path = DEFAULT_LOG_FILE,
    cwd: Path = PROJECT_ROOT,
) -> ScannerProcessStatus:
    status = reconcile_scanner_status(
        latest_heartbeat_completed_at,
        stale_after_seconds,
        pid_file,
        log_file,
    )
    if status.running and "heartbeat stale" not in status.message:
        return status
    if status.running:
        stop_scanner(pid_file, log_file, timeout_seconds=5)
    return start_scanner(pid_file=pid_file, log_file=log_file, cwd=cwd)


def watchdog_scanner_once(
    latest_heartbeat_completed_at: Optional[str],
    stale_after_seconds: float,
    command: Optional[List[str]] = None,
    pid_file: Path = DEFAULT_PID_FILE,
    log_file: Path = DEFAULT_LOG_FILE,
    cwd: Path = PROJECT_ROOT,
) -> ScannerWatchdogResult:
    status = reconcile_scanner_status(
        latest_heartbeat_completed_at,
        stale_after_seconds,
        pid_file,
        log_file,
    )
    action = "ok"
    if not status.running:
        action = "started"
        status = start_scanner(command=command, pid_file=pid_file, log_file=log_file, cwd=cwd)
    elif "heartbeat stale" in status.message:
        action = "restarted"
        stop_scanner(pid_file, log_file, timeout_seconds=5)
        status = start_scanner(command=command, pid_file=pid_file, log_file=log_file, cwd=cwd)
    return ScannerWatchdogResult(
        ok=status.running,
        action=action,
        status=status,
        stale_after_seconds=stale_after_seconds,
        latest_heartbeat_completed_at=latest_heartbeat_completed_at,
    )


def stop_scanner(
    pid_file: Path = DEFAULT_PID_FILE,
    log_file: Path = DEFAULT_LOG_FILE,
    timeout_seconds: float = 10.0,
) -> ScannerProcessStatus:
    pid = read_pid(pid_file)
    if pid is None:
        if pid_file == DEFAULT_PID_FILE:
            stopped = _stop_orphan_scanners(timeout_seconds)
            if stopped:
                clear_pid(pid_file)
                return ScannerProcessStatus(
                    False,
                    None,
                    f"stopped {stopped} scanner process(es) without pid file",
                    pid_file,
                    log_file,
                )
        return ScannerProcessStatus(False, None, "scanner was not running", pid_file, log_file)
    if not is_pid_running(pid):
        clear_pid(pid_file)
        if pid_file == DEFAULT_PID_FILE:
            stopped = _stop_orphan_scanners(timeout_seconds, exclude={pid})
            if stopped:
                return ScannerProcessStatus(
                    False,
                    pid,
                    f"stale scanner pid file removed; stopped {stopped} orphan scanner process(es)",
                    pid_file,
                    log_file,
                )
        return ScannerProcessStatus(False, pid, "stale scanner pid file removed", pid_file, log_file)

    if not _terminate_process_group(pid, signal.SIGTERM):
        return ScannerProcessStatus(
            True,
            pid,
            "scanner could not be stopped: permission denied",
            pid_file,
            log_file,
        )
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not is_pid_running(pid):
            clear_pid(pid_file)
            return ScannerProcessStatus(False, pid, "scanner stopped", pid_file, log_file)
        time.sleep(0.2)

    if not _terminate_process_group(pid, signal.SIGKILL):
        return ScannerProcessStatus(
            True,
            pid,
            "scanner could not be force-stopped: permission denied",
            pid_file,
            log_file,
        )
    clear_pid(pid_file)
    return ScannerProcessStatus(False, pid, "scanner force-stopped", pid_file, log_file)


def find_scanner_pids() -> List[int]:
    return _find_trading_bot_command_pids("-m trading_bot scan")


def find_watchdog_pids() -> List[int]:
    return _find_trading_bot_command_pids("-m trading_bot watchdog")


def _find_trading_bot_command_pids(command_fragment: str) -> List[int]:
    try:
        result = subprocess.run(
            ["ps", "axo", "pid=,command="],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    current_pid = os.getpid()
    pids: List[int] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid == current_pid:
            continue
        if command_fragment in command and is_pid_running(pid):
            pids.append(pid)
    return pids


def _stop_orphan_scanners(timeout_seconds: float, exclude: Optional[set] = None) -> int:
    exclude = exclude or set()
    pids = [pid for pid in find_scanner_pids() if pid not in exclude]
    for pid in pids:
        _terminate_process_group(pid, signal.SIGTERM)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if all(not is_pid_running(pid) for pid in pids):
            return len(pids)
        time.sleep(0.2)
    for pid in pids:
        if is_pid_running(pid):
            _terminate_process_group(pid, signal.SIGKILL)
    return len(pids)


def run_scan_once(
    command: Optional[List[str]] = None,
    cwd: Path = PROJECT_ROOT,
    timeout_seconds: int = 180,
) -> subprocess.CompletedProcess:
    cmd = command or [sys.executable, "-m", "trading_bot", "scan", "--once"]
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )


def clean_scan_stderr(stderr: Optional[str]) -> str:
    if not stderr:
        return ""

    cleaned_lines = []
    skip_warning_source_line = False
    for raw_line in stderr.splitlines():
        line = raw_line.rstrip()
        if "NotOpenSSLWarning" in line:
            skip_warning_source_line = True
            continue
        if skip_warning_source_line and line.strip().startswith("warnings.warn("):
            skip_warning_source_line = False
            continue
        skip_warning_source_line = False
        if line.strip():
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def summarize_scan_result(result: subprocess.CompletedProcess) -> ScanRunSummary:
    success = result.returncode == 0
    return ScanRunSummary(
        success=success,
        status_message="Scan completed." if success else "Scan failed.",
        stdout=(result.stdout or "").strip(),
        diagnostics=clean_scan_stderr(result.stderr or ""),
    )


def _terminate_process_group(pid: int, sig: signal.Signals) -> bool:
    try:
        os.killpg(pid, sig)
        return True
    except ProcessLookupError:
        return True
    except PermissionError:
        try:
            os.kill(pid, sig)
            return True
        except ProcessLookupError:
            return True
        except PermissionError:
            return False


def _is_zombie_process(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    state = result.stdout.strip()
    return state.startswith("Z") or " Z" in state
