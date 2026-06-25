from datetime import datetime, timedelta

from trading_bot.data.market_data import (
    MarketDataEngine,
    completed_candles_for_timeframe,
    is_stale,
    resample_candles,
)
from trading_bot.models import Candle
from trading_bot.settings import Settings
from trading_bot.storage import SQLiteStore


def make_candle(index, price=100):
    return Candle(
        symbol="SPY",
        timeframe="1m",
        timestamp=datetime(2026, 1, 2, 9, 30) + timedelta(minutes=index),
        open=price + index,
        high=price + index + 1,
        low=price + index - 1,
        close=price + index + 0.5,
        volume=100 + index,
        source="test",
    )


class FakeColumns:
    nlevels = 1


class FakeTimestamp:
    def __init__(self, value):
        self.value = value

    def to_pydatetime(self):
        return self.value


class FakeFrame:
    columns = FakeColumns()

    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        for timestamp, row in self.rows:
            yield FakeTimestamp(timestamp), row


def test_resample_candles_uses_ohlcv_rules():
    candles = [make_candle(i) for i in range(5)]
    resampled = resample_candles(candles, "5m", 5)

    assert len(resampled) == 1
    bar = resampled[0]
    assert bar.open == candles[0].open
    assert bar.high == max(c.high for c in candles)
    assert bar.low == min(c.low for c in candles)
    assert bar.close == candles[-1].close
    assert bar.volume == sum(c.volume for c in candles)


def test_stale_detection_flags_old_candles():
    old = [make_candle(0)]
    now = datetime(2026, 1, 2, 10, 0)

    assert is_stale(old, stale_minutes=7, now=now)
    assert not is_stale([make_candle(29)], stale_minutes=7, now=now)


def test_completed_candles_for_timeframe_drops_partial_alert_bar():
    one_minute = [make_candle(i) for i in range(20)]
    fifteen = resample_candles(one_minute, "15m", 15)
    context = {"1m": one_minute, "15m": fifteen}

    completed = completed_candles_for_timeframe(context, "15m")

    assert len(fifteen) == 2
    assert len(completed) == 1
    assert completed[0].timestamp == datetime(2026, 1, 2, 9, 30)


def test_normalize_frame_drops_nan_ohlc_rows():
    frame = FakeFrame(
        [
            (
                datetime(2026, 1, 2, 9, 30),
                {
                    "Open": 100.0,
                    "High": 101.0,
                    "Low": 99.0,
                    "Close": 100.5,
                    "Volume": 1000,
                },
            ),
            (
                datetime(2026, 1, 2, 9, 31),
                {
                    "Open": 100.0,
                    "High": 101.0,
                    "Low": 99.0,
                    "Close": float("nan"),
                    "Volume": 1000,
                },
            ),
        ]
    )

    candles = MarketDataEngine._normalize_frame("SPY", "1m", frame)

    assert len(candles) == 1
    assert candles[0].close == 100.5


def test_storage_skips_invalid_candles_instead_of_writing_nulls(tmp_path):
    settings = Settings(database_path=str(tmp_path / "bot.sqlite"))
    store = SQLiteStore(settings.database_file)
    valid = make_candle(0)
    invalid = make_candle(1)
    invalid.close = float("nan")

    inserted = store.upsert_candles([valid, invalid])

    assert inserted == 1
    candles = store.latest_candles("SPY", "1m", limit=10)
    assert len(candles) == 1
    assert candles[0].timestamp == valid.timestamp
