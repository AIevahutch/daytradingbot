from datetime import datetime, timedelta

from trading_bot.carter_squeeze import CarterSqueezeEngine
from trading_bot.data.market_data import resample_candles
from trading_bot.models import Candle
from trading_bot.settings import Settings
from trading_bot.signal_sources import CARTER_SIGNAL_SOURCE, CARTER_SOURCE_LABEL


def squeeze_release_context(symbol="SPY", release_volume=1800, release_close=101.25):
    start = datetime(2026, 1, 2, 9, 30)
    candles = []
    for index in range(24):
        close = 100.0 + ((index % 2) - 0.5) * 0.02
        candles.append(
            Candle(
                symbol,
                "5m",
                start + timedelta(minutes=5 * index),
                close - 0.01,
                100.5,
                99.5,
                close,
                1000,
                "test",
            )
        )
    candles.append(
        Candle(
            symbol,
            "5m",
            start + timedelta(minutes=5 * 24),
            100.1,
            101.5,
            100.0,
            release_close,
            release_volume,
            "test",
        )
    )
    return {
        "5m": candles,
        "15m": resample_candles(candles, "15m", 15),
        "30m": resample_candles(candles, "30m", 30),
        "1h": resample_candles(candles, "1h", 60),
        "1m": [],
    }


def test_carter_squeeze_detects_alertable_release():
    engine = CarterSqueezeEngine(Settings())

    signals = engine.detect(
        "SPY",
        squeeze_release_context(),
        {"SPY": "bullish", "QQQ": "bullish", "IWM": "bullish"},
        {"is_no_trade": False, "market_condition": "trending", "hard_blocks": []},
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.setup_type == "Carter Squeeze"
    assert signal.timeframe == "5m"
    assert signal.status == "alert_ready"
    assert signal.confidence >= 80
    assert signal.risk_reward == 1.0
    assert signal.features["alert_source"] == CARTER_SIGNAL_SOURCE
    assert signal.features["source_label"] == CARTER_SOURCE_LABEL
    assert signal.features["squeeze_duration"] >= 5
    assert signal.features["squeeze_release"] is True
    assert signal.features["momentum_confirmed"] is True
    assert signal.features["volume_confirmed"] is True
    assert signal.features["strict_volume_confirmed"] is True
    assert signal.features["all_indexes_aligned"] is True
    assert signal.features["clean_1r_path"] is True
    assert signal.features["tactical_exit_r_multiple"] == 1.0


def test_carter_squeeze_blocks_weak_volume_release():
    engine = CarterSqueezeEngine(Settings())

    signals = engine.detect(
        "SPY",
        squeeze_release_context(release_volume=900),
        {"SPY": "bullish", "QQQ": "bullish", "IWM": "bullish"},
        {"is_no_trade": False, "market_condition": "trending", "hard_blocks": []},
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.status == "blocked"
    assert signal.confidence < 80
    assert any(
        "volume ratio" in block
        for block in signal.features["score_breakdown"]["hard_blocks"]
    )


def test_carter_squeeze_blocks_without_all_three_index_alignment():
    engine = CarterSqueezeEngine(Settings())

    signals = engine.detect(
        "SPY",
        squeeze_release_context(),
        {"SPY": "bullish", "QQQ": "bullish", "IWM": "neutral"},
        {"is_no_trade": False, "market_condition": "trending", "hard_blocks": []},
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.status == "blocked"
    assert signal.confidence < 80
    assert any(
        "SPY/QQQ/IWM are not all aligned" in block
        for block in signal.features["score_breakdown"]["hard_blocks"]
    )


def test_carter_squeeze_can_be_disabled():
    settings = Settings()
    settings.carter_squeeze["enabled"] = False
    engine = CarterSqueezeEngine(settings)

    assert engine.detect(
        "SPY",
        squeeze_release_context(),
        {"QQQ": "bullish"},
        {"is_no_trade": False, "market_condition": "trending", "hard_blocks": []},
    ) == []
