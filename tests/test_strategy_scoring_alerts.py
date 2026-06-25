from datetime import datetime, timedelta

from trading_bot.alerts.telegram import (
    ALERT_FOOTER,
    format_alert,
    format_tactical_exit_alert,
)
from trading_bot.data.market_data import resample_candles
from trading_bot.levels.levels import Level
from trading_bot.models import Candle, SetupSignal, utc_now
from trading_bot.scoring.scoring import ConfidenceScorer
from trading_bot.settings import Settings
from trading_bot.strategy.engine import StrategyEngine, fast_intraday_bias


def candle(index, close, volume=1000):
    ts = datetime(2026, 1, 2, 9, 30) + timedelta(minutes=5 * index)
    return Candle("SPY", "15m", ts, close - 0.1, close + 0.2, close - 0.2, close, volume, "test")


def test_strategy_detects_vwap_reclaim():
    fifteen = [candle(i, 99.5 + i * 0.02) for i in range(20)]
    fifteen[-2] = candle(18, 99.8, 1100)
    fifteen[-1] = Candle("SPY", "15m", datetime(2026, 1, 2, 11, 10), 99.9, 100.6, 99.95, 100.4, 1500, "test")
    levels = [
        Level("SPY", "vwap", 100.0, "session", "2026-01-02"),
        Level("SPY", "previous_day_high", 100.2, "1d", "2026-01-02"),
    ]

    signals = StrategyEngine().detect(
        "SPY",
        {"15m": fifteen, "30m": fifteen, "1h": fifteen, "1d": fifteen},
        levels,
        {"QQQ": "bullish", "IWM": "neutral"},
    )

    assert any(signal.setup_type == "VWAP reclaim + retest" for signal in signals)
    assert {signal.timeframe for signal in signals}.issubset({"15m", "30m", "1h"})


def test_strategy_uses_5m_trigger_with_one_r_daytrade_targets():
    five_minute = [candle(i, 99.5 + i * 0.02) for i in range(20)]
    five_minute[-2] = candle(18, 99.8, 1100)
    five_minute[-1] = Candle("SPY", "5m", datetime(2026, 1, 2, 11, 10), 99.9, 100.6, 99.95, 100.4, 1500, "test")
    levels = [
        Level("SPY", "vwap", 100.0, "session", "2026-01-02"),
        Level("SPY", "previous_day_high", 100.2, "1d", "2026-01-02"),
    ]

    signals = StrategyEngine().detect(
        "SPY",
        {"5m": five_minute, "15m": [], "30m": [], "1h": [], "1d": []},
        levels,
        {"QQQ": "bullish", "IWM": "neutral"},
        alert_timeframes=["5m"],
    )

    reclaim = [signal for signal in signals if signal.setup_type == "VWAP reclaim + retest"]
    assert reclaim
    setup = reclaim[0]
    entry_mid = (setup.entry_low + setup.entry_high) / 2
    risk = abs(entry_mid - setup.stop_loss)
    assert setup.timeframe == "5m"
    assert round(setup.target1 - entry_mid, 4) == round(risk, 4)
    assert round(setup.target2 - entry_mid, 4) == round(risk * 2, 4)
    assert setup.risk_reward == 1.0


def test_strategy_can_exclude_vwap_setups_from_live_candidates():
    fifteen = [candle(i, 99.5 + i * 0.02) for i in range(20)]
    fifteen[-2] = candle(18, 99.8, 1100)
    fifteen[-1] = Candle("SPY", "15m", datetime(2026, 1, 2, 11, 10), 99.9, 100.6, 99.95, 100.4, 1500, "test")
    levels = [
        Level("SPY", "vwap", 100.0, "session", "2026-01-02"),
        Level("SPY", "previous_day_high", 100.2, "1d", "2026-01-02"),
    ]

    signals = StrategyEngine().detect(
        "SPY",
        {"15m": fifteen, "30m": fifteen, "1h": fifteen, "1d": fifteen},
        levels,
        {"QQQ": "bullish", "IWM": "neutral"},
        excluded_setup_types=["VWAP reclaim + retest", "VWAP rejection + retest"],
    )

    assert all("VWAP" not in signal.setup_type for signal in signals)


