from datetime import datetime, timedelta

from trading_bot.alerts.telegram import TelegramResult
from trading_bot.data.market_data import resample_candles
from trading_bot.models import Candle, SetupSignal, utc_now
from trading_bot.replay import HistoricalReplay
from trading_bot.scanner import TradingScanner
from trading_bot.settings import Settings
from trading_bot.storage import SQLiteStore


def one_minute_series(symbol, start, count=150, base=100.0, step=0.007):
    price = base
    candles = []
    for index in range(count):
        close = price + step
        candles.append(
            Candle(
                symbol=symbol,
                timeframe="1m",
                timestamp=start + timedelta(minutes=index),
                open=price,
                high=close + 0.03,
                low=price - 0.03,
                close=close,
                volume=1000 + index * 5,
                source="test",
            )
        )
        price = close
    return candles


class FakeDataEngine:
    def fetch_symbol_context(self, symbol, days=5):
        candles = one_minute_series(symbol, utc_now() - timedelta(minutes=140), count=140)
        return {
            "1m": candles,
            "5m": resample_candles(candles, "5m", 5),
            "15m": resample_candles(candles, "15m", 15),
            "1h": resample_candles(candles, "1h", 60),
            "1d": [],
        }


class FakeStrategy:
    def detect(self, symbol, candles_by_tf, levels, market_biases, stale_data=False):
        return [
            SetupSignal(
                symbol=symbol,
                setup_type="QA breakout",
                direction="LONG",
                timeframe="5m",
                created_at=utc_now(),
                entry_low=100,
                entry_high=100.1,
                stop_loss=99.5,
                target1=101,
                target2=102,
                invalidation=99.5,
                risk_reward=1.8,
                reasoning="Synthetic QA setup.",
                avoid_if="Synthetic invalidation.",
                features={
                    "timeframe_aligned": True,
                    "level_confluence": True,
                    "vwap_confirmed": True,
                    "volume_confirmed": True,
                    "market_confirmed": True,
                },
            )
        ]


class FakeNoTrade:
    def evaluate(self, symbol, candles, levels, market_biases, stale_data=False):
        return {
            "is_no_trade": False,
            "market_condition": "trending",
            "reason": "",
            "hard_blocks": [],
        }


class FailingTelegram:
    def send_message(self, text, max_attempts=3, retry_delay_seconds=0):
        return TelegramResult(False, "network down", attempts=max_attempts)


def test_scanner_persists_failed_telegram_attempt_and_heartbeat(tmp_path):
    settings = Settings(database_path=str(tmp_path / "bot.sqlite"), telegram_retry_delay_seconds=0)
    store = SQLiteStore(settings.database_file)
    scanner = TradingScanner(
        settings,
        store,
        data_engine=FakeDataEngine(),
        telegram=FailingTelegram(),
    )
    scanner.strategy = FakeStrategy()
    scanner.no_trade = FakeNoTrade()

    outcome = scanner.scan_once()

    assert outcome["alerts"]
    alerts = store.list_rows("alerts", 10)
    attempts = store.list_rows("telegram_delivery_attempts", 10)
    heartbeats = store.list_rows("scanner_heartbeats", 10)
    breakdowns = store.list_rows("score_breakdowns", 10)
    assert alerts[0]["delivered"] == 0
    assert attempts[0]["error"] == "network down"
    assert heartbeats[0]["status"] == "ok"
    assert breakdowns[0]["status"] == "alert_ready"


def test_historical_replay_records_paper_events(tmp_path):
    settings = Settings(database_path=str(tmp_path / "replay.sqlite"))
    store = SQLiteStore(settings.database_file)
    start = datetime(2026, 1, 2, 9, 30)
    for symbol, base in [("SPY", 100.0), ("QQQ", 200.0), ("IWM", 150.0)]:
        store.upsert_candles(one_minute_series(symbol, start, count=150, base=base))
        store.upsert_candles(
            [
                Candle(symbol, "1d", datetime(2026, 1, 1), base, base + 0.5, base - 1, base, 100000, "test"),
                Candle(symbol, "1d", datetime(2026, 1, 2), base, base + 2, base - 0.5, base + 1, 100000, "test"),
            ]
        )

    replay = HistoricalReplay(settings, store)
    replay.strategy = FakeStrategy()
    replay.no_trade = FakeNoTrade()

    summary = replay.run("2026-01-02", "2026-01-02")

    assert summary["run_id"] == 1
    assert summary["event_count"] > 0
    assert store.list_rows("paper_runs", 1)[0]["status"] == "completed"
    assert store.list_rows("paper_events", 5)
