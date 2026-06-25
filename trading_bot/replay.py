from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from trading_bot.data.market_data import (
    TIMEFRAME_MINUTES,
    completed_candles_for_timeframe,
    is_stale,
    resample_candles,
)
from trading_bot.carter_squeeze import CarterSqueezeEngine
from trading_bot.levels.levels import LevelEngine
from trading_bot.models import Candle, SetupSignal
from trading_bot.failed_auction_trap import FailedAuctionTrapEngine
from trading_bot.psychology.no_trade import NoTradeEngine
from trading_bot.scoring.scoring import ConfidenceScorer
from trading_bot.scoring.selection import ranked_setups
from trading_bot.settings import Settings
from trading_bot.signal_sources import (
    CARTER_SIGNAL_SOURCE,
    CARTER_SOURCE_LABEL,
    CORE_SIGNAL_SOURCE,
    CORE_SOURCE_LABEL,
    FAILED_AUCTION_TRAP_SIGNAL_SOURCE,
    FAILED_AUCTION_TRAP_SOURCE_LABEL,
    FEATURE_ALERT_SOURCE,
    FEATURE_SOURCE_LABEL,
    tag_alert_source,
)
from trading_bot.storage import SQLiteStore
from trading_bot.strategy.engine import StrategyEngine, fast_intraday_bias, trend_bias