def test_strategy_can_exclude_premarket_high_break_from_live_candidates():
    fifteen = [candle(i, 99.7 + i * 0.02) for i in range(20)]
    fifteen[-2] = Candle("SPY", "15m", datetime(2026, 1, 2, 11, 5), 100.0, 100.18, 99.95, 100.1, 1100, "test")
    fifteen[-1] = Candle("SPY", "15m", datetime(2026, 1, 2, 11, 10), 100.08, 100.7, 100.05, 100.5, 1800, "test")
    levels = [
        Level("SPY", "vwap", 99.8, "session", "2026-01-02"),
        Level("SPY", "premarket_high", 100.2, "premarket", "2026-01-02"),
    ]
    context = {"15m": fifteen, "30m": [], "1h": [], "1d": []}

    included = StrategyEngine().detect(
        "SPY",
        context,
        levels,
        {"QQQ": "bullish", "IWM": "bullish"},
        alert_timeframes=["15m"],
    )
    excluded = StrategyEngine().detect(
        "SPY",
        context,
        levels,
        {"QQQ": "bullish", "IWM": "bullish"},
        alert_timeframes=["15m"],
        excluded_setup_types=["premarket high break + hold"],
    )

    assert any(signal.setup_type == "premarket high break + hold" for signal in included)
    assert all(signal.setup_type != "premarket high break + hold" for signal in excluded)


def test_strategy_detects_fast_momentum_expansion_before_15m_close():
    one_minute = []
    ts = datetime(2026, 1, 2, 10, 0)
    price = 100.0
    for index in range(28):
        close = price + 0.02
        one_minute.append(
            Candle("SPY", "1m", ts + timedelta(minutes=index), price, close + 0.05, price - 0.05, close, 1000, "test")
        )
        price = close
    one_minute.append(
        Candle("SPY", "1m", ts + timedelta(minutes=28), 100.55, 103.1, 100.5, 102.9, 9000, "test")
    )
    levels = [Level("SPY", "vwap", 100.1, "session", "2026-01-02")]
    context = {
        "1m": one_minute,
        "5m": resample_candles(one_minute, "5m", 5),
        "15m": resample_candles(one_minute, "15m", 15),
        "30m": resample_candles(one_minute, "30m", 30),
        "1h": resample_candles(one_minute, "1h", 60),
        "1d": [],
    }

    signals = StrategyEngine().detect(
        "SPY",
        context,
        levels,
        {"QQQ": "bullish", "IWM": "neutral"},
        alert_timeframes=["15m"],
    )

    fast = [signal for signal in signals if signal.setup_type == "Fast momentum expansion"]
    assert fast
    assert fast[0].timeframe == "1m"
    assert fast[0].features["midday_momentum_exception"]
    assert fast[0].features["volume_expansion_ratio"] >= 2.4


def test_strategy_detects_delayed_fast_momentum_expansion_short():
    one_minute = []
    ts = datetime(2026, 1, 2, 10, 0)
    price = 100.0
    for index in range(28):
        close = price + 0.01
        one_minute.append(
            Candle("SPY", "1m", ts + timedelta(minutes=index), price, close + 0.04, price - 0.04, close, 1000, "test")
        )
        price = close
    one_minute.append(
        Candle("SPY", "1m", ts + timedelta(minutes=28), 100.28, 100.32, 96.9, 97.1, 12000, "test")
    )
    one_minute.extend(
        [
            Candle("SPY", "1m", ts + timedelta(minutes=29), 97.1, 97.7, 96.95, 97.4, 2500, "test"),
            Candle("SPY", "1m", ts + timedelta(minutes=30), 97.4, 97.5, 96.8, 97.0, 2300, "test"),
        ]
    )
    levels = [Level("SPY", "vwap", 99.8, "session", "2026-01-02")]
    context = {
        "1m": one_minute,
        "5m": resample_candles(one_minute, "5m", 5),
        "15m": resample_candles(one_minute, "15m", 15),
        "30m": resample_candles(one_minute, "30m", 30),
        "1h": resample_candles(one_minute, "1h", 60),
        "1d": [],
    }

    signals = StrategyEngine().detect(
        "SPY",
        context,
        levels,
        {"QQQ": "bearish", "IWM": "bearish"},
        alert_timeframes=["15m"],
    )

    fast = [signal for signal in signals if signal.setup_type == "Fast momentum expansion"]
    assert fast
    assert fast[0].direction == "SHORT"
    assert fast[0].features["signal_timestamp"] == one_minute[-3].timestamp.isoformat()
    assert fast[0].features["signal_lag_minutes"] == 2
    assert fast[0].features["volume_expansion_ratio"] >= 2.4


