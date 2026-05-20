from datetime import datetime, timedelta

from trading_bot.analytics.performance import breakdowns, calculate_metrics, mistake_tag_counts
from trading_bot.analytics.recommendations import RecommendationEngine
from trading_bot.models import Candle
from trading_bot.psychology.no_trade import NoTradeEngine
from trading_bot.settings import Settings


def candle(index, close=100, volume=1000):
    ts = datetime(2026, 1, 2, 9, 30) + timedelta(minutes=5 * index)
    return Candle("SPY", "5m", ts, close, close + 0.02, close - 0.02, close, volume, "test")


def test_no_trade_flags_low_range_chop():
    candles = [candle(i, 100 + i * 0.001) for i in range(25)]

    state = NoTradeEngine(Settings()).evaluate("SPY", candles, [], {"QQQ": "neutral"})

    assert state["is_no_trade"]
    assert "chop" in state["reason"]


def test_performance_metrics_and_breakdowns():
    trades = [
        {"opened_at": "2026-01-02T10:00:00", "realized_pl": 100, "took_trade": 1, "setup_type": "A", "market_condition": "trending", "confidence": 90, "mistake_tags_json": "[]"},
        {"opened_at": "2026-01-02T11:00:00", "realized_pl": -50, "took_trade": 1, "setup_type": "A", "market_condition": "trending", "confidence": 88, "mistake_tags_json": '["FOMO"]'},
        {"opened_at": "2026-01-03T10:00:00", "realized_pl": 150, "took_trade": 1, "setup_type": "B", "market_condition": "balanced", "confidence": 91, "mistake_tags_json": "[]"},
    ]

    metrics = calculate_metrics(trades)
    assert metrics["total_pl"] == 200
    assert metrics["win_rate"] == 66.67
    assert metrics["profit_factor"] == 5
    assert breakdowns(trades)["by_setup_type"]["A"]["total_pl"] == 50
    assert mistake_tag_counts(trades)["FOMO"] == 1


def test_recommendation_engine_suggests_without_applying_rules():
    losing_trades = [
        {"setup_type": "VWAP reclaim", "realized_pl": -10, "took_trade": 1, "opened_at": f"2026-01-0{i}T10:00:00", "mistake_tags_json": "[]"}
        for i in range(1, 4)
    ]

    recs = RecommendationEngine().generate(losing_trades, [])

    assert recs
    assert all(rec.status == "pending_review" for rec in recs)
    assert recs[0].sample_size == 3
    assert recs[0].evidence_quality == "low"
    assert recs[0].overfitting_risk == "high"