class HistoricalReplay:
    def __init__(self, settings: Settings, store: SQLiteStore):
        self.settings = settings
        self.store = store
        self.level_engine = LevelEngine()
        self.strategy = StrategyEngine()
        self.carter_squeeze = CarterSqueezeEngine(settings)
        self.failed_auction_trap = FailedAuctionTrapEngine(settings)
        self.no_trade = NoTradeEngine(settings)
        self.scorer = ConfidenceScorer(settings)

    def run(
        self,
        start_date: str,
        end_date: str,
        symbols: Optional[List[str]] = None,
        csv_dir: Optional[Path] = None,
    ) -> Dict:
        symbols = symbols or self.settings.symbols
        start, end = _date_bounds(start_date, end_date)
        warmup_start = start - timedelta(days=7)
        source = f"csv:{csv_dir}" if csv_dir else "sqlite"
        run_id = self.store.begin_paper_run(source, start_date, end_date, symbols)
        one_minute = self._load_one_minute(symbols, warmup_start, end, csv_dir)
        daily = {
            symbol: self.store.candles_between(symbol, "1d", start - timedelta(days=30), end)
            for symbol in symbols
        }
        timeline = sorted({c.timestamp for candles in one_minute.values() for c in candles})
        current: Dict[str, List[Candle]] = {symbol: [] for symbol in symbols}
        indexes = {symbol: 0 for symbol in symbols}
        last_event_at: Dict[Tuple, datetime] = {}
        alert_counts: Dict[Tuple[str, str, date], int] = {}
        last_symbol_alert_at: Dict[Tuple[str, str, date], datetime] = {}
        duplicate_minutes = int(self.settings.strategy.get("duplicate_alert_minutes", 90))
        symbol_cooldown_minutes = int(
            self.settings.strategy.get("symbol_alert_cooldown_minutes", 30)
        )
        primary_timeframe = self.settings.alert_timeframes[0]
        evaluation_interval = _evaluation_interval_minutes(self.settings.alert_timeframes)

        try:
            for ts in timeline:
                for symbol in symbols:
                    candles = one_minute.get(symbol, [])
                    index = indexes[symbol]
                    while index < len(candles) and candles[index].timestamp <= ts:
                        current[symbol].append(candles[index])
                        index += 1
                    indexes[symbol] = index

                if ts < start or ts > end:
                    continue

                if not _is_completed_replay_close(ts, self.settings.alert_timeframes):
                    continue

                contexts = {
                    symbol: self._context(symbol, candles, daily.get(symbol, []), ts)
                    for symbol, candles in current.items()
                    if candles
                }
                market_biases = {
                    symbol: fast_intraday_bias(
                        context,
                        trend_bias(completed_candles_for_timeframe(context, primary_timeframe)),
                    )
                    for symbol, context in contexts.items()
                }

                for symbol, context in contexts.items():
                    intraday = context["1m"]
                    primary = completed_candles_for_timeframe(context, primary_timeframe)
                    if len(primary) < 20:
                        continue
                    levels = self.level_engine.compute_levels(
                        symbol, intraday, context.get("1d", [])
                    )
                    stale = is_stale(intraday, self.settings.stale_data_minutes, now=ts)
                    no_trade_state = self.no_trade.evaluate(
                        symbol, primary, levels, market_biases, stale_data=stale
                    )
                    setups = self.strategy.detect(
                        symbol,
                        context,
                        levels,
                        market_biases,
                        stale_data=stale,
                        alert_timeframes=self.settings.alert_timeframes,
                    )
                    setups = _exclude_setup_types(setups, self.settings.excluded_setup_types)
                    scored_records = []
                    for setup in setups:
                        setup.created_at = ts
                        scored = self.scorer.score(setup, no_trade_state)
                        tag_alert_source(scored, CORE_SIGNAL_SOURCE, CORE_SOURCE_LABEL)
                        key = _setup_key(scored, ts.date(), CORE_SIGNAL_SOURCE)
                        prior = last_event_at.get(key)
                        duplicate_active = (
                            prior is not None
                            and (ts - prior).total_seconds() / 60 < duplicate_minutes
                        )
                        outcome, r_multiple, path_metrics = _outcome_metrics_for_setup(
                            scored, _future_candles(one_minute[symbol], ts)
                        )
                        scored_records.append(
                            (scored, key, outcome, r_multiple, path_metrics, duplicate_active)
                        )

                    self._record_replay_records(
                        run_id=run_id,
                        event_time=ts,
                        symbol=symbol,
                        records=scored_records,
                        alert_counts=alert_counts,
                        last_symbol_alert_at=last_symbol_alert_at,
                        last_event_at=last_event_at,
                        source_key=CORE_SIGNAL_SOURCE,
                        source_label=CORE_SOURCE_LABEL,
                        duplicate_minutes=duplicate_minutes,
                        symbol_cooldown_minutes=symbol_cooldown_minutes,
                        max_alerts_per_day=self.settings.max_alerts_per_symbol_per_day,
                        evaluation_interval=evaluation_interval,
                    )

                    carter_records = []
                    for setup in self.carter_squeeze.detect(
                        symbol,
                        context,
                        market_biases,
                        no_trade_state=no_trade_state,
                    ):
                        setup.created_at = ts
                        key = _setup_key(setup, ts.date(), CARTER_SIGNAL_SOURCE)
                        prior = last_event_at.get(key)
                        carter_duplicate_minutes = int(
                            self.settings.carter_squeeze.get("duplicate_alert_minutes", 90)
                        )
                        duplicate_active = (
                            prior is not None
                            and (ts - prior).total_seconds() / 60 < carter_duplicate_minutes
                        )
                        outcome, r_multiple, path_metrics = _outcome_metrics_for_setup(
                            setup, _future_candles(one_minute[symbol], ts)
                        )
                        carter_records.append(
                            (setup, key, outcome, r_multiple, path_metrics, duplicate_active)
                        )
                    self._record_replay_records(
                        run_id=run_id,
                        event_time=ts,
                        symbol=symbol,
                        records=carter_records,
                        alert_counts=alert_counts,
                        last_symbol_alert_at=last_symbol_alert_at,
                        last_event_at=last_event_at,
                        source_key=CARTER_SIGNAL_SOURCE,
                        source_label=CARTER_SOURCE_LABEL,
                        duplicate_minutes=int(
                            self.settings.carter_squeeze.get("duplicate_alert_minutes", 90)
                        ),
                        symbol_cooldown_minutes=int(
                            self.settings.carter_squeeze.get("symbol_alert_cooldown_minutes", 30)
                        ),
                        max_alerts_per_day=int(
                            self.settings.carter_squeeze.get("max_alerts_per_symbol_per_day", 2)
                        ),
                        evaluation_interval=evaluation_interval,
                    )

                    trap_records = []
                    for setup in self.failed_auction_trap.detect(
                        symbol,
                        context,
                        levels=levels,
                        market_biases=market_biases,
                        no_trade_state=no_trade_state,
                    ):
                        setup.created_at = ts
                        key = _setup_key(setup, ts.date(), FAILED_AUCTION_TRAP_SIGNAL_SOURCE)
                        prior = last_event_at.get(key)
                        trap_duplicate_minutes = int(
                            self.settings.failed_auction_trap.get("duplicate_alert_minutes", 90)
                        )
                        duplicate_active = (
                            prior is not None
                            and (ts - prior).total_seconds() / 60 < trap_duplicate_minutes
                        )
                        outcome, r_multiple, path_metrics = _outcome_metrics_for_setup(
                            setup, _future_candles(one_minute[symbol], ts)
                        )
                        trap_records.append(
                            (setup, key, outcome, r_multiple, path_metrics, duplicate_active)
                        )
                    self._record_replay_records(
                        run_id=run_id,
                        event_time=ts,
                        symbol=symbol,
                        records=trap_records,
                        alert_counts=alert_counts,
                        last_symbol_alert_at=last_symbol_alert_at,
                        last_event_at=last_event_at,
                        source_key=FAILED_AUCTION_TRAP_SIGNAL_SOURCE,
                        source_label=FAILED_AUCTION_TRAP_SOURCE_LABEL,
                        duplicate_minutes=int(
                            self.settings.failed_auction_trap.get("duplicate_alert_minutes", 90)
                        ),
                        symbol_cooldown_minutes=int(
                            self.settings.failed_auction_trap.get("symbol_alert_cooldown_minutes", 30)
                        ),
                        max_alerts_per_day=int(
                            self.settings.failed_auction_trap.get("max_alerts_per_symbol_per_day", 3)
                        ),
                        evaluation_interval=evaluation_interval,
                    )

            summary = self.store.paper_summary(run_id)
            self.store.finish_paper_run(run_id, "completed", summary)
            return {"run_id": run_id, **summary}
        except Exception as exc:
            summary = {"error": str(exc), **self.store.paper_summary(run_id)}
            self.store.finish_paper_run(run_id, "failed", summary)
            raise

    def _record_replay_records(
        self,
        run_id: int,
        event_time: datetime,
        symbol: str,
        records: List[Tuple[SetupSignal, Tuple, str, Optional[float], Dict, bool]],
        alert_counts: Dict[Tuple[str, str, date], int],
        last_symbol_alert_at: Dict[Tuple[str, str, date], datetime],
        last_event_at: Dict[Tuple, datetime],
        source_key: str,
        source_label: str,
        duplicate_minutes: int,
        symbol_cooldown_minutes: int,
        max_alerts_per_day: int,
        evaluation_interval: int,
    ) -> None:
        del duplicate_minutes
        if not records:
            return
        ranked_alerts = [
            setup
            for setup in ranked_setups(record[0] for record in records)
            if setup.status == "alert_ready"
        ]
        chosen_setup = ranked_alerts[0] if ranked_alerts else None

        for (
            scored,
            key,
            outcome,
            r_multiple,
            path_metrics,
            duplicate_active,
        ) in records:
            alert_key = (source_key, symbol, event_time.date())
            prior_alert_count = alert_counts.get(alert_key, 0)
            last_symbol_alert = last_symbol_alert_at.get(alert_key)
            cooldown_active = (
                last_symbol_alert is not None
                and (event_time - last_symbol_alert).total_seconds() / 60 < symbol_cooldown_minutes
            )
            lower_priority = (
                scored.status == "alert_ready"
                and chosen_setup is not None
                and scored is not chosen_setup
            )
            event_type = _event_type(scored, outcome)
            suppression_reason = ""
            if scored.status == "alert_ready":
                if duplicate_active:
                    event_type = "suppressed"
                    suppression_reason = "duplicate setup suppressed"
                elif prior_alert_count >= max_alerts_per_day:
                    event_type = "suppressed"
                    suppression_reason = "daily alert cap reached"
                elif cooldown_active:
                    event_type = "suppressed"
                    suppression_reason = "symbol alert cooldown active"
                elif lower_priority:
                    event_type = "suppressed"
                    suppression_reason = "lower-priority setup suppressed"
                else:
                    event_type = "alerted"
            if event_type == "alerted":
                alert_counts[alert_key] = prior_alert_count + 1
                last_symbol_alert_at[alert_key] = event_time
            cap_note = (
                "daily alert cap reached"
                if scored.status == "alert_ready" and prior_alert_count >= max_alerts_per_day
                else ""
            )
            cooldown_note = (
                "symbol alert cooldown active"
                if scored.status == "alert_ready" and cooldown_active
                else ""
            )
            priority_note = "lower-priority setup suppressed" if lower_priority else ""
            metadata = {
                "status": scored.status,
                "signal_source": source_key,
                FEATURE_ALERT_SOURCE: source_key,
                FEATURE_SOURCE_LABEL: source_label,
                "suppression_reason": suppression_reason,
                "market_condition": scored.market_condition,
                "market_regime": (scored.features or {}).get(
                    "market_regime", scored.market_condition
                ),
                "timeframe": scored.timeframe,
                "triggered": path_metrics.get("triggered"),
                "triggered_at": path_metrics.get("triggered_at"),
                "mfe_r": path_metrics.get("mfe_r"),
                "mae_r": path_metrics.get("mae_r"),
                "move_start_success": path_metrics.get("move_start_success"),
                "tactical_exit_price": path_metrics.get("tactical_exit_price"),
                "tactical_outcome": path_metrics.get("tactical_outcome"),
                "tactical_r_multiple": path_metrics.get("tactical_r_multiple"),
                "replay_evaluated_on_completed_close": True,
                "replay_evaluation_interval_minutes": evaluation_interval,
                "replay_latest_1m_at": event_time.isoformat(),
                "path_metrics": path_metrics,
                "score_breakdown": scored.features.get("score_breakdown", {}),
                "features": scored.features,
            }
            self.store.insert_paper_event(
                run_id=run_id,
                event_time=event_time,
                symbol=symbol,
                event_type=event_type,
                setup_type=scored.setup_type,
                direction=scored.direction,
                confidence=scored.confidence,
                risk_reward=scored.risk_reward,
                entry_low=scored.entry_low,
                entry_high=scored.entry_high,
                stop_loss=scored.stop_loss,
                target1=scored.target1,
                outcome=outcome,
                r_multiple=r_multiple,
                notes=suppression_reason
                or cap_note
                or cooldown_note
                or priority_note
                or scored.features.get("score_breakdown", {}).get("no_trade_reason", ""),
                metadata=metadata,
            )
            last_event_at[key] = event_time

    def _load_one_minute(
        self,
        symbols: List[str],
        start: datetime,
        end: datetime,
        csv_dir: Optional[Path],
    ) -> Dict[str, List[Candle]]:
        if csv_dir:
            return {symbol: _read_csv_candles(symbol, Path(csv_dir), start, end) for symbol in symbols}
        return {
            symbol: self.store.candles_between(symbol, "1m", start, end)
            for symbol in symbols
        }

    @staticmethod
    def _context(
        symbol: str, one_minute: List[Candle], daily: List[Candle], ts: datetime
    ) -> Dict[str, List[Candle]]:
        daily_context = _daily_context(one_minute, daily, ts)
        if not daily_context:
            daily_context = resample_candles(one_minute, "1d", 60 * 24)
        return {
            "1m": one_minute,
            "5m": resample_candles(one_minute, "5m", 5),
            "10m": resample_candles(one_minute, "10m", 10),
            "15m": resample_candles(one_minute, "15m", 15),
            "30m": resample_candles(one_minute, "30m", 30),
            "1h": resample_candles(one_minute, "1h", 60),
            "1d": daily_context,
        }


