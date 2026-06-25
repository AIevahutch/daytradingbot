from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo

from trading_bot.alerts.telegram import TelegramClient
from trading_bot.data.market_data import latest_age_minutes
from trading_bot.models import Candle, utc_now
from trading_bot.runtime.scanner_process import reconcile_scanner_status, watchdog_status
from trading_bot.settings import PROJECT_ROOT, Settings
from trading_bot.storage import SQLiteStore


def _status_from_checks(checks: List[Dict]) -> str:
    if any(check["status"] == "fail" for check in checks):
        return "fail"
    if any(check["status"] == "warn" for check in checks):
        return "degraded"
    return "ok"


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _market_data_expected(settings: Settings, now_utc: datetime) -> bool:
    local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(
        ZoneInfo(settings.timezone)
    )
    if local_now.weekday() >= 5:
        return False
    market_hours = settings.market_hours
    start = _parse_time(market_hours.get("premarket_start", "04:00"))
    end = _parse_time(market_hours.get("after_hours_end", "20:00"))
    return start <= local_now.time() <= end


def _minutes_since(timestamp: str, now_utc: datetime) -> float:
    then = datetime.fromisoformat(timestamp)
    return max((now_utc - then).total_seconds() / 60.0, 0.0)


def run_healthcheck(settings: Settings, store: SQLiteStore) -> Dict:
    telegram = TelegramClient()
    checks: List[Dict] = []
    now = utc_now()
    market_expected = _market_data_expected(settings, now)

    missing = telegram.validate_configuration()
    checks.append(
        {
            "name": "telegram_config",
            "status": "fail" if missing else "ok",
            "detail": "missing " + ", ".join(missing) if missing else "configured",
        }
    )

    db_path = settings.database_file
    checks.append(
        {
            "name": "database",
            "status": "ok" if db_path.exists() else "fail",
            "detail": str(db_path),
        }
    )

    candle_status = store.latest_candle_status()
    one_minute = [row for row in candle_status if row["timeframe"] == "1m"]
    if one_minute:
        latest = max(datetime.fromisoformat(row["latest_timestamp"]) for row in one_minute)
        age = latest_age_minutes([Candle("", "1m", latest, 0, 0, 0, 0, 0)])
        freshness_status = "ok"
        freshness_stale_minutes = max(
            float(settings.stale_data_minutes),
            (settings.scan_cadence_seconds / 60.0) + 2.0,
        )
        if market_expected and age > freshness_stale_minutes:
            freshness_status = "warn"
        session_detail = (
            "market data expected"
            if market_expected
            else "outside configured market-data window"
        )
        checks.append(
            {
                "name": "data_freshness",
                "status": freshness_status,
                "detail": (
                    f"latest 1m candle {latest.isoformat()} "
                    f"({age:.1f} minutes old); {session_detail}"
                ),
            }
        )
    else:
        checks.append(
            {
                "name": "data_freshness",
                "status": "fail" if market_expected else "warn",
                "detail": "no 1m candles stored",
            }
        )

    latest_scan = store.latest_scan_heartbeat()
    heartbeat_status = "ok"
    heartbeat_detail = "scanner stopped outside configured market-data window"
    heartbeat_stale_minutes = max((settings.scan_cadence_seconds * 3) / 60.0, 5.0)
    process = reconcile_scanner_status(
        latest_scan["completed_at"] if latest_scan else None,
        heartbeat_stale_minutes * 60.0,
    )
    if latest_scan:
        heartbeat_age = _minutes_since(latest_scan["completed_at"], now)
        heartbeat_detail = (
            f"{latest_scan['completed_at']} "
            f"({heartbeat_age:.1f} minutes old); process {process.message}"
        )
        if process.running and heartbeat_age > heartbeat_stale_minutes:
            heartbeat_status = "warn"
        elif market_expected and not process.running:
            heartbeat_status = "warn"
        elif market_expected and latest_scan["status"] == "failed":
            heartbeat_status = "warn"
    elif process.running:
        heartbeat_status = "warn"
        heartbeat_detail = "scanner running but no scan heartbeat recorded yet"
    elif market_expected:
        heartbeat_status = "warn"
        heartbeat_detail = "scanner stopped during configured market-data window"
    checks.append(
        {
            "name": "scanner_heartbeat",
            "status": heartbeat_status,
            "detail": heartbeat_detail,
        }
    )

    watchdog = watchdog_status()
    checks.append(
        {
            "name": "scanner_watchdog",
            "status": "ok" if watchdog.running else "warn",
            "detail": (
                f"{watchdog.message}; pid {watchdog.pid}"
                if watchdog.running
                else f"{watchdog.message}; launcher will start it"
            ),
        }
    )

    log_path = PROJECT_ROOT / "logs" / "trading_bot.log"
    checks.append(
        {
            "name": "logging",
            "status": "ok" if log_path.exists() else "warn",
            "detail": str(log_path),
        }
    )

    failed_alerts = store.list_failed_alerts(limit=100)
    checks.append(
        {
            "name": "telegram_delivery",
            "status": "warn" if failed_alerts else "ok",
            "detail": f"{len(failed_alerts)} failed alerts pending retry",
        }
    )

    return {
        "checked_at": utc_now().isoformat(),
        "status": _status_from_checks(checks),
        "project_root": str(PROJECT_ROOT),
        "database": str(Path(settings.database_file)),
        "checks": checks,
    }
