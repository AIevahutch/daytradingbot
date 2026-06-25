from datetime import datetime

from trading_bot import scanner as scanner_module
from trading_bot.data.market_data import MarketDataEngine
from trading_bot.scanner import TradingScanner, market_data_window_open
from trading_bot.settings import Settings


class RecordingStore:
    def __init__(self):
        self.heartbeats = []

    def insert_scan_heartbeat(self, started_at, completed_at, status, summary):
        self.heartbeats.append(
            {
                "started_at": started_at,
                "completed_at": completed_at,
                "status": status,
                "summary": summary,
            }
        )
        return len(self.heartbeats)


class FailingIfCalledDataEngine(MarketDataEngine):
    def fetch_symbol_context(self, symbol, days=5):
        raise AssertionError("market data should not be fetched outside session")


class SaturdayDatetime(datetime):
    @classmethod
    def utcnow(cls):
        return cls(2026, 6, 13, 16, 0, 0)


def test_market_data_window_open_skips_weekends():
    settings = Settings()

    assert not market_data_window_open(settings, datetime(2026, 6, 13, 16, 0, 0))


def test_scanner_pauses_without_fetching_data_outside_market_window(monkeypatch):
    settings = Settings()
    store = RecordingStore()
    monkeypatch.setattr(scanner_module, "datetime", SaturdayDatetime)

    scanner = TradingScanner(
        settings,
        store,
        data_engine=FailingIfCalledDataEngine(),
    )

    outcome = scanner.scan_once()

    assert outcome["errors"] == []
    assert outcome["alerts"] == []
    assert outcome["no_trade"] == [
        "Scanner paused: outside configured market-data window"
    ]
    assert store.heartbeats[0]["status"] == "paused"