def _date_bounds(start_date: str, end_date: str) -> Tuple[datetime, datetime]:
    start = datetime.combine(date.fromisoformat(start_date), time.min)
    end = datetime.combine(date.fromisoformat(end_date), time.max).replace(microsecond=0)
    return start, end


def _evaluation_interval_minutes(alert_timeframes: List[str]) -> int:
    intervals = [
        TIMEFRAME_MINUTES[timeframe]
        for timeframe in alert_timeframes
        if timeframe in TIMEFRAME_MINUTES
    ]
    return min(intervals) if intervals else 15


def _is_completed_replay_close(timestamp: datetime, alert_timeframes: List[str]) -> bool:
    interval = _evaluation_interval_minutes(alert_timeframes)
    if interval <= 1:
        return True
    if timestamp.second or timestamp.microsecond:
        return False
    return timestamp.minute % interval == interval - 1


def _daily_context(
    one_minute: List[Candle], daily: List[Candle], timestamp: datetime
) -> List[Candle]:
    session_date = timestamp.date()
    historical_daily = [candle for candle in daily if candle.timestamp.date() < session_date]
    current_intraday = [
        candle for candle in one_minute if candle.timestamp.date() == session_date
    ]
    if not current_intraday:
        return historical_daily
    return [*historical_daily, _intraday_daily_candle(current_intraday)]