def test_strategy_detects_fast_momentum_expansion_on_5m_and_10m():
    def expansion_context(timeframe, minutes):
        ts = datetime(2026, 1, 2, 10, 0)
        bars = []
        price = 100.0
        for index in range(28):
            close = price + 0.02
            bars.append(
                Candle(
                    "SPY",
                    timeframe,
                    ts + timedelta(minutes=minutes * index),
                    price,
                    close + 0.05,
                    price - 0.05,
                    close,
                    1000,
                    "test",
                )
            )
            price = close
        bars.append(
            Candle(
                "SPY",
                timeframe,
                ts + timedelta(minutes=minutes * 28),
                100.55,
                103.1,
                100.5,
                102.9,
                9000,
                "test",
            )
        )
        return bars

    levels = [Level("SPY", "vwap", 100.1, "session", "2026-01-02")]

    five_signals = StrategyEngine().detect(
        "SPY",
        {"1m": [], "5m": expansion_context("5m", 5), "10m": [], "15m": [], "30m": [], "1h": [], "1d": []},
        levels,
        {"QQQ": "bullish", "IWM": "bullish"},
        alert_timeframes=["15m"],
    )
    ten_signals = StrategyEngine().detect(
        "SPY",
        {"1m": [], "5m": [], "10m": expansion_context("10m", 10), "15m": [], "30m": [], "1h": [], "1d": []},
        levels,
        {"QQQ": "bullish", "IWM": "bullish"},
        alert_timeframes=["15m"],
    )

    five_fast = [signal for signal in five_signals if signal.setup_type == "Fast momentum expansion"]
    ten_fast = [signal for signal in ten_signals if signal.setup_type == "Fast momentum expansion"]
    assert five_fast
    assert five_fast[0].timeframe == "5m"
    assert five_fast[0].features["primary_timeframe"] == "5m"
    assert ten_fast
    assert ten_fast[0].timeframe == "10m"
    assert ten_fast[0].features["primary_timeframe"] == "10m"


def test_fast_intraday_bias_uses_recent_shock_candle_when_feed_lags():
    one_minute = []
    ts = datetime(2026, 1, 2, 10, 0)
    price = 100.0
    for index in range(28):
        close = price + 0.01
        one_minute.append(
            Candle("SPY", "1m", ts + timedelta(minutes=index), price, close + 0.04, price - 0.04, close, 1000, "test")
        )
        price = close
    one_minute.append(
        Candle("SPY", "1m", ts + timedelta(minutes=28), 100.28, 100.32, 96.9, 97.1, 12000, "test")
    )
    one_minute.extend(
        [
            Candle("SPY", "1m", ts + timedelta(minutes=29), 97.1, 97.7, 96.95, 97.4, 2500, "test"),
            Candle("SPY", "1m", ts + timedelta(minutes=30), 97.4, 97.5, 96.8, 97.0, 2300, "test"),
        ]
    )

    assert fast_intraday_bias({"1m": one_minute}, "bullish") == "bearish"


