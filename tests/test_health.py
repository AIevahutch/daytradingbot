from datetime import datetime, timedelta

from trading_bot import health as health_module
from trading_bot.health import run_healthcheck
from trading_bot.models import Candle
from trading_bot.runtime.scanner_process import ScannerProcessStatus
from trading_bot.settings import Settings
from trading_bot.storage import SQLiteStore


class FakeTelegramClient:
    def validate_configuration(self):
        return []


def _store_with_context(tmp_path, latest_candle_at, heartbeat_at):
    settings = Settings(database_path=str(tmp_path / "bot.sqlite"))
    store = SQLiteStore(settings.database_file)
    store.upsert_candles(
        [
            Candle(
                symbol="SPY",
                timeframe="1m",
                timestamp=latest_candle_at,
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
                source="test",
            )
        ]
    )
    store.insert_scan_heartbeat(
        heartbeat_at,
        heartbeat_at,
        "ok",
        {"alerts": [], "watch_only": [], "no_trade": ["SPY: no trade"], "errors": []},
    )
    return settings, store


def test_health_allows_stale_data_outside_market_window(monkeypatch, tmp_path):
    now = datetime(2026, 6, 7, 16, 0)  # Sunday UTC.
    settings, store = _store_with_context(
        tmp_path,
        latest_candle_at=now - timedelta(days=2),
        heartbeat_at=now - timedelta(days=2),
    )
    monkeypatch.setattr(health_module, "utc_now", lambda: now)
    monkeypatch.setattr(health_module, "TelegramClient", FakeTelegramClient)
    monkeypatch.setattr(
        health_module,
        "watchdog_status",
        lambda: ScannerProcessStatus(True, 456, "scanner watchdog is running"),
    )
    monkeypatch.setattr(
        health_module,
        "reconcile_scanner_status",
        lambda latest, stale_after: ScannerProcessStatus(
            False, None, "scanner is not running"
        ),
    )

    health = run_healthcheck(settings, store)

    checks = {check["name"]: check for check in health["checks"]}
    assert health["status"] == "ok"
    assert checks["data_freshness"]["status"] == "ok"
    assert checks["scanner_heartbeat"]["status"] == "ok"
    assert checks["scanner_watchdog"]["status"] == "ok"


def test_health_allows_failed_scanner_heartbeat_outside_market_window(monkeypatch, tmp_path):
    now = datetime(2026, 6, 10, 5, 30)  # Tuesday night, after configured window.
    settings, store = _store_with_context(
        tmp_path,
        latest_candle_at=now - timedelta(hours=5),
        heartbeat_at=now - timedelta(minutes=10),
    )
    store.insert_scan_heartbeat(
        now - timedelta(minutes=1),
        now - timedelta(minutes=1),
        "failed",
        {
            "alerts": [],
            "watch_only": [],
            "no_trade": [],
            "errors": ["scanner cycle failed"],
        },
    )
    monkeypatch.setattr(health_module, "utc_now", lambda: now)
    monkeypatch.setattr(health_module, "TelegramClient", FakeTelegramClient)
    monkeypatch.setattr(
        health_module,
        "watchdog_status",
        lambda: ScannerProcessStatus(True, 456, "scanner watchdog is running"),
    )
    monkeypatch.setattr(
        health_module,
        "reconcile_scanner_status",
        lambda latest, stale_after: ScannerProcessStatus(
            True, 123, "scanner is running"
        ),
    )

    health = run_healthcheck(settings, store)

    checks = {check["name"]: check for check in health["checks"]}
    assert health["status"] == "ok"
    assert checks["data_freshness"]["status"] == "ok"
    assert checks["scanner_heartbeat"]["status"] == "ok"
    assert checks["scanner_watchdog"]["status"] == "ok"


def test_health_warns_when_live_window_data_or_scanner_is_stale(monkeypatch, tmp_path):
    now = datetime(2026, 6, 3, 14, 0)  # Wednesday, 10:00 ET.
    settings, store = _store_with_context(
        tmp_path,
        latest_candle_at=now - timedelta(minutes=30),
        heartbeat_at=now - timedelta(minutes=30),
    )
    monkeypatch.setattr(health_module, "utc_now", lambda: now)
    monkeypatch.setattr(health_module, "TelegramClient", FakeTelegramClient)
    monkeypatch.setattr(
        health_module,
        "watchdog_status",
        lambda: ScannerProcessStatus(False, None, "scanner watchdog is not running"),
    )
    monkeypatch.setattr(
        health_module,
        "reconcile_scanner_status",
        lambda latest, stale_after: ScannerProcessStatus(
            False, None, "scanner is not running"
        ),
    )

    health = run_healthcheck(settings, store)

    checks = {check["name"]: check for check in health["checks"]}
    assert health["status"] == "degraded"
    assert checks["data_freshness"]["status"] == "warn"
    assert checks["scanner_heartbeat"]["status"] == "warn"
    assert checks["scanner_watchdog"]["status"] == "warn"
