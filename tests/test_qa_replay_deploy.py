import json
from datetime import datetime, timedelta

from trading_bot.alerts.telegram import TelegramResult
from trading_bot.data.market_data import (
    TIMEFRAME_MINUTES,
    completed_candles_for_timeframe,
    resample_candles,
)
from trading_bot.live_paper import (
    experimental_lane_summaries,
    list_live_experimental_lane_paper_events,
    list_live_failed_auction_trap_paper_events,
    list_live_carter_put_paper_events,
    list_current_live_100_paper_events,
    refresh_live_100_outcomes,
    refresh_live_source_outcomes,
)
from trading_bot.models import Candle, SetupSignal, utc_now
from trading_bot.research.agent import current_session_date
from trading_bot.research.models import ResearchBrief
from trading_bot.replay import (
    HistoricalReplay,
    _daily_context,
    _is_completed_replay_close,
)
from trading_bot.scanner import TradingScanner
from trading_bot.settings import Settings
from trading_bot.signal_sources import (
    CARTER_SIGNAL_SOURCE,
    CARTER_SOURCE_LABEL,
    CORE_SIGNAL_SOURCE,
    CORE_SOURCE_LABEL,
    FAILED_AUCTION_TRAP_SIGNAL_SOURCE,
    FAILED_AUCTION_TRAP_SOURCE_LABEL,
    FAST_MOMENTUM_SIGNAL_SOURCE,
    FAST_MOMENTUM_SOURCE_LABEL,
    HIGH_POTENTIAL_LIQUIDITY_SWEEP_SIGNAL_SOURCE,
    HIGH_POTENTIAL_LIQUIDITY_SWEEP_SOURCE_LABEL,
    LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
    LIVE_FAST_MOMENTUM_PAPER_SOURCE,
    LIVE_CARTER_PAPER_SOURCE,
    LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE,
    tag_alert_source,
)
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
            "30m": resample_candles(candles, "30m", 30),
            "1h": resample_candles(candles, "1h", 60),
            "1d": [],
        }


class TacticalExitDataEngine:
    def __init__(self, candles):
        self.candles = candles

    def fetch_symbol_context(self, symbol, days=5):
        return {
            "1m": self.candles,
            "5m": resample_candles(self.candles, "5m", 5),
            "15m": resample_candles(self.candles, "15m", 15),
            "30m": resample_candles(self.candles, "30m", 30),
            "1h": resample_candles(self.candles, "1h", 60),
            "1d": [],
        }