def test_confidence_threshold_separates_79_and_80():
    settings = Settings(alert_threshold=80, scoring_weights={"base_setup": 72, "clean_risk_reward": 8})
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="SPY",
        setup_type="test",
        direction="LONG",
        timeframe="15m",
        created_at=utc_now(),
        entry_low=100,
        entry_high=100.2,
        stop_loss=99.5,
        target1=101,
        target2=102,
        invalidation=99.5,
        risk_reward=2.0,
        features={},
    )
    scored = scorer.score(setup)
    assert scored.confidence == 80
    assert scorer.is_alertable(scored)

    weak_settings = Settings(
        alert_threshold=80,
        scoring_weights={"base_setup": 71, "clean_risk_reward": 8},
    )
    weak_scorer = ConfidenceScorer(weak_settings)
    weak = SetupSignal(**{**setup.__dict__, "features": {}})
    weak_scored = weak_scorer.score(weak)
    assert weak_scored.confidence == 79
    assert weak_scored.status == "watch_only"
    assert not scorer.is_alertable(weak_scored)


def test_hard_block_prevents_alert_even_when_raw_score_is_high():
    settings = Settings()
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="SPY",
        setup_type="test",
        direction="LONG",
        timeframe="15m",
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


def test_midday_momentum_exception_can_override_lunch_block():
    settings = Settings()
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="SPY",
        setup_type="Fast momentum expansion",
        direction="LONG",
        timeframe="1m",
        created_at=utc_now(),
        entry_low=728.6,
        entry_high=729.5,
        stop_loss=727.0,
        target1=731.0,
        target2=732.5,
        invalidation=727.0,
        risk_reward=1.8,
        features={
            "timeframe_aligned": True,
            "level_confluence": True,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "market_confirmed": True,
            "fast_momentum_expansion": True,
            "midday_momentum_exception": True,
            "volume_expansion_ratio": 3.2,
            "range_expansion_ratio": 4.0,
            "recent_move_pct": 0.7,
        },
    )

    scored = scorer.score(
        setup,
        {
            "is_no_trade": True,
            "market_condition": "midday_lull",
            "reason": "midday participation lull; avoid lunch-session fakeouts",
            "hard_blocks": ["midday participation lull; avoid lunch-session fakeouts"],
        },
    )

    assert scored.status == "alert_ready"
    assert scored.market_condition == "trending"
    factors = [
        item["factor"]
        for item in scored.features["score_breakdown"]["positives"]
    ]
    assert "midday_momentum_exception" in factors
    assert not scored.features["score_breakdown"]["hard_blocks"]


def test_fast_momentum_expansion_overrides_research_hard_block():
    settings = Settings()
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="SPY",
        setup_type="Fast momentum expansion",
        direction="LONG",
        timeframe="1m",
        created_at=utc_now(),
        entry_low=728.6,
        entry_high=729.5,
        stop_loss=727.0,
        target1=731.0,
        target2=732.5,
        invalidation=727.0,
        risk_reward=1.8,
        features={
            "timeframe_aligned": True,
            "level_confluence": True,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "market_confirmed": True,
            "fast_momentum_expansion": True,
            "midday_momentum_exception": True,
            "volume_expansion_ratio": 3.2,
            "range_expansion_ratio": 4.0,
            "recent_move_pct": 0.7,
        },
    )

    scored = scorer.score(
        setup,
        {
            "is_no_trade": True,
            "market_condition": "research_blocked",
            "reason": "do_not_trade",
            "hard_blocks": ["high-risk macro day"],
            "research": {
                "enabled": True,
                "hard_block": True,
                "reason": "do_not_trade",
                "hard_blocks": ["high-risk macro day"],
                "penalty": -30,
            },
        },
    )

    assert scored.status == "alert_ready"
    assert scored.confidence >= settings.alert_threshold
    assert scored.market_condition == "trending"
    assert scored.features["risk_override"] == "fast_momentum_expansion"
    assert scored.features["score_breakdown"]["hard_blocks"] == []


