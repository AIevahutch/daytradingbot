from datetime import datetime, timedelta

from trading_bot.levels.levels import LevelEngine, compute_vwap, level_map
from trading_bot.models import Candle


def candle(ts, open_price, high, low, close, volume=100):
    return Candle("SPY", "1m", ts, open_price, high, low, close, volume, "test")


def test_compute_vwap_uses_typical_price_volume():
    candles = [
        candle(datetime(2026, 1, 2, 9, 30), 10, 12, 9, 11, 100),
        candle(datetime(2026, 1, 2, 9, 31), 11, 13, 10, 12, 100),
    ]

    expected = (((12 + 9 + 11) / 3 * 100) + ((13 + 10 + 12) / 3 * 100)) / 200
    assert round(compute_vwap(candles), 4) == round(expected, 4)


def test_level_engine_generates_prior_day_and_session_levels():
    prior = [
        candle(datetime(2026, 1, 1, 9, 30) + timedelta(minutes=i), 100, 101 + i, 99, 100.5, 100)
        for i in range(3)
    ]
    premarket = [candle(datetime(2026, 1, 2, 8, 0), 103, 104, 102, 103, 100)]
    today = [candle(datetime(2026, 1, 2, 9, 30), 105, 106, 104, 105, 100)]

    levels = LevelEngine().compute_levels("SPY", prior + premarket + today, [])
    mapped = level_map(levels)

    assert mapped["previous_day_high"] == 103
    assert mapped["previous_day_low"] == 99
    assert mapped["premarket_high"] == 104
    assert mapped["premarket_low"] == 102
    assert "vwap" in mapped
    assert "gap_fill" in mapped

