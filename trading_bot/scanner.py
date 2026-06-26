from __future__ import annotations

import logging
import time
import json
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List
from zoneinfo import ZoneInfo

from trading_bot.alerts.telegram import (
    TelegramClient,
    format_alert,
    format_carter_squeeze_alert,
    format_tactical_exit_alert,
    tactical_exit_price,
)
from trading_bot.alert_policy import is_core_telegram_entry_allowed
from trading_bot.carter_squeeze import CarterSqueezeEngine
from trading_bot.data.market_data import (
    DataUnavailable,
    MarketDataEngine,
    completed_candles_for_timeframe,
    is_stale,
)
from trading_bot.failed_auction_trap import FailedAuctionTrapEngine
from trading_bot.levels.levels import LevelEngine
from trading_bot.models import Candle, SetupSignal
from trading_bot import live_paper
from trading_bot.psychology.no_trade import NoTradeEngine
from trading_bot.research.agent import current_session_date
from trading_bot.research.gating import apply_research_gate, research_gate_context
from trading_bot.scoring.scoring import (
    ConfidenceScorer,
    strict_liquidity_sweep_exception_allowed,
)
from trading_bot.scoring.selection import ranked_records
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
    LIVE_CARTER_PAPER_SOURCE,
    LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE,
    LIVE_FAST_MOMENTUM_PAPER_SOURCE,
    LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
    tag_alert_source,
)
from trading_bot.storage import SQLiteStore
from trading_bot.strategy.engine import StrategyEngine, fast_intraday_bias, trend_bias

logger = logging.getLogger(__name__)


def _parse_session_time(value: str) -> dt_time:
    hour, minute = str(value).split(":", 1)
    return dt_time(int(hour), int(minute))


def market_data_window_open(settings: Settings, now_utc: datetime) -> bool:
    local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(
        ZoneInfo(settings.timezone)
    )
    if local_now.weekday() >= 5:
        return False
    market_hours = settings.market_hours
    start = _parse_session_time(market_hours.get("premarket_start", "04:00"))
    end = _parse_session_time(market_hours.get("after_hours_end", "20:00"))
    return start <= local_now.time() <= end