def _intraday_daily_candle(candles: List[Candle]) -> Candle:
    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    first = ordered[0]
    last = ordered[-1]
    return Candle(
        symbol=first.symbol,
        timeframe="1d",
        timestamp=datetime.combine(first.timestamp.date(), time.min),
        open=first.open,
        high=max(candle.high for candle in ordered),
        low=min(candle.low for candle in ordered),
        close=last.close,
        volume=sum(candle.volume for candle in ordered),
        source=first.source,
    )


def _read_csv_candles(
    symbol: str, csv_dir: Path, start: datetime, end: datetime
) -> List[Candle]:
    path = csv_dir / f"{symbol}.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        candles = []
        for row in reader:
            timestamp = _parse_timestamp(row)
            if timestamp is None or timestamp < start or timestamp > end:
                continue
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe="1m",
                    timestamp=timestamp,
                    open=float(_get(row, "open", "Open")),
                    high=float(_get(row, "high", "High")),
                    low=float(_get(row, "low", "Low")),
                    close=float(_get(row, "close", "Close")),
                    volume=float(_get(row, "volume", "Volume", default="0") or 0),
                    source="csv",
                )
            )
    return sorted(candles, key=lambda candle: candle.timestamp)


def _parse_timestamp(row: Dict[str, str]) -> Optional[datetime]:
    raw = _get(row, "timestamp", "datetime", "Datetime", "date", "Date", default="")
    if not raw:
        return None
    value = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def _get(row: Dict[str, str], *names: str, default: Optional[str] = None) -> Optional[str]:
    for name in names:
        if name in row:
            return row[name]
    return default