def test_all_index_aligned_strat_short_can_override_research_block_as_trend_expansion():
    settings = Settings()
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="QQQ",
        setup_type="Strat 2-1-2 continuation",
        direction="SHORT",
        timeframe="30m",
        created_at=utc_now(),
        entry_low=733.0,
        entry_high=733.4,
        stop_loss=734.0,
        target1=731.8,
        target2=730.6,
        invalidation=734.0,
        risk_reward=2.0,
        features={
            "timeframe_aligned": True,
            "level_confluence": False,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "market_confirmed": True,
            "weak_volume": False,
            "stale_data": False,
            "conflicting_timeframes": False,
            "overextended": False,
            "peer_biases": {"SPY": "bearish", "QQQ": "bearish", "IWM": "bearish"},
            "day_bias": "bearish",
            "hour_bias": "bearish",
            "thirty_bias": "bearish",
            "fifteen_bias": "bearish",
            "primary_bias": "bearish",
        },
    )

    scored = scorer.score(
        setup,
        {
            "is_no_trade": True,
            "market_condition": "research_blocked",
            "reason": "do_not_trade",
            "hard_blocks": ["Research risk score is in the no-trade zone."],
            "research": {
                "enabled": True,
                "hard_block": True,
                "reason": "do_not_trade",
                "hard_blocks": ["Research risk score is in the no-trade zone."],
                "penalty": -30,
            },
        },
    )

    assert scored.status == "alert_ready"
    assert scored.confidence >= settings.alert_threshold
    assert scored.market_condition == "trending"
    assert scored.features["risk_override"] == "all_index_trend_continuation"
    assert scored.features["score_breakdown"]["hard_blocks"] == []


def test_balanced_quality_bonus_rewards_clean_level_setups_without_overriding_blocks():
    settings = Settings(
        alert_threshold=80,
        scoring_weights={
            "base_setup": 60,
            "level_confluence": 7,
            "timeframe_continuity": 0,
            "vwap_confirmation": 7,
            "volume_confirmation": 6,
            "market_confirmation": 6,
            "clean_risk_reward": 8,
            "balanced_quality_bonus": 4,
        },
    )
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="IWM",
        setup_type="VWAP reclaim + retest",
        direction="LONG",
        timeframe="30m",
        created_at=utc_now(),
        entry_low=100,
        entry_high=100.2,
        stop_loss=99.4,
        target1=101.4,
        target2=102.2,
        invalidation=99.4,
        risk_reward=2.0,
        features={
            "level_confluence": True,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "vwap_setup": True,
            "timeframe_aligned": True,
            "market_confirmed": True,
            "vwap_favorable_close": True,
            "vwap_body_confirmed": True,
            "vwap_volume_ratio": 1.3,
            "vwap_entry_extension_pct": 0.2,
            "vwap_cross_count": 0,
            "signal_timestamp": "2026-01-02T11:00:00",
        },
    )

    scored = scorer.score(setup, {"market_condition": "balanced"})
    factors = [
        item["factor"]
        for item in scored.features["score_breakdown"]["positives"]
    ]

    assert "balanced_quality_bonus" in factors
    assert scored.confidence == 98

    weak = SetupSignal(**{**setup.__dict__, "features": {**setup.features, "weak_volume": True}})
    weak_scored = scorer.score(weak, {"market_condition": "balanced"})
    assert weak_scored.status == "blocked"
    assert weak_scored.confidence < settings.alert_threshold


def test_mixed_spy_qqq_alignment_blocks_core_alert():
    settings = Settings()
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="IWM",
        setup_type="premarket high break + hold",
        direction="LONG",
        timeframe="30m",
        created_at=utc_now(),
        entry_low=293.24,
        entry_high=293.52,
        stop_loss=292.65,
        target1=294.83,
        target2=295.56,
        invalidation=293.24,
        risk_reward=2.0,
        features={
            "level_confluence": True,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "timeframe_aligned": True,
            "market_confirmed": True,
            "peer_biases": {
                "SPY": "neutral",
                "QQQ": "bullish",
                "IWM": "neutral",
            },
        },
    )

    scored = scorer.score(setup, {"market_condition": "balanced"})

    assert scored.status == "blocked"
    assert scored.confidence < settings.alert_threshold
    assert any(
        "strict index alignment failed" in block
        for block in scored.features["score_breakdown"]["hard_blocks"]
    )