class TradingScanner:
    def __init__(
        self,
        settings: Settings,
        store: SQLiteStore,
        data_engine: MarketDataEngine = None,
        telegram: TelegramClient = None,
    ):
        self.settings = settings
        self.store = store
        self.data_engine = data_engine or MarketDataEngine()
        self.telegram = telegram or TelegramClient()
        self.level_engine = LevelEngine()
        self.strategy = StrategyEngine()
        self.carter_squeeze = CarterSqueezeEngine(settings)
        self.failed_auction_trap = FailedAuctionTrapEngine(settings)
        self.no_trade = NoTradeEngine(settings)
        self.scorer = ConfidenceScorer(settings)

    def backfill(self, days: int = 5) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for symbol in self.settings.symbols:
            context = self.data_engine.fetch_symbol_context(symbol, days=days)
            symbol_count = 0
            for candles in context.values():
                symbol_count += self.store.upsert_candles(candles)
            levels = self.level_engine.compute_levels(
                symbol, context.get("1m", []), context.get("1d", [])
            )
            if levels:
                self.store.replace_levels(symbol, levels[0].session_date, levels)
            counts[symbol] = symbol_count
        return counts

    def scan_once(self) -> Dict[str, List[str]]:
        started_at = datetime.utcnow().replace(microsecond=0)
        result: Dict[str, List[str]] = {"alerts": [], "watch_only": [], "no_trade": [], "errors": []}
        if isinstance(self.data_engine, MarketDataEngine) and not market_data_window_open(
            self.settings, started_at
        ):
            result["no_trade"].append("Scanner paused: outside configured market-data window")
            self.store.insert_scan_heartbeat(
                started_at,
                datetime.utcnow().replace(microsecond=0),
                "paused",
                result,
            )
            return result

        contexts: Dict[str, Dict[str, List[Candle]]] = {}
        market_biases: Dict[str, str] = {}
        primary_timeframe = self.settings.alert_timeframes[0]
        research_gate = research_gate_context(self.settings, self.store, started_at)
        if research_gate.get("enabled") and research_gate.get("hard_block"):
            result["no_trade"].append(f"Research: {research_gate.get('reason')}")

        for symbol in self.settings.symbols:
            try:
                context = self.data_engine.fetch_symbol_context(symbol, days=5)
            except DataUnavailable as exc:
                message = f"{symbol}: {exc}"
                logger.warning(message)
                result["errors"].append(message)
                self.store.upsert_daily_review(
                    datetime.utcnow().date().isoformat(),
                    "low_quality",
                    notes=message,
                    no_trade_reason="stale or missing market data",
                )
                continue
            contexts[symbol] = context
            for candles in context.values():
                self.store.upsert_candles(candles)
            primary = completed_candles_for_timeframe(context, primary_timeframe)
            market_biases[symbol] = fast_intraday_bias(context, trend_bias(primary))

        result["alerts"].extend(self._send_tactical_exit_alerts(contexts))

        for symbol, context in contexts.items():
            intraday = context.get("1m", [])
            primary = completed_candles_for_timeframe(context, primary_timeframe)
            daily = context.get("1d", [])
            stale = is_stale(intraday, self.settings.stale_data_minutes)
            levels = self.level_engine.compute_levels(symbol, intraday, daily)
            if levels:
                self.store.replace_levels(symbol, levels[0].session_date, levels)

            no_trade_state = self.no_trade.evaluate(
                symbol, primary, levels, market_biases, stale_data=stale
            )
            no_trade_state = apply_research_gate(no_trade_state, research_gate)
            setups = self.strategy.detect(
                symbol,
                context,
                levels,
                market_biases,
                stale_data=stale,
                alert_timeframes=self.settings.alert_timeframes,
            )
            setups = _exclude_setup_types(setups, self.settings.excluded_setup_types)
            self._send_carter_squeeze_alerts(
                result,
                symbol,
                context,
                no_trade_state,
                market_biases,
            )
            self._record_failed_auction_trap_signals(
                result,
                symbol,
                context,
                levels,
                no_trade_state,
                market_biases,
            )
            if not setups:
                reason = no_trade_state.get("reason") or "No A+ setups detected"
                result["no_trade"].append(f"Core Model {symbol}: {reason}")
                self.store.upsert_daily_review(
                    datetime.utcnow().date().isoformat(),
                    no_trade_state.get("market_condition", "balanced"),
                    notes=f"{symbol}: {reason}",
                    no_trade_reason=reason,
                )
                continue

            scored_records = []
            for setup in setups:
                scored = self.scorer.score(setup, no_trade_state)
                tag_alert_source(scored, CORE_SIGNAL_SOURCE, CORE_SOURCE_LABEL)
                setup_id = self.store.insert_setup(scored)
                scored_records.append((scored, setup_id))

            dashboard_only_setup_ids = set()
            for scored, setup_id in scored_records:
                if _is_fast_momentum_experiment(scored) and self.scorer.is_alertable(scored):
                    self._record_fast_momentum_signal(result, scored, setup_id)
                    dashboard_only_setup_ids.add(setup_id)
                elif _is_high_potential_liquidity_sweep(scored, self.settings):
                    self._record_high_potential_liquidity_sweep(result, scored, setup_id)
                    dashboard_only_setup_ids.add(setup_id)

            dashboard_candidate_records = [
                record
                for record in ranked_records(scored_records)
                if record[1] not in dashboard_only_setup_ids
                and self.scorer.is_alertable(record[0])
            ]
            alertable_records = [
                record
                for record in dashboard_candidate_records
                if _core_telegram_alert_allowed(record[0])
            ]
            chosen_record = alertable_records[0] if alertable_records else None

            for scored, setup_id in scored_records:
                if chosen_record and setup_id == chosen_record[1]:
                    continue
                if setup_id in dashboard_only_setup_ids:
                    continue
                if self.scorer.is_alertable(scored):
                    if _core_telegram_alert_allowed(scored):
                        result["no_trade"].append(
                            f"{symbol}: lower-priority {scored.setup_type} suppressed"
                        )
                    else:
                        result["watch_only"].append(
                            f"Core Model {symbol}: {scored.timeframe} {scored.setup_type} "
                            f"{scored.confidence}/100 dashboard-only"
                        )
                else:
                    result["watch_only"].append(
                        f"{symbol}: {scored.timeframe} {scored.setup_type} {scored.confidence}/100"
                    )
            if not chosen_record:
                continue

            scored, setup_id = chosen_record
            if (
                not _daily_cap_override_allowed(scored)
                and self.store.alert_count_today_for_source(symbol, CORE_SIGNAL_SOURCE)
                >= self.settings.max_alerts_per_symbol_per_day
            ):
                result["no_trade"].append(f"Core Model {symbol}: daily alert cap reached")
                continue
            if self.store.has_recent_symbol_alert_for_source(
                symbol,
                int(self.settings.strategy.get("symbol_alert_cooldown_minutes", 30)),
                CORE_SIGNAL_SOURCE,
            ):
                result["no_trade"].append(f"Core Model {symbol}: symbol alert cooldown active")
                continue
            if self.store.has_recent_duplicate_alert_for_source(
                scored,
                int(self.settings.strategy.get("duplicate_alert_minutes", 90)),
                CORE_SIGNAL_SOURCE,
            ):
                result["no_trade"].append(f"Core Model {symbol}: duplicate alert suppressed")
                continue
            message = format_alert(scored)
            delivery = self.telegram.send_message(
                message,
                max_attempts=self.settings.telegram_max_attempts,
                retry_delay_seconds=self.settings.telegram_retry_delay_seconds,
            )
            alert_id = self.store.insert_alert(
                setup_id,
                scored,
                message,
                delivered=delivery.delivered,
                delivery_error=delivery.error,
            )
            if scored.confidence == 100:
                session_date = current_session_date(self.settings).isoformat()
                run_id = self.store.get_or_create_paper_run(
                    "live_100_alerts",
                    session_date,
                    self.settings.symbols,
                )
                self.store.insert_live_paper_alert(run_id, alert_id, setup_id, scored)
            self.store.insert_telegram_attempt(
                symbol=symbol,
                message=message,
                delivered=delivery.delivered,
                attempt_number=delivery.attempts,
                error=delivery.error,
                alert_id=alert_id,
                setup_id=setup_id,
            )
            result["alerts"].append(
                f"Core Model {symbol}: {scored.timeframe} {scored.setup_type} {scored.confidence}/100"
            )
        self._refresh_paper_outcomes(result)
        status = "degraded" if result["errors"] else "ok"
        self.store.insert_scan_heartbeat(
            started_at, datetime.utcnow().replace(microsecond=0), status, result
        )
        return result

    def _refresh_paper_outcomes(self, result: Dict[str, List[str]]) -> None:
        try:
            summaries = live_paper.refresh_all_live_outcomes(
                self.store,
                set(getattr(self.settings, "excluded_setup_types", []) or []),
            )
        except Exception as exc:
            logger.warning("Paper outcome refresh failed: %s", exc)
            result["errors"].append("Paper outcome refresh failed")
            return
        updated = sum(int(summary.get("updated", 0) or 0) for summary in summaries.values())
        locked_lanes = [
            lane for lane, summary in summaries.items() if summary.get("error") == "database_locked"
        ]
        if updated:
            result["watch_only"].append(f"Paper tracking: updated {updated} outcome(s)")
        if locked_lanes:
            result["no_trade"].append(
                "Paper tracking refresh skipped while database was busy: "
                + ", ".join(sorted(locked_lanes))
            )

    def _send_carter_squeeze_alerts(
        self,
        result: Dict[str, List[str]],
        symbol: str,
        context: Dict[str, List[Candle]],
        no_trade_state: Dict,
        market_biases: Dict[str, str],
    ) -> None:
        setups = self.carter_squeeze.detect(
            symbol,
            context,
            market_biases,
            no_trade_state=no_trade_state,
        )
        if not setups:
            return
        records = []
        for setup in setups:
            setup_id = self.store.insert_setup(setup)
            records.append((setup, setup_id))

        alertable = [record for record in ranked_records(records) if self.carter_squeeze.is_alertable(record[0])]
        chosen = alertable[0] if alertable else None
        for setup, _setup_id in records:
            if chosen and setup is chosen[0]:
                continue
            if setup.status == "blocked":
                result["no_trade"].append(
                    f"Carter Squeeze {symbol}: {setup.setup_type} blocked at {setup.confidence}/100"
                )
            else:
                result["watch_only"].append(
                    f"Carter Squeeze {symbol}: {setup.timeframe} {setup.setup_type} {setup.confidence}/100"
                )
        if not chosen:
            return

        setup, setup_id = chosen
        cfg = self.settings.carter_squeeze
        if (
            self.store.alert_count_today_for_source(symbol, CARTER_SIGNAL_SOURCE)
            >= int(cfg.get("max_alerts_per_symbol_per_day", 2))
        ):
            result["no_trade"].append(f"Carter Squeeze {symbol}: daily alert cap reached")
            return
        if self.store.has_recent_symbol_alert_for_source(
            symbol,
            int(cfg.get("symbol_alert_cooldown_minutes", 30)),
            CARTER_SIGNAL_SOURCE,
        ):
            result["no_trade"].append(f"Carter Squeeze {symbol}: symbol alert cooldown active")
            return
        if self.store.has_recent_duplicate_alert_for_source(
            setup,
            int(cfg.get("duplicate_alert_minutes", 90)),
            CARTER_SIGNAL_SOURCE,
        ):
            result["no_trade"].append(f"Carter Squeeze {symbol}: duplicate alert suppressed")
            return

        message = format_carter_squeeze_alert(setup)
        delivery = self.telegram.send_message(
            message,
            max_attempts=self.settings.telegram_max_attempts,
            retry_delay_seconds=self.settings.telegram_retry_delay_seconds,
        )
        alert_id = self.store.insert_alert(
            setup_id,
            setup,
            message,
            delivered=delivery.delivered,
            delivery_error=delivery.error,
        )
        session_date = current_session_date(self.settings).isoformat()
        run_id = self.store.get_or_create_paper_run(
            LIVE_CARTER_PAPER_SOURCE,
            session_date,
            [symbol],
        )
        self.store.insert_source_paper_alert(
            run_id=run_id,
            alert_id=alert_id,
            setup_id=setup_id,
            setup=setup,
            mode=LIVE_CARTER_PAPER_SOURCE,
            source_key=CARTER_SIGNAL_SOURCE,
            source_label=CARTER_SOURCE_LABEL,
            notes="Auto-paper trade from Carter Squeeze alert. Alert-only; no real order placed.",
        )
        self.store.insert_telegram_attempt(
            symbol=symbol,
            message=message,
            delivered=delivery.delivered,
            attempt_number=delivery.attempts,
            error=delivery.error,
            alert_id=alert_id,
            setup_id=setup_id,
        )
        result["alerts"].append(
            f"Carter Squeeze {symbol}: {setup.timeframe} {setup.setup_type} {setup.confidence}/100"
        )

    def _record_failed_auction_trap_signals(
        self,
        result: Dict[str, List[str]],
        symbol: str,
        context: Dict[str, List[Candle]],
        levels,
        no_trade_state: Dict,
        market_biases: Dict[str, str],
    ) -> None:
        setups = self.failed_auction_trap.detect(
            symbol,
            context,
            levels=levels,
            market_biases=market_biases,
            no_trade_state=no_trade_state,
        )
        if not setups:
            return
        records = []
        for setup in setups:
            setup_id = self.store.insert_setup(setup)
            records.append((setup, setup_id))

        trackable = [
            record
            for record in ranked_records(records)
            if self.failed_auction_trap.is_paper_trackable(record[0])
        ]
        chosen = trackable[0] if trackable else None
        for setup, _setup_id in records:
            if chosen and setup is chosen[0]:
                continue
            result["watch_only"].append(
                f"Failed Auction Trap {symbol}: {setup.timeframe} {setup.setup_type} "
                f"{setup.direction} {setup.confidence}/100 dashboard-only"
            )
        if not chosen:
            return

        setup, setup_id = chosen
        session_date = current_session_date(self.settings).isoformat()
        run_id = self.store.get_or_create_paper_run(
            LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE,
            session_date,
            [symbol],
        )
        event_id = self.store.insert_source_paper_signal(
            run_id=run_id,
            setup_id=setup_id,
            setup=setup,
            mode=LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE,
            source_key=FAILED_AUCTION_TRAP_SIGNAL_SOURCE,
            source_label=FAILED_AUCTION_TRAP_SOURCE_LABEL,
            notes=(
                "Dashboard-only paper trade from Failed Auction Trap experiment. "
                "No Telegram alert sent; no real order placed."
            ),
        )
        if event_id is None:
            result["no_trade"].append(f"Failed Auction Trap {symbol}: duplicate paper signal suppressed")
            return
        result["watch_only"].append(
            f"Failed Auction Trap {symbol}: {setup.timeframe} {setup.direction} "
            f"{setup.confidence}/100 paper-tracked dashboard-only"
        )

    def _record_fast_momentum_signal(
        self,
        result: Dict[str, List[str]],
        setup: SetupSignal,
        setup_id: int,
    ) -> None:
        session_date = current_session_date(self.settings).isoformat()
        run_id = self.store.get_or_create_paper_run(
            LIVE_FAST_MOMENTUM_PAPER_SOURCE,
            session_date,
            [setup.symbol],
        )
        event_id = self.store.insert_source_paper_signal(
            run_id=run_id,
            setup_id=setup_id,
            setup=setup,
            mode=LIVE_FAST_MOMENTUM_PAPER_SOURCE,
            source_key=FAST_MOMENTUM_SIGNAL_SOURCE,
            source_label=FAST_MOMENTUM_SOURCE_LABEL,
            notes=(
                "Dashboard-only paper trade from Fast Momentum Expansion experiment. "
                "No Telegram alert sent; no real order placed."
            ),
        )
        if event_id is None:
            result["no_trade"].append(f"Fast Momentum {setup.symbol}: duplicate paper signal suppressed")
            return
        result["watch_only"].append(
            f"Fast Momentum {setup.symbol}: {setup.timeframe} {setup.direction} "
            f"{setup.confidence}/100 paper-tracked dashboard-only"
        )

    def _record_high_potential_liquidity_sweep(
        self,
        result: Dict[str, List[str]],
        setup: SetupSignal,
        setup_id: int,
    ) -> None:
        score_breakdown = (setup.features or {}).get("score_breakdown") or {}
        raw_score = int(score_breakdown.get("raw_score") or setup.confidence or 0)
        paper_setup = SetupSignal(
            **{
                **setup.__dict__,
                "confidence": raw_score,
                "status": "watch_only",
                "features": {
                    **(setup.features or {}),
                    "blocked_core_confidence": setup.confidence,
                    "candidate_raw_score": raw_score,
                },
            }
        )
        session_date = current_session_date(self.settings).isoformat()
        run_id = self.store.get_or_create_paper_run(
            LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
            session_date,
            [setup.symbol],
        )
        event_id = self.store.insert_source_paper_signal(
            run_id=run_id,
            setup_id=setup_id,
            setup=paper_setup,
            mode=LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
            source_key=HIGH_POTENTIAL_LIQUIDITY_SWEEP_SIGNAL_SOURCE,
            source_label=HIGH_POTENTIAL_LIQUIDITY_SWEEP_SOURCE_LABEL,
            notes=(
                "Dashboard-only paper trade from High-Potential Balanced Liquidity Sweep lane. "
                "No Telegram alert sent; no real order placed."
            ),
            metadata={
                "blocked_core_confidence": setup.confidence,
                "candidate_raw_score": raw_score,
            },
        )
        if event_id is None:
            result["no_trade"].append(
                f"High-Potential Liquidity {setup.symbol}: duplicate paper signal suppressed"
            )
            return
        result["watch_only"].append(
            f"High-Potential Liquidity {setup.symbol}: {setup.timeframe} {setup.direction} "
            f"{raw_score}/100 paper-tracked dashboard-only"
        )

    def _send_tactical_exit_alerts(self, contexts: Dict[str, Dict[str, List[Candle]]]) -> List[str]:
        sent = []
        since = datetime.utcnow().replace(microsecond=0) - timedelta(days=1)
        for row in self.store.list_tactical_exit_candidates(since):
            symbol = row["symbol"]
            one_minute = contexts.get(symbol, {}).get("1m", [])
            if not one_minute:
                continue
            setup = _setup_from_row(row)
            exit_price = tactical_exit_price(setup)
            if exit_price is None:
                continue
            if _tactical_exit_state(setup, one_minute, exit_price) != "target":
                continue
            if not _tactical_exit_followup_allowed(setup, self.settings):
                continue
            message = format_tactical_exit_alert(
                setup,
                price=exit_price,
                original_alert_id=row.get("original_alert_id"),
            )
            delivery = self.telegram.send_message(
                message,
                max_attempts=self.settings.telegram_max_attempts,
                retry_delay_seconds=self.settings.telegram_retry_delay_seconds,
            )
            management_setup = SetupSignal(
                symbol=setup.symbol,
                setup_type="Suggested sell/partial",
                direction=setup.direction,
                timeframe=setup.timeframe,
                created_at=datetime.utcnow().replace(microsecond=0),
                entry_low=setup.entry_low,
                entry_high=setup.entry_high,
                stop_loss=setup.stop_loss,
                target1=exit_price,
                target2=setup.target2,
                invalidation=setup.invalidation,
                confidence=setup.confidence,
                risk_reward=setup.risk_reward,
                reasoning=f"{setup.setup_type} reached tactical +1R management.",
                avoid_if=setup.avoid_if,
                market_condition=setup.market_condition,
                status="management",
                features=setup.features,
            )
            alert_id = self.store.insert_alert(
                row.get("setup_id"),
                management_setup,
                message,
                delivered=delivery.delivered,
                delivery_error=delivery.error,
            )
            self.store.insert_telegram_attempt(
                symbol=symbol,
                message=message,
                delivered=delivery.delivered,
                attempt_number=delivery.attempts,
                error=delivery.error,
                alert_id=alert_id,
                setup_id=row.get("setup_id"),
            )
            sent.append(f"{symbol}: suggested sell/partial at {exit_price:.2f}")
        return sent

    def run_forever(self) -> None:
        logger.info("Starting scanner for %s", ", ".join(self.settings.symbols))
        while True:
            try:
                outcome = self.scan_once()
                logger.info("Scan outcome: %s", outcome)
            except KeyboardInterrupt:
                logger.info("Scanner stopped by user")
                raise
            except Exception:
                logger.exception("Scanner cycle failed")
                now = datetime.utcnow().replace(microsecond=0)
                self.store.insert_scan_heartbeat(
                    now,
                    now,
                    "failed",
                    {"alerts": [], "watch_only": [], "no_trade": [], "errors": ["scanner cycle failed"]},
                )
            time.sleep(self.settings.scan_cadence_seconds)