def _future_candles(candles: Iterable[Candle], timestamp: datetime) -> List[Candle]:
    return [candle for candle in candles if candle.timestamp > timestamp]


def _exclude_setup_types(
    setups: List[SetupSignal], excluded_setup_types: List[str]
) -> List[SetupSignal]:
    excluded = {str(setup_type) for setup_type in excluded_setup_types or []}
    if not excluded:
        return setups
    return [setup for setup in setups if setup.setup_type not in excluded]


def _setup_key(setup: SetupSignal, session_date: date, source_key: Optional[str] = None) -> Tuple:
    return (
        source_key or (setup.features or {}).get(FEATURE_ALERT_SOURCE) or CORE_SIGNAL_SOURCE,
        setup.symbol,
        session_date.isoformat(),
        setup.setup_type,
        setup.direction,
        round(setup.entry_low, 2),
        round(setup.entry_high, 2),
    )


def _event_type(
    setup: SetupSignal,
    outcome: str,
) -> str:
    if setup.status == "alert_ready":
        return "alerted"
    if setup.status == "blocked":
        return "blocked"
    if outcome == "win" and setup.confidence >= 75:
        return "missed"
    return "ignored"


def _outcome_for_setup(setup: SetupSignal, future: List[Candle]) -> Tuple[str, Optional[float]]:
    outcome, r_multiple, _metrics = _outcome_metrics_for_setup(setup, future)
    return outcome, r_multiple