class FakeStrategy:
    def detect(
        self,
        symbol,
        candles_by_tf,
        levels,
        market_biases,
        stale_data=False,
        alert_timeframes=None,
    ):
        return [
            SetupSignal(
                symbol=symbol,
                setup_type="QA breakout",
                direction="LONG",
                timeframe="15m",
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


class RecordingStrategy:
    def __init__(self):
        self.calls = []

    def detect(
        self,
        symbol,
        candles_by_tf,
        levels,
        market_biases,
        stale_data=False,
        alert_timeframes=None,
    ):
        latest_raw = candles_by_tf["1m"][-1].timestamp
        self.calls.append(
            {
                "latest_raw": latest_raw,
                "completed": {
                    timeframe: completed_candles_for_timeframe(candles_by_tf, timeframe)
                    for timeframe in ("15m", "30m", "1h")
                },
            }
        )
        return []


class EmptyStrategy:
    def detect(
        self,
        symbol,
        candles_by_tf,
        levels,
        market_biases,
        stale_data=False,
        alert_timeframes=None,
    ):
        return []


class FakeFastMomentumStrategy:
    def detect(
        self,
        symbol,
        candles_by_tf,
        levels,
        market_biases,
        stale_data=False,
        alert_timeframes=None,
    ):
        return [
            SetupSignal(
                symbol=symbol,
                setup_type="Fast momentum expansion",
                direction="SHORT",
                timeframe="5m",
                created_at=utc_now(),
                entry_low=100.0,
                entry_high=100.2,
                stop_loss=101.0,
                target1=99.0,
                target2=98.0,
                invalidation=101.0,
                risk_reward=1.0,
                reasoning="Synthetic fast momentum expansion.",
                avoid_if="Momentum candle is reclaimed.",
                features={
                    "fast_momentum_expansion": True,
                    "midday_momentum_exception": True,
                    "volume_expansion_ratio": 3.0,
                    "range_expansion_ratio": 2.5,
                    "recent_move_pct": 0.5,
                    "timeframe_aligned": True,
                    "level_confluence": True,
                    "vwap_confirmed": True,
                    "volume_confirmed": True,
                    "market_confirmed": True,
                    "peer_biases": {
                        "SPY": "bearish",
                        "QQQ": "bearish",
                        "IWM": "bearish",
                    },
                },
            )
        ]


class FakeHighPotentialLiquiditySweepStrategy:
    def detect(
        self,
        symbol,
        candles_by_tf,
        levels,
        market_biases,
        stale_data=False,
        alert_timeframes=None,
    ):
        return [
            SetupSignal(
                symbol=symbol,
                setup_type="Liquidity sweep reversal",
                direction="SHORT",
                timeframe="15m",
                created_at=utc_now(),
                entry_low=298.90,
                entry_high=299.10,
                stop_loss=299.75,
                target1=298.05,
                target2=297.20,
                invalidation=299.75,
                risk_reward=1.0,
                reasoning="Synthetic high-potential balanced liquidity sweep.",
                avoid_if="IWM reclaims the sweep high.",
                features={
                    "level_confluence": True,
                    "vwap_confirmed": True,
                    "volume_confirmed": True,
                    "timeframe_aligned": True,
                    "market_confirmed": False,
                    "peer_biases": {
                        "SPY": "bearish",
                        "QQQ": "bearish",
                        "IWM": "neutral",
                    },
                },
            )
        ]


class FakeCoreLiquiditySweep100Strategy:
    def detect(
        self,
        symbol,
        candles_by_tf,
        levels,
        market_biases,
        stale_data=False,
        alert_timeframes=None,
    ):
        return [
            SetupSignal(
                symbol=symbol,
                setup_type="Liquidity sweep reversal",
                direction="LONG",
                timeframe="5m",
                created_at=utc_now(),
                entry_low=100.0,
                entry_high=100.2,
                stop_loss=99.5,
                target1=101.2,
                target2=102.2,
                invalidation=99.5,
                risk_reward=1.0,
                reasoning="Synthetic 100/100 liquidity sweep.",
                avoid_if="Synthetic invalidation.",
                features={
                    "timeframe_aligned": True,
                    "level_confluence": True,
                    "vwap_confirmed": True,
                    "volume_confirmed": True,
                    "market_confirmed": True,
                    "peer_biases": {
                        "SPY": "bullish",
                        "QQQ": "bullish",
                        "IWM": "neutral",
                    },
                },
            )
        ]


class FakeCarterSqueeze:
    def detect(self, symbol, context, market_biases, no_trade_state=None):
        setup = SetupSignal(
            symbol=symbol,
            setup_type="Carter Squeeze",
            direction="LONG",
            timeframe="15m",
            created_at=utc_now(),
            entry_low=100.0,
            entry_high=100.2,
            stop_loss=99.0,
            target1=102.2,
            target2=103.2,
            invalidation=99.0,
            confidence=88,
            risk_reward=2.0,
            reasoning="Synthetic Carter squeeze release.",
            avoid_if="Synthetic Carter invalidation.",
            market_condition="trend",
            status="alert_ready",
            features={
                "market_regime": "trend",
                "score_breakdown": {
                    "threshold": 80,
                    "positives": [],
                    "penalties": [],
                    "hard_blocks": [],
                    "status": "alert_ready",
                },
            },
        )
        return [tag_alert_source(setup, CARTER_SIGNAL_SOURCE, CARTER_SOURCE_LABEL)]

    def is_alertable(self, setup):
        return setup.status == "alert_ready" and setup.confidence >= 80


class EmptyCarterSqueeze:
    def detect(self, symbol, context, market_biases, no_trade_state=None):
        return []


class FakeFailedAuctionTrap:
    def detect(self, symbol, context, levels=None, market_biases=None, no_trade_state=None):
        setup = SetupSignal(
            symbol=symbol,
            setup_type="Failed Auction Trap",
            direction="LONG",
            timeframe="5m",
            created_at=utc_now(),
            entry_low=100.0,
            entry_high=100.1,
            stop_loss=99.8,
            target1=100.3,
            target2=100.5,
            invalidation=99.8,
            confidence=90,
            risk_reward=1.0,
            reasoning="Synthetic failed auction trap.",
            avoid_if="Synthetic trap invalidation.",
            market_condition="trending",
            status="alert_ready",
            features={
                "market_regime": "trending",
                "score_breakdown": {
                    "threshold": 80,
                    "positives": [],
                    "penalties": [],
                    "hard_blocks": [],
                    "status": "alert_ready",
                },
            },
        )
        return [tag_alert_source(setup, FAILED_AUCTION_TRAP_SIGNAL_SOURCE, FAILED_AUCTION_TRAP_SOURCE_LABEL)]

    def is_paper_trackable(self, setup):
        return setup.status == "alert_ready" and setup.confidence >= 80


class EmptyFailedAuctionTrap:
    def detect(self, symbol, context, levels=None, market_biases=None, no_trade_state=None):
        return []


class FakeNoTrade:
    def evaluate(self, symbol, candles, levels, market_biases, stale_data=False):
        return {
            "is_no_trade": False,
            "market_condition": "trending",
            "reason": "",
            "hard_blocks": [],
        }


class FakeBalancedNoTrade:
    def evaluate(self, symbol, candles, levels, market_biases, stale_data=False):
        return {
            "is_no_trade": False,
            "market_condition": "balanced",
            "reason": "",
            "hard_blocks": [],
        }


class FailingTelegram:
    def send_message(self, text, max_attempts=3, retry_delay_seconds=0):
        return TelegramResult(False, "network down", attempts=max_attempts)


class RecordingTelegram:
    def __init__(self):
        self.messages = []

    def send_message(self, text, max_attempts=3, retry_delay_seconds=0):
        self.messages.append(text)
        return TelegramResult(True, None, attempts=1)


def test_scanner_persists_failed_telegram_attempt_and_heartbeat(tmp_path):
    settings = Settings(database_path=str(tmp_path / "bot.sqlite"), telegram_retry_delay_seconds=0)
    store = SQLiteStore(settings.database_file)
    store.upsert_research_brief(
        ResearchBrief(
            session_date=current_session_date(settings).isoformat(),
            phase="premarket",
            risk_score=20,
            bias="bullish",
            trade_today=True,
            decision="trade_allowed",
            summary="Test research allows trading.",
            drivers=["Test driver."],
            source_status={"test": "ok"},
        )
    )
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


def test_scanner_auto_papers_live_100_confidence_alerts_once(tmp_path):
    settings = Settings(
        symbols=["SPY"],
        database_path=str(tmp_path / "live_paper.sqlite"),
        telegram_retry_delay_seconds=0,
        max_alerts_per_symbol_per_day=3,
    )
    settings.research["enabled"] = False
    settings.strategy["duplicate_alert_minutes"] = 0
    settings.strategy["symbol_alert_cooldown_minutes"] = 0
    store = SQLiteStore(settings.database_file)
    scanner = TradingScanner(
        settings,
        store,
        data_engine=FakeDataEngine(),
        telegram=RecordingTelegram(),
    )
    scanner.strategy = FakeStrategy()
    scanner.no_trade = FakeNoTrade()

    first = scanner.scan_once()

    assert first["alerts"]
    paper_runs = store.list_rows("paper_runs", 10)
    paper_events = store.list_rows("paper_events", 10)
    alerts = store.list_rows("alerts", 10)
    setups = store.list_rows("setups", 10)
    assert len(paper_runs) == 1
    assert len(paper_events) == 1
    assert paper_runs[0]["source"] == "live_100_alerts"
    assert all(event["event_type"] == "alerted" for event in paper_events)
    assert all(event["outcome"] == "open" for event in paper_events)
    assert all(event["confidence"] == 100 for event in paper_events)
    assert all(
        json.loads(event["metadata_json"])["mode"] == "live_100_alert"
        for event in paper_events
    )
    setup = SetupSignal(
        symbol=setups[0]["symbol"],
        setup_type=setups[0]["setup_type"],
        direction=setups[0]["direction"],
        timeframe=setups[0]["timeframe"],
        created_at=datetime.fromisoformat(setups[0]["created_at"]),
        entry_low=setups[0]["entry_low"],
        entry_high=setups[0]["entry_high"],
        stop_loss=setups[0]["stop_loss"],
        target1=setups[0]["target1"],
        target2=setups[0]["target2"],
        invalidation=setups[0]["invalidation"],
        confidence=setups[0]["confidence"],
        risk_reward=setups[0]["risk_reward"],
        reasoning=setups[0]["reasoning"],
        avoid_if=setups[0]["avoid_if"],
        market_condition=setups[0]["market_condition"],
        status=setups[0]["status"],
    )
    assert store.insert_live_paper_alert(
        paper_runs[0]["id"],
        alerts[0]["id"],
        setups[0]["id"],
        setup,
    ) is None
    assert len(store.list_rows("paper_events", 10)) == 1


def test_scanner_runs_core_and_carter_alerts_in_parallel(tmp_path):
    settings = Settings(
        symbols=["SPY"],
        database_path=str(tmp_path / "parallel.sqlite"),
        telegram_retry_delay_seconds=0,
        max_alerts_per_symbol_per_day=3,
    )
    settings.research["enabled"] = False
    settings.strategy["duplicate_alert_minutes"] = 0
    settings.strategy["symbol_alert_cooldown_minutes"] = 0
    settings.carter_squeeze["duplicate_alert_minutes"] = 0
    settings.carter_squeeze["symbol_alert_cooldown_minutes"] = 0
    store = SQLiteStore(settings.database_file)
    telegram = RecordingTelegram()
    scanner = TradingScanner(
        settings,
        store,
        data_engine=FakeDataEngine(),
        telegram=telegram,
    )
    scanner.strategy = FakeStrategy()
    scanner.carter_squeeze = FakeCarterSqueeze()
    scanner.no_trade = FakeNoTrade()

    outcome = scanner.scan_once()

    assert any(item.startswith("Core Model SPY") for item in outcome["alerts"])
    assert any(item.startswith("Carter Squeeze SPY") for item in outcome["alerts"])
    assert any("Signal source: Core Model" in message for message in telegram.messages)
    assert any(message.startswith("CARTER SQUEEZE BUY SPY") for message in telegram.messages)
    paper_runs = store.list_rows("paper_runs", 10)
    assert {run["source"] for run in paper_runs} == {"live_100_alerts", LIVE_CARTER_PAPER_SOURCE}
    metadata = [json.loads(event["metadata_json"]) for event in store.list_rows("paper_events", 10)]
    assert {item["source_label"] for item in metadata} == {CORE_SOURCE_LABEL, CARTER_SOURCE_LABEL}
    assert any(item["signal_source"] == CARTER_SIGNAL_SOURCE for item in metadata)


def test_scanner_paper_tracks_failed_auction_trap_without_telegram(tmp_path):
    settings = Settings(
        symbols=["SPY"],
        database_path=str(tmp_path / "failed_auction_trap.sqlite"),
        telegram_retry_delay_seconds=0,
    )
    settings.research["enabled"] = False
    store = SQLiteStore(settings.database_file)
    telegram = RecordingTelegram()
    scanner = TradingScanner(
        settings,
        store,
        data_engine=FakeDataEngine(),
        telegram=telegram,
    )
    scanner.strategy = EmptyStrategy()
    scanner.carter_squeeze = EmptyCarterSqueeze()
    scanner.failed_auction_trap = FakeFailedAuctionTrap()
    scanner.no_trade = FakeNoTrade()

    outcome = scanner.scan_once()

    assert not telegram.messages
    assert any("Failed Auction Trap SPY" in item for item in outcome["watch_only"])
    paper_runs = store.list_rows("paper_runs", 10)
    assert {run["source"] for run in paper_runs} == {LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE}
    events = list_live_failed_auction_trap_paper_events(store)
    assert len(events) == 1
    metadata = json.loads(events[0]["metadata_json"])
    assert metadata["paper_only"] is True
    assert metadata["telegram_sent"] is False
    assert metadata["signal_source"] == FAILED_AUCTION_TRAP_SIGNAL_SOURCE
    assert metadata["source_label"] == FAILED_AUCTION_TRAP_SOURCE_LABEL


def test_scanner_paper_tracks_fast_momentum_without_telegram(tmp_path):
    settings = Settings(
        symbols=["SPY"],
        database_path=str(tmp_path / "fast_momentum.sqlite"),
        telegram_retry_delay_seconds=0,
        max_alerts_per_symbol_per_day=3,
    )
    settings.research["enabled"] = False
    store = SQLiteStore(settings.database_file)
    telegram = RecordingTelegram()
    scanner = TradingScanner(
        settings,
        store,
        data_engine=FakeDataEngine(),
        telegram=telegram,
    )
    scanner.strategy = FakeFastMomentumStrategy()
    scanner.carter_squeeze = EmptyCarterSqueeze()
    scanner.failed_auction_trap = EmptyFailedAuctionTrap()
    scanner.no_trade = FakeNoTrade()

    outcome = scanner.scan_once()

    assert telegram.messages == []
    assert outcome["alerts"] == []
    assert any("Fast Momentum SPY" in item for item in outcome["watch_only"])
    alerts = store.list_rows("alerts", 10)
    assert alerts == []
    paper_runs = store.list_rows("paper_runs", 10)
    assert len(paper_runs) == 1
    assert paper_runs[0]["source"] == LIVE_FAST_MOMENTUM_PAPER_SOURCE
    paper_events = store.list_rows("paper_events", 10)
    assert len(paper_events) == 1
    metadata = json.loads(paper_events[0]["metadata_json"])
    assert metadata["paper_only"] is True
    assert metadata["telegram_sent"] is False
    assert metadata["signal_source"] == FAST_MOMENTUM_SIGNAL_SOURCE


def test_scanner_paper_tracks_high_potential_liquidity_sweep_without_telegram(tmp_path):
    settings = Settings(
        symbols=["IWM"],
        database_path=str(tmp_path / "high_potential_liquidity.sqlite"),
        telegram_retry_delay_seconds=0,
        max_alerts_per_symbol_per_day=3,
    )
    settings.research["enabled"] = False
    store = SQLiteStore(settings.database_file)
    telegram = RecordingTelegram()
    scanner = TradingScanner(
        settings,
        store,
        data_engine=FakeDataEngine(),
        telegram=telegram,
    )
    scanner.strategy = FakeHighPotentialLiquiditySweepStrategy()
    scanner.carter_squeeze = EmptyCarterSqueeze()
    scanner.failed_auction_trap = EmptyFailedAuctionTrap()
    scanner.no_trade = FakeBalancedNoTrade()

    outcome = scanner.scan_once()

    assert telegram.messages == []
    assert outcome["alerts"] == []
    assert any("High-Potential Liquidity IWM" in item for item in outcome["watch_only"])
    alerts = store.list_rows("alerts", 10)
    assert alerts == []
    paper_runs = store.list_rows("paper_runs", 10)
    assert len(paper_runs) == 1
    assert paper_runs[0]["source"] == LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE
    paper_events = store.list_rows("paper_events", 10)
    assert len(paper_events) == 1
    assert paper_events[0]["confidence"] == 98
    metadata = json.loads(paper_events[0]["metadata_json"])
    assert metadata["paper_only"] is True
    assert metadata["telegram_sent"] is False
    assert metadata["signal_source"] == HIGH_POTENTIAL_LIQUIDITY_SWEEP_SIGNAL_SOURCE
    assert metadata["blocked_core_confidence"] == 79


def test_core_alert_cap_excludes_fast_momentum_entries(tmp_path):
    settings = Settings(symbols=["SPY"], database_path=str(tmp_path / "cap_count.sqlite"))
    store = SQLiteStore(settings.database_file)
    setup_time = utc_now()
    prior_setups = [
        SetupSignal(
            symbol="SPY",
            setup_type="Fast momentum expansion",
            direction="LONG",
            timeframe="5m",
            created_at=setup_time,
            entry_low=100.0,
            entry_high=100.2,
            stop_loss=99.5,
            target1=101.2,
            target2=102.2,
            invalidation=99.5,
            confidence=100,
            risk_reward=1.0,
            reasoning="Old fast momentum alert before it became dashboard-only.",
            avoid_if="Momentum fails.",
            status="alert_ready",
        ),
        SetupSignal(
            symbol="SPY",
            setup_type="Liquidity sweep reversal",
            direction="LONG",
            timeframe="30m",
            created_at=setup_time,
            entry_low=100.0,
            entry_high=100.2,
            stop_loss=99.5,
            target1=101.2,
            target2=102.2,
            invalidation=99.5,
            confidence=94,
            risk_reward=1.0,
            reasoning="Prior core alert.",
            avoid_if="Sweep fails.",
            status="alert_ready",
        ),
        SetupSignal(
            symbol="SPY",
            setup_type="Strat 2-1-2 continuation",
            direction="SHORT",
            timeframe="1h",
            created_at=setup_time,
            entry_low=100.0,
            entry_high=100.2,
            stop_loss=101.0,
            target1=99.0,
            target2=98.0,
            invalidation=101.0,
            confidence=93,
            risk_reward=1.0,
            reasoning="Prior lower-quality core alert.",
            avoid_if="Trend fails.",
            status="alert_ready",
        ),
    ]
    for setup in prior_setups:
        setup_id = store.insert_setup(setup)
        store.insert_alert(setup_id, setup, f"prior {setup.setup_type}", delivered=True)

    assert store.alert_count_today_for_source("SPY", CORE_SIGNAL_SOURCE) == 2


def test_scanner_allows_100_liquidity_sweep_after_daily_cap(tmp_path):
    settings = Settings(
        symbols=["SPY"],
        database_path=str(tmp_path / "cap_override.sqlite"),
        telegram_retry_delay_seconds=0,
        max_alerts_per_symbol_per_day=3,
    )
    settings.research["enabled"] = False
    settings.strategy["duplicate_alert_minutes"] = 0
    settings.strategy["symbol_alert_cooldown_minutes"] = 0
    store = SQLiteStore(settings.database_file)
    setup_time = utc_now()
    for index in range(3):
        prior = SetupSignal(
            symbol="SPY",
            setup_type=f"Prior core alert {index}",
            direction="LONG",
            timeframe="15m",
            created_at=setup_time,
            entry_low=100.0,
            entry_high=100.2,
            stop_loss=99.5,
            target1=101.2,
            target2=102.2,
            invalidation=99.5,
            confidence=90,
            risk_reward=1.0,
            reasoning="Prior capped alert.",
            avoid_if="Synthetic invalidation.",
            status="alert_ready",
        )
        setup_id = store.insert_setup(prior)
        store.insert_alert(setup_id, prior, "prior capped alert", delivered=True)
    old_alert_time = (utc_now() - timedelta(hours=2)).replace(microsecond=0).isoformat()
    with store.connect() as conn:
        conn.execute("update alerts set created_at = ?", (old_alert_time,))
    telegram = RecordingTelegram()
    scanner = TradingScanner(
        settings,
        store,
        data_engine=FakeDataEngine(),
        telegram=telegram,
    )
    scanner.strategy = FakeCoreLiquiditySweep100Strategy()
    scanner.carter_squeeze = EmptyCarterSqueeze()
    scanner.failed_auction_trap = EmptyFailedAuctionTrap()
    scanner.no_trade = FakeNoTrade()

    outcome = scanner.scan_once()

    assert any("Core Model SPY" in item for item in outcome["alerts"])
    assert not any("daily alert cap reached" in item for item in outcome["no_trade"])
    assert len(telegram.messages) == 1
    assert "Liquidity sweep reversal" in telegram.messages[0]


def test_experimental_lane_metrics_separate_open_and_closed_signals(tmp_path):
    settings = Settings(database_path=str(tmp_path / "experimental_lanes.sqlite"))
    store = SQLiteStore(settings.database_file)
    fast_run_id = store.get_or_create_paper_run(
        LIVE_FAST_MOMENTUM_PAPER_SOURCE,
        "2026-06-25",
        ["SPY"],
    )
    sweep_run_id = store.get_or_create_paper_run(
        LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
        "2026-06-25",
        ["IWM"],
    )
    base_time = datetime(2026, 6, 25, 7, 0)
    fast_setup = SetupSignal(
        symbol="SPY",
        setup_type="Fast Momentum Expansion",
        direction="LONG",
        timeframe="5m",
        created_at=base_time,
        entry_low=100.0,
        entry_high=100.2,
        stop_loss=99.5,
        target1=101.2,
        target2=102.2,
        invalidation=99.5,
        confidence=86,
        risk_reward=2.0,
        reasoning="Dashboard-only fast expansion test.",
        avoid_if="SPY loses impulse base.",
        status="watch_only",
    )
    sweep_setup = SetupSignal(
        symbol="IWM",
        setup_type="Liquidity sweep reversal",
        direction="LONG",
        timeframe="15m",
        created_at=base_time + timedelta(minutes=15),
        entry_low=200.0,
        entry_high=200.2,
        stop_loss=199.4,
        target1=201.2,
        target2=202.4,
        invalidation=199.4,
        confidence=98,
        risk_reward=2.0,
        reasoning="Balanced liquidity sweep candidate.",
        avoid_if="QQQ loses direction agreement.",
        status="watch_only",
    )

    fast_event_id = store.insert_source_paper_signal(
        fast_run_id,
        setup_id=1,
        setup=fast_setup,
        mode=LIVE_FAST_MOMENTUM_PAPER_SOURCE,
        source_key=FAST_MOMENTUM_SIGNAL_SOURCE,
        source_label=FAST_MOMENTUM_SOURCE_LABEL,
        notes="Synthetic open fast momentum row.",
    )
    sweep_event_id = store.insert_source_paper_signal(
        sweep_run_id,
        setup_id=2,
        setup=sweep_setup,
        mode=LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
        source_key=HIGH_POTENTIAL_LIQUIDITY_SWEEP_SIGNAL_SOURCE,
        source_label=HIGH_POTENTIAL_LIQUIDITY_SWEEP_SOURCE_LABEL,
        notes="Synthetic closed high-potential sweep row.",
    )
    store.update_paper_event_outcome(
        int(sweep_event_id),
        "win",
        1.25,
        {
            "mode": LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
            "signal_source": HIGH_POTENTIAL_LIQUIDITY_SWEEP_SIGNAL_SOURCE,
            "source_label": HIGH_POTENTIAL_LIQUIDITY_SWEEP_SOURCE_LABEL,
            "timeframe": "15m",
            "paper_only": True,
            "telegram_sent": False,
        },
    )

    fast_events = list_live_experimental_lane_paper_events(
        store,
        LIVE_FAST_MOMENTUM_PAPER_SOURCE,
    )
    summaries = experimental_lane_summaries(store)

    assert int(fast_event_id) == fast_events[0]["id"]
    assert fast_events[0]["outcome"] == "open"
    summary_by_source = {summary["paper_source"]: summary for summary in summaries}
    assert summary_by_source[LIVE_FAST_MOMENTUM_PAPER_SOURCE]["open_signals"] == 1
    assert summary_by_source[LIVE_FAST_MOMENTUM_PAPER_SOURCE]["closed_signals"] == 0
    assert summary_by_source[LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE][
        "open_signals"
    ] == 0
    assert summary_by_source[LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE][
        "closed_signals"
    ] == 1
    assert summary_by_source[LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE][
        "win_rate"
    ] == 100.0
    assert summary_by_source[LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE][
        "expectancy_r"
    ] == 1.25
    assert summary_by_source[LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE][
        "graduation_status"
    ] == "Collecting evidence"


def test_live_100_paper_outcomes_update_from_candles(tmp_path):
    settings = Settings(symbols=["SPY"], database_path=str(tmp_path / "live_outcomes.sqlite"))
    store = SQLiteStore(settings.database_file)
    run_id = store.get_or_create_paper_run("live_100_alerts", "2026-06-11", ["SPY"])
    alert_time = datetime(2026, 6, 11, 10, 0)
    setup = SetupSignal(
        symbol="SPY",
        setup_type="Liquidity sweep reversal",
        direction="LONG",
        timeframe="15m",
        created_at=alert_time,
        entry_low=100.0,
        entry_high=101.0,
        stop_loss=99.0,
        target1=103.5,
        target2=105.0,
        invalidation=99.0,
        confidence=100,
        risk_reward=2.0,
        reasoning="Synthetic live alert.",
        avoid_if="Synthetic invalidation.",
        market_condition="trending",
        status="alert_ready",
    )
    event_id = store.insert_live_paper_alert(run_id, alert_id=10, setup_id=20, setup=setup)
    store.upsert_candles(
        [
            Candle("SPY", "1m", alert_time + timedelta(minutes=1), 100.2, 100.8, 100.1, 100.6, 1000, "test"),
            Candle("SPY", "1m", alert_time + timedelta(minutes=2), 100.6, 102.1, 100.5, 101.9, 1200, "test"),
        ]
    )

    summary = refresh_live_100_outcomes(store)
    event = store.list_rows("paper_events", 1)[0]

    assert summary["wins"] == 1
    assert summary["losses"] == 0
    assert event["id"] == event_id
    assert event["outcome"] == "win"
    assert event["r_multiple"] == 1.0
    metadata = json.loads(event["metadata_json"])
    assert metadata["paper_management"] == "one_r"
    assert metadata["paper_target1"] == 102.0
    assert metadata["original_target1"] == 103.5
    assert metadata["path_metrics"]["resolution"] == "target1"


def test_live_paper_honors_existing_tactical_exit_alert(tmp_path):
    settings = Settings(symbols=["IWM"], database_path=str(tmp_path / "managed_win.sqlite"))
    store = SQLiteStore(settings.database_file)
    run_id = store.get_or_create_paper_run(
        LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
        "2026-06-25",
        ["IWM"],
    )
    alert_time = datetime(2026, 6, 25, 6, 53, 20)
    setup = SetupSignal(
        symbol="IWM",
        setup_type="Liquidity sweep reversal",
        direction="SHORT",
        timeframe="15m",
        created_at=alert_time,
        entry_low=299.37,
        entry_high=299.69,
        stop_loss=300.97,
        target1=298.09,
        target2=296.65,
        invalidation=300.97,
        confidence=98,
        risk_reward=1.0,
        reasoning="IWM failed above prior day high.",
        avoid_if="IWM reclaims the sweep high.",
        market_condition="balanced",
        status="alert_ready",
        features={
            "tactical_management": True,
            "tactical_exit_r_multiple": 1.0,
            "tactical_exit_price": 298.09,
            "tactical_exit_action": "COVER/PARTIAL",
        },
    )
    setup_id = store.insert_setup(setup)
    store.insert_alert(setup_id, setup, "original IWM liquidity alert", delivered=True)
    management_setup = SetupSignal(
        **{
            **setup.__dict__,
            "setup_type": "Suggested sell/partial",
            "created_at": alert_time + timedelta(minutes=8),
            "status": "management",
        }
    )
    store.insert_alert(
        setup_id,
        management_setup,
        "SUGGESTED COVER/PARTIAL IWM",
        delivered=True,
    )
    event_id = store.insert_source_paper_signal(
        run_id,
        setup_id=setup_id,
        setup=setup,
        mode=LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
        source_key=HIGH_POTENTIAL_LIQUIDITY_SWEEP_SIGNAL_SOURCE,
        source_label=HIGH_POTENTIAL_LIQUIDITY_SWEEP_SOURCE_LABEL,
        notes="Synthetic backfilled managed IWM row.",
        metadata={
            "original_core_setup_id": setup_id,
            "original_telegram_alert_sent": True,
        },
    )
    store.upsert_candles(
        [
            Candle("IWM", "1m", alert_time + timedelta(minutes=12), 298.83, 299.57, 298.83, 299.06, 1000, "test"),
            Candle("IWM", "1m", alert_time + timedelta(minutes=17), 299.97, 300.98, 299.97, 300.80, 1000, "test"),
        ]
    )

    summary = refresh_live_source_outcomes(
        store,
        lambda store_obj: list_live_experimental_lane_paper_events(
            store_obj,
            LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
        ),
    )
    event = store.list_rows("paper_events", 1)[0]

    assert event["id"] == event_id
    assert summary["wins"] == 1
    assert summary["losses"] == 0
    assert event["outcome"] == "win"
    assert event["r_multiple"] == 1.0
    metadata = json.loads(event["metadata_json"])
    assert metadata["path_metrics"]["resolution"] == "telegram_management_alert"


def test_current_live_100_paper_view_counts_only_core_strict_liquidity(tmp_path):
    settings = Settings(database_path=str(tmp_path / "current_strategy.sqlite"))
    store = SQLiteStore(settings.database_file)
    run_id = store.get_or_create_paper_run("live_100_alerts", "2026-06-11", ["SPY", "QQQ"])
    alert_time = datetime(2026, 6, 11, 10, 0)

    vwap_setup = SetupSignal(
        symbol="SPY",
        setup_type="VWAP reclaim + retest",
        direction="LONG",
        timeframe="15m",
        created_at=alert_time,
        entry_low=100.0,
        entry_high=100.2,
        stop_loss=99.5,
        target1=101.5,
        target2=102.5,
        invalidation=99.5,
        confidence=100,
        risk_reward=2.0,
        reasoning="Old VWAP paper row.",
        avoid_if="SPY loses VWAP.",
        status="alert_ready",
    )
    liquidity_setup = SetupSignal(
        symbol="QQQ",
        setup_type="Liquidity sweep reversal",
        direction="SHORT",
        timeframe="15m",
        created_at=alert_time + timedelta(minutes=1),
        entry_low=200.0,
        entry_high=200.2,
        stop_loss=201.0,
        target1=198.0,
        target2=197.0,
        invalidation=201.0,
        confidence=100,
        risk_reward=2.0,
        reasoning="Current liquidity setup.",
        avoid_if="QQQ reclaims sweep level.",
        status="alert_ready",
    )
    liquidity_30m_setup = SetupSignal(
        symbol="SPY",
        setup_type="Liquidity sweep reversal",
        direction="LONG",
        timeframe="30m",
        created_at=alert_time + timedelta(minutes=2),
        entry_low=101.0,
        entry_high=101.2,
        stop_loss=100.5,
        target1=102.5,
        target2=103.5,
        invalidation=100.5,
        confidence=100,
        risk_reward=2.0,
        reasoning="Current 30m liquidity setup.",
        avoid_if="SPY loses sweep level.",
        status="alert_ready",
    )
    liquidity_1h_setup = SetupSignal(
        symbol="QQQ",
        setup_type="Liquidity sweep reversal",
        direction="LONG",
        timeframe="1h",
        created_at=alert_time + timedelta(minutes=3),
        entry_low=202.0,
        entry_high=202.2,
        stop_loss=201.0,
        target1=204.0,
        target2=205.0,
        invalidation=201.0,
        confidence=100,
        risk_reward=2.0,
        reasoning="1h liquidity is context-only for current core metrics.",
        avoid_if="QQQ loses sweep level.",
        status="alert_ready",
    )
    expansion_setup = SetupSignal(
        symbol="SPY",
        setup_type="Fast momentum expansion",
        direction="LONG",
        timeframe="5m",
        created_at=alert_time + timedelta(minutes=4),
        entry_low=102.0,
        entry_high=102.2,
        stop_loss=101.5,
        target1=103.2,
        target2=104.2,
        invalidation=101.5,
        confidence=100,
        risk_reward=2.0,
        reasoning="Separate lane, not core strict.",
        avoid_if="Momentum fails.",
        status="alert_ready",
    )
    store.insert_live_paper_alert(run_id, alert_id=1, setup_id=10, setup=vwap_setup)
    store.insert_live_paper_alert(run_id, alert_id=2, setup_id=11, setup=liquidity_setup)
    store.insert_live_paper_alert(run_id, alert_id=3, setup_id=12, setup=liquidity_30m_setup)
    store.insert_live_paper_alert(run_id, alert_id=4, setup_id=13, setup=liquidity_1h_setup)
    store.insert_live_paper_alert(run_id, alert_id=5, setup_id=14, setup=expansion_setup)

    current_events = list_current_live_100_paper_events(
        store,
        [
            "VWAP reclaim + retest",
            "VWAP rejection + retest",
            "premarket high break + hold",
        ],
    )

    assert len(store.list_live_100_paper_events()) == 5
    assert len(current_events) == 2
    assert {event["setup_type"] for event in current_events} == {"Liquidity sweep reversal"}
    assert {
        json.loads(event["metadata_json"])["timeframe"] for event in current_events
    } == {"15m", "30m"}


def test_carter_put_paper_view_counts_only_short_side(tmp_path):
    settings = Settings(database_path=str(tmp_path / "carter_put.sqlite"))
    store = SQLiteStore(settings.database_file)
    run_id = store.get_or_create_paper_run(
        LIVE_CARTER_PAPER_SOURCE,
        "2026-06-11",
        ["SPY", "QQQ"],
    )
    alert_time = datetime(2026, 6, 11, 10, 0)

    short_setup = SetupSignal(
        symbol="SPY",
        setup_type="Carter Squeeze",
        direction="SHORT",
        timeframe="15m",
        created_at=alert_time,
        entry_low=100.0,
        entry_high=100.2,
        stop_loss=101.0,
        target1=98.5,
        target2=97.5,
        invalidation=101.0,
        confidence=88,
        risk_reward=2.0,
        reasoning="Trusted put-side Carter setup.",
        avoid_if="SPY reclaims squeeze trigger.",
        status="alert_ready",
    )
    long_setup = SetupSignal(
        symbol="QQQ",
        setup_type="Carter Squeeze",
        direction="LONG",
        timeframe="15m",
        created_at=alert_time + timedelta(minutes=1),
        entry_low=200.0,
        entry_high=200.2,
        stop_loss=199.0,
        target1=202.0,
        target2=203.0,
        invalidation=199.0,
        confidence=88,
        risk_reward=2.0,
        reasoning="Call-side Carter remains separate evidence.",
        avoid_if="QQQ loses squeeze trigger.",
        status="alert_ready",
    )
    store.insert_source_paper_signal(
        run_id,
        setup_id=20,
        setup=short_setup,
        mode=LIVE_CARTER_PAPER_SOURCE,
        source_key=CARTER_SIGNAL_SOURCE,
        source_label=CARTER_SOURCE_LABEL,
        notes="Synthetic Carter put-side paper row.",
    )
    store.insert_source_paper_signal(
        run_id,
        setup_id=21,
        setup=long_setup,
        mode=LIVE_CARTER_PAPER_SOURCE,
        source_key=CARTER_SIGNAL_SOURCE,
        source_label=CARTER_SOURCE_LABEL,
        notes="Synthetic Carter call-side paper row.",
    )

    put_events = list_live_carter_put_paper_events(store)

    assert len(put_events) == 1
    assert put_events[0]["symbol"] == "SPY"
    assert put_events[0]["direction"] == "SHORT"


def test_scanner_sends_tactical_exit_alert_once(tmp_path):
    settings = Settings(symbols=["SPY"], database_path=str(tmp_path / "sell.sqlite"))
    settings.research["enabled"] = False
    store = SQLiteStore(settings.database_file)
    setup_time = utc_now() - timedelta(minutes=10)
    setup = SetupSignal(
        symbol="SPY",
        setup_type="Liquidity sweep reversal",
        direction="LONG",
        timeframe="15m",
        created_at=setup_time,
        entry_low=100.0,
        entry_high=100.2,
        stop_loss=99.5,
        target1=101.4,
        target2=102.0,
        invalidation=99.5,
        confidence=100,
        risk_reward=2.0,
        reasoning="SPY swept and reclaimed prior day low.",
        avoid_if="SPY loses the sweep low.",
        status="alert_ready",
        features={
            "tactical_management": True,
            "tactical_exit_r_multiple": 1.0,
            "tactical_exit_price": 100.6,
            "tactical_exit_action": "SELL/PARTIAL",
        },
    )
    setup_id = store.insert_setup(setup)
    store.insert_alert(setup_id, setup, "original liquidity alert", delivered=True)
    candles = [
        Candle("SPY", "1m", setup_time + timedelta(minutes=1), 100.05, 100.2, 100.0, 100.1, 1000, "test"),
        Candle("SPY", "1m", setup_time + timedelta(minutes=2), 100.1, 100.65, 100.05, 100.6, 1200, "test"),
    ]
    telegram = RecordingTelegram()
    scanner = TradingScanner(
        settings,
        store,
        data_engine=TacticalExitDataEngine(candles),
        telegram=telegram,
    )
    scanner.strategy = EmptyStrategy()
    scanner.no_trade = FakeNoTrade()

    outcome = scanner.scan_once()

    assert any("suggested sell/partial" in item for item in outcome["alerts"])
    assert len(telegram.messages) == 1
    assert "SUGGESTED SELL/PARTIAL SPY" in telegram.messages[0]
    alerts = store.list_rows("alerts", 10)
    assert any(row["setup_type"] == "Suggested sell/partial" for row in alerts)


def test_scanner_suppresses_tactical_exit_for_currently_blocked_original_alert(tmp_path):
    settings = Settings(symbols=["IWM"], database_path=str(tmp_path / "blocked_sell.sqlite"))
    settings.research["enabled"] = False
    store = SQLiteStore(settings.database_file)
    setup_time = utc_now() - timedelta(minutes=10)
    setup = SetupSignal(
        symbol="IWM",
        setup_type="Liquidity sweep reversal",
        direction="SHORT",
        timeframe="15m",
        created_at=setup_time,
        entry_low=298.90,
        entry_high=299.10,
        stop_loss=299.75,
        target1=298.05,
        target2=297.20,
        invalidation=299.75,
        confidence=98,
        risk_reward=1.0,
        reasoning="IWM swept above prior day high and failed.",
        avoid_if="IWM reclaims the sweep high.",
        market_condition="balanced",
        status="alert_ready",
        features={
            "level_confluence": True,
            "vwap_confirmed": True,
            "volume_confirmed": True,
            "timeframe_aligned": True,
            "market_confirmed": False,
            "peer_biases": {
                "SPY": "bearish",
                "QQQ": "bearish",
                "IWM": "neutral",
            },
            "tactical_management": True,
            "tactical_exit_r_multiple": 1.0,
            "tactical_exit_price": 298.05,
            "tactical_exit_action": "COVER/PARTIAL",
        },
    )
    setup_id = store.insert_setup(setup)
    store.insert_alert(setup_id, setup, "original balanced liquidity alert", delivered=True)
    candles = [
        Candle("IWM", "1m", setup_time + timedelta(minutes=1), 299.0, 299.1, 298.8, 298.9, 1000, "test"),
        Candle("IWM", "1m", setup_time + timedelta(minutes=2), 298.9, 299.0, 298.0, 298.05, 1200, "test"),
    ]
    telegram = RecordingTelegram()
    scanner = TradingScanner(
        settings,
        store,
        data_engine=TacticalExitDataEngine(candles),
        telegram=telegram,
    )
    scanner.strategy = EmptyStrategy()
    scanner.no_trade = FakeNoTrade()

    outcome = scanner.scan_once()

    assert not any("suggested sell/partial" in item for item in outcome["alerts"])
    assert telegram.messages == []
    alerts = store.list_rows("alerts", 10)
    assert all(row["setup_type"] != "Suggested sell/partial" for row in alerts)


def test_historical_replay_records_paper_events(tmp_path):
    settings = Settings(database_path=str(tmp_path / "replay.sqlite"))
    store = SQLiteStore(settings.database_file)
    start = datetime(2026, 1, 2, 9, 30)
    for symbol, base in [("SPY", 100.0), ("QQQ", 200.0), ("IWM", 150.0)]:
        store.upsert_candles(one_minute_series(symbol, start, count=390, base=base))
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
    events = store.list_rows("paper_events", 5)
    assert events
    metadata = json.loads(events[0]["metadata_json"])
    assert "mfe_r" in metadata
    assert "mae_r" in metadata
    assert "path_metrics" in metadata
    assert metadata["replay_evaluated_on_completed_close"] is True
    assert _is_completed_replay_close(
        datetime.fromisoformat(events[0]["event_time"]), settings.alert_timeframes
    )


def test_replay_evaluates_on_completed_candle_closes(tmp_path):
    settings = Settings(database_path=str(tmp_path / "timing.sqlite"))
    store = SQLiteStore(settings.database_file)
    start = datetime(2026, 1, 2, 9, 30)
    for symbol, base in [("SPY", 100.0), ("QQQ", 200.0), ("IWM", 150.0)]:
        store.upsert_candles(one_minute_series(symbol, start, count=390, base=base))
        store.upsert_candles(
            [
                Candle(symbol, "1d", datetime(2026, 1, 1), base, base + 1, base - 1, base, 100000, "test"),
                Candle(symbol, "1d", datetime(2026, 1, 2), base, base + 99, base - 99, base, 100000, "test"),
            ]
        )

    replay = HistoricalReplay(settings, store)
    recorder = RecordingStrategy()
    replay.strategy = recorder
    replay.no_trade = FakeNoTrade()

    replay.run("2026-01-02", "2026-01-02")

    assert recorder.calls
    interval = min(TIMEFRAME_MINUTES[timeframe] for timeframe in settings.alert_timeframes)
    expected_close_minutes = {
        minute for minute in range(60) if (minute + 1) % interval == 0
    }
    for call in recorder.calls:
        latest_raw = call["latest_raw"]
        assert _is_completed_replay_close(latest_raw, settings.alert_timeframes)
        assert latest_raw.minute in expected_close_minutes
        for timeframe, completed in call["completed"].items():
            if not completed:
                continue
            minutes = TIMEFRAME_MINUTES[timeframe]
            assert completed[-1].timestamp + timedelta(minutes=minutes - 1) <= latest_raw


def test_replay_daily_context_uses_partial_current_day_without_lookahead():
    start = datetime(2026, 1, 2, 9, 30)
    current_intraday = one_minute_series("SPY", start, count=3, base=100.0, step=1.0)
    full_future_daily = Candle(
        "SPY",
        "1d",
        datetime(2026, 1, 2),
        100,
        999,
        1,
        500,
        100000,
        "test",
    )
    prior_daily = Candle(
        "SPY",
        "1d",
        datetime(2026, 1, 1),
        99,
        101,
        98,
        100,
        100000,
        "test",
    )

    context = _daily_context(
        current_intraday,
        [prior_daily, full_future_daily],
        start + timedelta(minutes=2),
    )

    assert len(context) == 2
    assert context[-1].timestamp == datetime(2026, 1, 2)
    assert context[-1].high == max(candle.high for candle in current_intraday)
    assert context[-1].low == min(candle.low for candle in current_intraday)
    assert context[-1].close == current_intraday[-1].close
    assert context[-1].high != full_future_daily.high


def test_paper_summary_separates_closed_open_blocked_and_suppressed(tmp_path):
    settings = Settings(database_path=str(tmp_path / "summary.sqlite"))
    store = SQLiteStore(settings.database_file)
    run_id = store.begin_paper_run("test", "2026-01-02", "2026-01-02", ["SPY"])
    event_time = datetime(2026, 1, 2, 10, 0)

    store.insert_paper_event(
        run_id,
        event_time,
        "SPY",
        "alerted",
        "win",
        r_multiple=2.0,
        metadata={"mfe_r": 2.0, "mae_r": 0.2},
    )
    store.insert_paper_event(
        run_id,
        event_time,
        "SPY",
        "alerted",
        "open",
        r_multiple=0.0,
        metadata={
            "mfe_r": 1.0,
            "mae_r": 0.6,
            "tactical_outcome": "win",
            "tactical_r_multiple": 1.0,
        },
    )
    store.insert_paper_event(run_id, event_time, "SPY", "blocked", "loss", r_multiple=-1.0)
    store.insert_paper_event(run_id, event_time, "SPY", "suppressed", "loss", r_multiple=-1.0)

    summary = store.paper_summary(run_id)

    assert summary["alerted_count"] == 2
    assert summary["closed_alerted_count"] == 1
    assert summary["open_alerted_count"] == 1
    assert summary["blocked_count"] == 1
    assert summary["suppressed_count"] == 1
    assert summary["win_rate"] == 100
    assert summary["total_r"] == 2
    assert summary["move_start_sample_size"] == 2
    assert summary["move_start_success_count"] == 2
    assert summary["move_start_rate"] == 100
    assert summary["avg_mfe_r"] == 1.5
    assert summary["tactical_sample_size"] == 1
    assert summary["tactical_win_rate"] == 100
    assert summary["tactical_total_r"] == 1


def test_paper_summary_filters_source_and_reports_r_metrics(tmp_path):
    settings = Settings(database_path=str(tmp_path / "source_summary.sqlite"))
    store = SQLiteStore(settings.database_file)
    run_id = store.begin_paper_run("test", "2026-01-02", "2026-01-02", ["SPY"])
    event_time = datetime(2026, 1, 2, 10, 0)

    store.insert_paper_event(
        run_id,
        event_time,
        "SPY",
        "alerted",
        "win",
        r_multiple=2.0,
        metadata={
            "signal_source": CARTER_SIGNAL_SOURCE,
            "source_label": CARTER_SOURCE_LABEL,
            "market_regime": "trend",
            "timeframe": "15m",
        },
    )
    store.insert_paper_event(
        run_id,
        event_time + timedelta(minutes=15),
        "SPY",
        "alerted",
        "loss",
        r_multiple=-1.0,
        metadata={
            "signal_source": CARTER_SIGNAL_SOURCE,
            "source_label": CARTER_SOURCE_LABEL,
            "market_regime": "chop",
            "timeframe": "15m",
        },
    )
    store.insert_paper_event(
        run_id,
        event_time,
        "QQQ",
        "alerted",
        "loss",
        r_multiple=-1.0,
        metadata={"signal_source": "core_model", "source_label": CORE_SOURCE_LABEL},
    )

    summary = store.paper_summary(run_id, signal_source=CARTER_SIGNAL_SOURCE)

    assert summary["alerted_count"] == 2
    assert summary["closed_alerted_count"] == 2
    assert summary["win_rate"] == 50
    assert summary["profit_factor"] == 2
    assert summary["avg_winner_r"] == 2
    assert summary["avg_loser_r"] == -1
    assert summary["winner_loser_ratio"] == 2
    assert summary["expectancy_r"] == 0.5
    assert summary["max_drawdown_r"] == -1
    assert summary["market_regime_breakdown"]["trend"]["win_rate"] == 100
    assert summary["market_regime_breakdown"]["chop"]["win_rate"] == 0
