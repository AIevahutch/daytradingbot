from datetime import datetime, timedelta

from trading_bot.alerts.telegram import ALERT_FOOTER, format_alert
from trading_bot.levels.levels import Level
from trading_bot.models import Candle, SetupSignal, utc_now
from trading_bot.scoring.scoring import ConfidenceScorer
from trading_bot.settings import Settings
from trading_bot.strategy.engine import StrategyEngine


def candle(index, close, volume=1000):
    ts = datetime(2026, 1, 2, 9, 30) + timedelta(minutes=5 * index)
    return Candle("SPY", "5m", ts, close - 0.1, close + 0.2, close - 0.2, close, volume, "test")


def test_strategy_detects_vwap_reclaim():
    five = [candle(i, 99.5 + i * 0.02) for i in range(20)]
    five[-2] = candle(18, 99.8, 1100)
    five[-1] = Candle("SPY", "5m", datetime(2026, 1, 2, 11, 10), 99.9, 100.6, 99.95, 100.4, 1500, "test")
    levels = [
        Level("SPY", "vwap", 100.0, "session", "2026-01-02"),
        Level("SPY", "previous_day_high", 100.2, "1d", "2026-01-02"),
    ]

    signals = StrategyEngine().detect(
        "SPY",
        {"5m": five, "15m": five, "1h": five, "1d": five},
        levels,
        {"QQQ": "bullish", "IWM": "neutral"},
    )

    assert any(signal.setup_type == "VWAP reclaim + retest" for signal in signals)


def test_confidence_threshold_separates_84_and_85():
    settings = Settings()
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="SPY",
        setup_type="test",
        direction="LONG",
        timeframe="5m",
        created_at=utc_now(),
        entry_low=100,
        entry_high=100.2,
        stop_loss=99.5,
        target1=101,
        target2=102,
        invalidation=99.5,
        risk_reward=2.0,
        features={
            "timeframe_aligned": True,
            "level_confluence": True,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "market_confirmed": True,
        },
    )
    scored = scorer.score(setup)
    assert scored.confidence >= 85
    assert scorer.is_alertable(scored)

    weak = SetupSignal(**{**setup.__dict__, "features": {"weak_volume": True, "conflicting_timeframes": True}})
    weak_scored = scorer.score(weak)
    assert weak_scored.confidence < 85
    assert not scorer.is_alertable(weak_scored)


def test_hard_block_prevents_alert_even_when_raw_score_is_high():
    settings = Settings()
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="SPY",
        setup_type="test",
        direction="LONG",
        timeframe="5m",
        created_at=utc_now(),
        entry_low=100,
        entry_high=100.2,
        stop_loss=99.5,
        target1=101,
        target2=102,
        invalidation=99.5,
        risk_reward=2.0,
        features={
            "timeframe_aligned": True,
            "level_confluence": True,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "market_confirmed": True,
        },
    )

    scored = scorer.score(
        setup,
        {
            "is_no_trade": True,
            "market_condition": "chop",
            "reason": "compressed low-range chop",
            "hard_blocks": ["compressed low-range chop"],
        },
    )

    assert scored.status == "blocked"
    assert scored.confidence < settings.alert_threshold
    assert not scorer.is_alertable(scored)
    assert "compressed low-range chop" in scored.features["score_breakdown"]["hard_blocks"]


def test_alert_format_contains_required_fields():
    setup = SetupSignal(
        symbol="SPY",
        setup_type="VWAP reclaim + retest",
        direction="LONG",
        timeframe="5m",
        created_at=utc_now(),
        entry_low=542.2,
        entry_high=542.5,
        stop_loss=541.6,
        target1=543.4,
        target2=544.8,
        invalidation=541.6,
        confidence=89,
        risk_reward=2.0,
        reasoning="SPY reclaimed VWAP and QQQ confirmed strength.",
        avoid_if="SPY loses VWAP.",
    )

    message = format_alert(setup)
    for text in [
        "SPY LONG SETUP",
        "Setup:",
        "Entry:",
        "Stop:",
        "Target 1:",
        "Target 2:",
        "Invalidation:",
        "Confidence: 89/100",
        "Risk/Reward:",
        "Reason:",
        "Avoid if:",
        ALERT_FOOTER,
    ]:
        assert text in message
