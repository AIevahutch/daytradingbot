from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List

from trading_bot.alerts.telegram import TelegramClient
from trading_bot.data.market_data import latest_age_minutes
from trading_bot.models import Candle, utc_now
from trading_bot.settings import PROJECT_ROOT, Settings
from trading_bot.storage import SQLiteStore


def _status_from_checks(checks: List[Dict]) -> str:
    if any(check["status"] == "fail" for check in checks):
        return "fail"
    if any(check["status"] == "warn" for check in checks):
        return "degraded"
    return "ok"


def run_healthcheck(settings: Settings, store: SQLiteStore) -> Dict:
    telegram = TelegramClient()
    checks: List[Dict] = []

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
        freshness_status = "ok" if age <= settings.stale_data_minutes else "warn"
        checks.append(
            {
                "name": "data_freshness",
                "status": freshness_status,
                "detail": f"latest 1m candle {latest.isoformat()} ({age:.1f} minutes old)",
            }
        )
    else:
        checks.append(
            {
                "name": "data_freshness",
                "status": "fail",
                "detail": "no 1m candles stored",
            }
        )

    latest_scan = store.latest_scan_heartbeat()
    checks.append(
        {
            "name": "scanner_heartbeat",
            "status": "ok" if latest_scan else "warn",
            "detail": latest_scan["completed_at"] if latest_scan else "no scan heartbeat recorded",
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