def test_balanced_break_and_hold_is_blocked_even_when_indexes_align():
    settings = Settings()
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="QQQ",
        setup_type="premarket high break + hold",
        direction="LONG",
        timeframe="30m",
        created_at=utc_now(),
        entry_low=720,
        entry_high=721,
        stop_loss=718,
        target1=725,
        target2=728,
        invalidation=720,
        risk_reward=2.0,
        features={
            "level_confluence": True,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "timeframe_aligned": True,
            "market_confirmed": True,
            "peer_biases": {
                "SPY": "bullish",
                "QQQ": "bullish",
                "IWM": "bullish",
            },
        },
    )

    scored = scorer.score(setup, {"market_condition": "balanced"})

    assert scored.status == "blocked"
    assert scored.confidence < settings.alert_threshold
    assert any(
        "break-and-hold requires trending market" in block
        for block in scored.features["score_breakdown"]["hard_blocks"]
    )


def test_break_and_hold_can_alert_only_as_all_index_trending_continuation():
    settings = Settings()
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="QQQ",
        setup_type="premarket high break + hold",
        direction="LONG",
        timeframe="30m",
        created_at=utc_now(),
        entry_low=720,
        entry_high=721,
        stop_loss=718,
        target1=725,
        target2=728,
        invalidation=720,
        risk_reward=2.0,
        features={
            "level_confluence": True,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "timeframe_aligned": True,
            "market_confirmed": True,
            "peer_biases": {
                "SPY": "bullish",
                "QQQ": "bullish",
                "IWM": "bullish",
            },
        },
    )

    scored = scorer.score(setup, {"market_condition": "trending"})

    assert scored.status == "alert_ready"
    assert scored.confidence >= settings.alert_threshold
    assert scored.features["level_break_confirmation"] == "all_index_trending_continuation"
    assert not scored.features["score_breakdown"]["hard_blocks"]


def test_vwap_quality_gate_blocks_weak_retest_alerts():
    settings = Settings()
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="SPY",
        setup_type="VWAP reclaim + retest",
        direction="LONG",
        timeframe="15m",
        created_at=utc_now(),
        entry_low=100,
        entry_high=100.2,
        stop_loss=99.4,
        target1=101.4,
        target2=102.2,
        invalidation=99.4,
        risk_reward=2.0,
        features={
            "vwap_setup": True,
            "timeframe_aligned": True,
            "level_confluence": False,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "market_confirmed": False,
            "vwap_favorable_close": True,
            "vwap_body_confirmed": True,
            "vwap_volume_ratio": 1.3,
            "vwap_entry_extension_pct": 0.2,
            "vwap_cross_count": 0,
            "signal_timestamp": "2026-01-02T10:00:00",
            "signal_source": "test",
        },
    )

    scored = scorer.score(setup)

    assert scored.status == "blocked"
    assert scored.confidence < settings.alert_threshold
    assert any(
        "peer confirmation" in block
        for block in scored.features["score_breakdown"]["hard_blocks"]
    )


def test_weak_spy_vwap_reclaim_long_is_blocked_pending_review():
    settings = Settings()
    scorer = ConfidenceScorer(settings)
    setup = SetupSignal(
        symbol="SPY",
        setup_type="VWAP reclaim + retest",
        direction="LONG",
        timeframe="15m",
        created_at=utc_now(),
        entry_low=100,
        entry_high=100.2,
        stop_loss=99.4,
        target1=101.4,
        target2=102.2,
        invalidation=99.4,
        risk_reward=2.0,
        features={
            "vwap_setup": True,
            "timeframe_aligned": True,
            "level_confluence": True,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "market_confirmed": True,
            "vwap_favorable_close": True,
            "vwap_body_confirmed": True,
            "vwap_volume_ratio": 1.25,
            "vwap_body_ratio": 0.4,
            "vwap_close_position": 0.66,
            "vwap_entry_extension_pct": 0.2,
            "vwap_cross_count": 0,
            "signal_timestamp": "2026-01-02T11:00:00",
            "signal_source": "test",
        },
    )

    scored = scorer.score(setup)

    assert scored.status == "blocked"
    assert any(
        "SPY VWAP reclaim" in block
        for block in scored.features["score_breakdown"]["hard_blocks"]
    )


