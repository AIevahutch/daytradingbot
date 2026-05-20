from datetime import datetime, timedelta

from trading_bot.data.market_data import is_stale, resample_candles
from trading_bot.models import Candle


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

