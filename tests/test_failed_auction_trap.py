from datetime import datetime, timedelta

from trading_bot.data.market_data import resample_candles
from trading_bot.failed_auction_trap import FailedAuctionTrapEngine
from trading_bot.models import Candle
from trading_bot.settings import Settings
from trading_bot.signal_sources import (
    FAILED_AUCTION_TRAP_SIGNAL_SOURCE,
    FAILED_AUCTION_TRAP_SOURCE_LABEL,
)


def _candle(symbol, ts, open_price, high, low, close, volume=1000, timeframe="1m"):
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=ts,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        source="test",
    )


def _context_with_premarket_low_trap(symbol="SPY", close_back_inside=True):
    base_day = datetime(2026, 6, 24)
    prior_day_regular = [
        _candle(symbol, datetime(2026, 6, 23, 14, 0) + timedelta(minutes=i), 100, 101, 99, 100.5)
        for i in range(10)
    ]
    premarket = [
        _candle(symbol, base_day.replace(hour=12, minute=i), 100.8, 101.5, 100.0, 100.7)
        for i in range(20)
    ]
    regular = [
        _candle(symbol, base_day.replace(hour=13, minute=30) + timedelta(minutes=i), 100.4, 100.5, 100.1, 100.3)
        for i in range(30)
    ]
    five_minute = []
    ts = base_day.replace(hour=12, minute=15)
    price = 100.35
    for index in range(20):
        five_minute.append(
            _candle(symbol, ts + timedelta(minutes=index * 5), price, price + 0.06, price - 0.06, price, 1000, "5m")
        )
    previous_close = 99.92
    last_close = 100.18 if close_back_inside else 99.96
    five_minute.append(
        _candle(symbol, base_day.replace(hour=13, minute=55), 100.05, 100.08, 99.98, previous_close, 1100, "5m")
    )
    five_minute.append(
        _candle(symbol, base_day.replace(hour=14, minute=0), previous_close, 100.32, 99.9, last_close, 2600, "5m")
    )
    one_minute = prior_day_regular + premarket + regular
    one_minute.extend(
        [
            _candle(symbol, base_day.replace(hour=13, minute=55) + timedelta(minutes=i), 100.05, 100.2, 99.98, 100.12)
            for i in range(10)
        ]
    )
    return {
        "1m": one_minute,
        "5m": five_minute,
        "15m": resample_candles(one_minute, "15m", 15),
        "30m": resample_candles(one_minute, "30m", 30),
        "1h": resample_candles(one_minute, "1h", 60),
        "1d": [],
    }


def _settings():
    settings = Settings()
    settings.failed_auction_trap["timeframes"] = ["5m"]
    settings.failed_auction_trap["session_timezone"] = "America/New_York"
    return settings


def test_failed_auction_trap_detects_clean_close_back_inside():
    engine = FailedAuctionTrapEngine(_settings())

    signals = engine.detect(
        "SPY",
        _context_with_premarket_low_trap(),
        market_biases={"SPY": "bullish", "QQQ": "bullish", "IWM": "neutral"},
        no_trade_state={"market_condition": "trending"},
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.setup_type == "Failed Auction Trap"
    assert signal.direction == "LONG"
    assert signal.status == "alert_ready"
    assert signal.confidence >= 80
    assert signal.features["trap_level_name"] == "premarket_low"
    assert signal.features["alert_source"] == FAILED_AUCTION_TRAP_SIGNAL_SOURCE
    assert signal.features["source_label"] == FAILED_AUCTION_TRAP_SOURCE_LABEL


def test_failed_auction_trap_ignores_wick_only_failure():
    engine = FailedAuctionTrapEngine(_settings())

    signals = engine.detect(
        "SPY",
        _context_with_premarket_low_trap(close_back_inside=False),
        market_biases={"SPY": "bullish", "QQQ": "bullish"},
        no_trade_state={"market_condition": "trending"},
    )

    assert signals == []


def test_failed_auction_trap_blocks_when_spy_qqq_disagree():
    engine = FailedAuctionTrapEngine(_settings())

    signals = engine.detect(
        "SPY",
        _context_with_premarket_low_trap(),
        market_biases={"SPY": "bullish", "QQQ": "bearish"},
        no_trade_state={"market_condition": "trending"},
    )

    assert len(signals) == 1
    assert signals[0].status == "watch_only"
    assert signals[0].confidence == 79
    hard_blocks = signals[0].features["score_breakdown"]["hard_blocks"]
    assert "SPY and QQQ do not agree with the trap direction" in hard_blocks