def test_alert_format_contains_required_fields():
    setup = SetupSignal(
        symbol="SPY",
        setup_type="VWAP reclaim + retest",
        direction="LONG",
        timeframe="15m",
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
        market_condition="trending",
        features={"peer_biases": {"SPY": "bullish", "QQQ": "bullish", "IWM": "bullish"}},
    )

    message = format_alert(setup)
    for text in [
        "BUY SPY because SPY reclaimed VWAP and QQQ confirmed strength.",
        "Confidence rate: 89/100",
        "Market condition: TRENDING",
        "Index alignment: YES - SPY/QQQ/IWM all BULLISH",
        "Setup:",
        "Direction: LONG",
        "Entry zone:",
        "Stop loss:",
        "Target 1:",
        "Target 2:",
        "Invalidation:",
        "Risk/reward:",
        "Avoid if: SPY loses VWAP.",
        ALERT_FOOTER,
    ]:
        assert text in message


def test_alert_format_supports_sell_short_alerts():
    setup = SetupSignal(
        symbol="QQQ",
        setup_type="VWAP rejection + retest",
        direction="SHORT",
        timeframe="15m",
        created_at=utc_now(),
        entry_low=460.1,
        entry_high=460.4,
        stop_loss=461.0,
        target1=459.0,
        target2=457.8,
        invalidation=461.0,
        confidence=82,
        risk_reward=2.1,
        reasoning="QQQ rejected VWAP and sellers held the retest.",
        avoid_if="QQQ reclaims VWAP.",
        market_condition="balanced",
        features={"peer_biases": {"SPY": "bearish", "QQQ": "bullish", "IWM": "bearish"}},
    )

    message = format_alert(setup)

    assert message.startswith("SELL/SHORT QQQ because QQQ rejected VWAP")
    assert "Confidence rate: 82/100" in message
    assert "Market condition: BALANCED" in message
    assert "Index alignment: NO/MIXED - SPY=BEARISH, QQQ=BULLISH, IWM=BEARISH" in message
    assert "Direction: SHORT" in message
    assert "Avoid if: QQQ reclaims VWAP." in message


def test_alert_format_shows_high_research_risk_warning():
    setup = SetupSignal(
        symbol="QQQ",
        setup_type="Strat 2-1-2 continuation",
        direction="SHORT",
        timeframe="30m",
        created_at=utc_now(),
        entry_low=733.0,
        entry_high=733.4,
        stop_loss=734.0,
        target1=731.8,
        target2=730.6,
        invalidation=734.0,
        confidence=93,
        risk_reward=2.0,
        reasoning="QQQ broke lower with SPY/QQQ/IWM aligned.",
        avoid_if="QQQ reclaims the breakdown candle.",
        market_condition="trending",
        features={
            "peer_biases": {"SPY": "bearish", "QQQ": "bearish", "IWM": "bearish"},
            "score_breakdown": {
                "research": {
                    "enabled": True,
                    "risk_score": 91,
                    "reason": "research risk is high; be careful",
                }
            },
        },
    )

    message = format_alert(setup)

    assert "Research risk: HIGH (91/100) - be careful and confirm manually." in message


def test_liquidity_sweep_alert_includes_tactical_sell_guidance():
    setup = SetupSignal(
        symbol="IWM",
        setup_type="Liquidity sweep reversal",
        direction="LONG",
        timeframe="15m",
        created_at=utc_now(),
        entry_low=285.25,
        entry_high=285.35,
        stop_loss=284.30,
        target1=287.30,
        target2=288.30,
        invalidation=284.30,
        confidence=100,
        risk_reward=2.0,
        reasoning="IWM swept below prior day low and reclaimed it.",
        avoid_if="IWM loses the sweep low.",
        features={
            "tactical_management": True,
            "tactical_exit_r_multiple": 1.0,
            "tactical_exit_price": 286.30,
            "tactical_exit_action": "SELL/PARTIAL",
        },
    )

    message = format_alert(setup)
    sell_message = format_tactical_exit_alert(setup, original_alert_id=12)

    assert "Suggested SELL/PARTIAL: 286.30 (+1R)" in message
    assert "SUGGESTED SELL/PARTIAL IWM" in sell_message
    assert "Original alert id: 12" in sell_message