def _outcome_metrics_for_setup(
    setup: SetupSignal, future: List[Candle]
) -> Tuple[str, Optional[float], Dict[str, object]]:
    entry_mid = (setup.entry_low + setup.entry_high) / 2
    risk = abs(entry_mid - setup.stop_loss)
    metrics: Dict[str, object] = {
        "entry_mid": round(entry_mid, 4),
        "risk_per_share": round(risk, 4),
        "triggered": False,
        "triggered_at": None,
        "mfe_r": None,
        "mae_r": None,
        "move_start_success": False,
        "bars_after_trigger": 0,
        "resolution": "invalid_risk",
    }
    if risk <= 0:
        return "invalid_risk", None, metrics
    tactical_exit_price = _tactical_exit_price(setup, entry_mid, risk)
    if tactical_exit_price is not None:
        metrics["tactical_exit_price"] = round(tactical_exit_price, 4)
        metrics["tactical_r_multiple"] = float(
            (setup.features or {}).get("tactical_exit_r_multiple", 1.0)
        )
        metrics["tactical_outcome"] = "not_triggered"
    triggered = False
    max_favorable_r = 0.0
    max_adverse_r = 0.0
    target_r = round(abs(setup.target1 - entry_mid) / risk, 2)
    metrics["target_r"] = target_r
    for candle in future:
        if not triggered and candle.low <= setup.entry_high and candle.high >= setup.entry_low:
            triggered = True
            metrics["triggered"] = True
            metrics["triggered_at"] = candle.timestamp.isoformat()
        if not triggered:
            continue
        metrics["bars_after_trigger"] = int(metrics["bars_after_trigger"]) + 1
        if setup.direction == "LONG":
            max_favorable_r = max(max_favorable_r, (candle.high - entry_mid) / risk)
            max_adverse_r = max(max_adverse_r, (entry_mid - candle.low) / risk)
            stopped = candle.low <= setup.stop_loss
            target_hit = candle.high >= setup.target1
            tactical_hit = (
                tactical_exit_price is not None and candle.high >= tactical_exit_price
            )
        else:
            max_favorable_r = max(max_favorable_r, (entry_mid - candle.low) / risk)
            max_adverse_r = max(max_adverse_r, (candle.high - entry_mid) / risk)
            stopped = candle.high >= setup.stop_loss
            target_hit = candle.low <= setup.target1
            tactical_hit = (
                tactical_exit_price is not None and candle.low <= tactical_exit_price
            )
        metrics["mfe_r"] = round(max_favorable_r, 2)
        metrics["mae_r"] = round(max_adverse_r, 2)
        metrics["move_start_success"] = max_favorable_r >= 1.0
        if stopped:
            if tactical_exit_price is not None and metrics.get("tactical_outcome") != "win":
                metrics["tactical_outcome"] = "loss"
                metrics["tactical_r_multiple"] = -1.0
            metrics["resolution"] = "stop"
            return "loss", -1.0, metrics
        if tactical_hit and metrics.get("tactical_outcome") not in {"win", "loss"}:
            metrics["tactical_outcome"] = "win"
        if target_hit:
            metrics["resolution"] = "target1"
            return "win", target_r, metrics
    if triggered:
        if metrics.get("tactical_outcome") == "not_triggered":
            metrics["tactical_outcome"] = "open"
        metrics["resolution"] = "open"
        return "open", 0.0, metrics
    metrics["resolution"] = "not_triggered"
    return "not_triggered", None, metrics


def _tactical_exit_price(
    setup: SetupSignal, entry_mid: float, risk: float
) -> Optional[float]:
    features = setup.features or {}
    raw_price = features.get("tactical_exit_price")
    if raw_price is not None:
        try:
            return float(raw_price)
        except (TypeError, ValueError):
            return None
    raw_multiple = features.get("tactical_exit_r_multiple")
    if raw_multiple is None:
        return None
    multiple = float(raw_multiple)
    if setup.direction == "SHORT":
        return entry_mid - risk * multiple
    return entry_mid + risk * multiple