def _setup_from_row(row: Dict) -> SetupSignal:
    try:
        features = json.loads(row.get("features_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        features = {}
    return SetupSignal(
        symbol=row["symbol"],
        setup_type=row["setup_type"],
        direction=row["direction"],
        timeframe=row["timeframe"],
        created_at=datetime.fromisoformat(row["setup_created_at"]),
        entry_low=float(row["entry_low"]),
        entry_high=float(row["entry_high"]),
        stop_loss=float(row["stop_loss"]),
        target1=float(row["target1"]),
        target2=float(row["target2"]),
        invalidation=float(row["invalidation"]),
        confidence=int(row["confidence"] or 0),
        risk_reward=float(row["risk_reward"] or 0),
        reasoning=row.get("reasoning") or "",
        avoid_if=row.get("avoid_if") or "",
        market_condition=row.get("market_condition") or "unknown",
        status=row.get("status") or "candidate",
        features=features,
    )


def _exclude_setup_types(
    setups: List[SetupSignal], excluded_setup_types: List[str]
) -> List[SetupSignal]:
    excluded = {str(setup_type) for setup_type in excluded_setup_types or []}
    if not excluded:
        return setups
    return [setup for setup in setups if setup.setup_type not in excluded]


def _is_fast_momentum_experiment(setup: SetupSignal) -> bool:
    return (
        setup.setup_type == "Fast momentum expansion"
        or bool((setup.features or {}).get("fast_momentum_expansion"))
    )


def _is_high_potential_liquidity_sweep(setup: SetupSignal, settings: Settings) -> bool:
    if setup.setup_type != "Liquidity sweep reversal":
        return False
    if str(setup.timeframe) not in {"15m", "30m"}:
        return False
    if str(setup.market_condition or "").lower() not in {"balanced", "mixed", "chop"}:
        return False
    score_breakdown = (setup.features or {}).get("score_breakdown") or {}
    raw_score = int(score_breakdown.get("raw_score") or setup.confidence or 0)
    if raw_score < 90 or raw_score > 99:
        return False
    if setup.risk_reward < float(settings.strategy.get("min_risk_reward", 1.0)):
        return False
    expected_bias = "bullish" if str(setup.direction).upper() == "LONG" else "bearish"
    peer_biases = (setup.features or {}).get("peer_biases") or {}
    required_symbols = settings.strategy.get("strict_index_alignment_symbols") or [
        "SPY",
        "QQQ",
    ]
    if isinstance(required_symbols, str):
        required_symbols = [
            symbol.strip()
            for symbol in required_symbols.split(",")
            if symbol.strip()
        ]
    return all(
        str(peer_biases.get(symbol, "")).lower() == expected_bias
        for symbol in required_symbols
    )


def _daily_cap_override_allowed(setup: SetupSignal) -> bool:
    return (
        setup.setup_type == "Liquidity sweep reversal"
        and int(setup.confidence or 0) >= 100
        and setup.status == "alert_ready"
    )


def _core_telegram_alert_allowed(setup: SetupSignal) -> bool:
    return is_core_telegram_entry_allowed(setup.__dict__)


def _tactical_exit_followup_allowed(setup: SetupSignal, settings: Settings) -> bool:
    if setup.status != "alert_ready" or setup.confidence < settings.alert_threshold:
        return False
    market_condition = str(setup.market_condition or "").lower()
    if market_condition not in {"balanced", "mixed", "chop"}:
        return True
    return strict_liquidity_sweep_exception_allowed(
        setup,
        setup.features or {},
        int(setup.confidence or 0),
        settings,
    )


def _tactical_exit_state(
    setup: SetupSignal, one_minute: List[Candle], exit_price: float
) -> str:
    active_candles = [
        candle for candle in one_minute if candle.timestamp > setup.created_at
    ]
    triggered = False
    for candle in active_candles:
        if not triggered and candle.low <= setup.entry_high and candle.high >= setup.entry_low:
            triggered = True
        if not triggered:
            continue
        if setup.direction.upper() == "LONG":
            stopped = candle.low <= setup.stop_loss
            target_hit = candle.high >= exit_price
        else:
            stopped = candle.high >= setup.stop_loss
            target_hit = candle.low <= exit_price
        if stopped:
            return "stop"
        if target_hit:
            return "target"
    return "open" if triggered else "not_triggered"
