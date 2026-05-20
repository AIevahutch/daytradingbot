from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from trading_bot.data.market_data import is_stale, resample_candles
from trading_bot.levels.levels import LevelEngine
from trading_bot.models import Candle, SetupSignal
from trading_bot.psychology.no_trade import NoTradeEngine
from trading_bot.scoring.scoring import ConfidenceScorer
from trading_bot.settings import Settings
from trading_bot.storage import SQLiteStore
from trading_bot.strategy.engine import StrategyEngine, trend_bias


class HistoricalReplay:
    def __init__(self, settings: Settings, store: SQLiteStore):
        self.settings = settings
        self.store = store
        self.level_engine = LevelEngine()
        self.strategy = StrategyEngine()
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
        source = f"csv:{csv_dir}" if csv_dir else "sqlite"
        run_id = self.store.begin_paper_run(source, start_date, end_date, symbols)
        one_minute = self._load_one_minute(symbols, start, end, csv_dir)
        daily = {
            symbol: self.store.candles_between(symbol, "1d", start - timedelta(days=30), end)
            for symbol in symbols
        }
        timeline = sorted({c.timestamp for candles in one_minute.values() for c in candles})
        current: Dict[str, List[Candle]] = {symbol: [] for symbol in symbols}
        indexes = {symbol: 0 for symbol in symbols}
        last_event_at: Dict[Tuple, datetime] = {}
        duplicate_minutes = int(self.settings.strategy.get("duplicate_alert_minutes", 90))

        try:
            for ts in timeline:
                for symbol in symbols:
                    candles = one_minute.get(symbol, [])
                    index = indexes[symbol]
                    while index < len(candles) and candles[index].timestamp <= ts:
                        current[symbol].append(candles[index])
                        index += 1
                    indexes[symbol] = index

                if ts.minute % 5 != 4:
                    continue

                contexts = {
                    symbol: self._context(symbol, candles, daily.get(symbol, []), ts)
                    for symbol, candles in current.items()
                    if candles
                }
                market_biases = {
                    symbol: trend_bias(context.get("5m", []))
                    for symbol, context in contexts.items()
                }

                for symbol, context in contexts.items():
                    intraday = context["1m"]
                    five = context["5m"]
                    if len(five) < 20:
                        continue
                    levels = self.level_engine.compute_levels(
                        symbol, intraday, context.get("1d", [])
                    )
                    stale = is_stale(intraday, self.settings.stale_data_minutes, now=ts)
                    no_trade_state = self.no_trade.evaluate(
                        symbol, five, levels, market_biases, stale_data=stale
                    )
                    setups = self.strategy.detect(
                        symbol, context, levels, market_biases, stale_data=stale
                    )
                    for setup in setups:
                        setup.created_at = ts
                        scored = self.scorer.score(setup, no_trade_state)
                        key = _setup_key(scored, ts.date())
                        prior = last_event_at.get(key)
                        if prior and (ts - prior).total_seconds() / 60 < duplicate_minutes:
                            continue
                        outcome, r_multiple = _outcome_for_setup(
                            scored, _future_candles(one_minute[symbol], ts)
                        )
                        event_type = _event_type(scored, outcome)
                        self.store.insert_paper_event(
                            run_id=run_id,
                            event_time=ts,
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
                            notes=scored.features.get("score_breakdown", {}).get(
                                "no_trade_reason", ""
                            ),
                            metadata={
                                "status": scored.status,
                                "market_condition": scored.market_condition,
                                "score_breakdown": scored.features.get("score_breakdown", {}),
                            },
                        )
                        last_event_at[key] = ts

            summary = self.store.paper_summary(run_id)
            self.store.finish_paper_run(run_id, "completed", summary)
            return {"run_id": run_id, **summary}
        except Exception as exc:
            summary = {"error": str(exc), **self.store.paper_summary(run_id)}
            self.store.finish_paper_run(run_id, "failed", summary)
            raise

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
        daily_context = [candle for candle in daily if candle.timestamp.date() <= ts.date()]
        if not daily_context:
            daily_context = resample_candles(one_minute, "1d", 60 * 24)
        return {
            "1m": one_minute,
            "5m": resample_candles(one_minute, "5m", 5),
            "15m": resample_candles(one_minute, "15m", 15),
            "1h": resample_candles(one_minute, "1h", 60),
            "1d": daily_context,
        }


def _date_bounds(start_date: str, end_date: str) -> Tuple[datetime, datetime]:
    start = datetime.combine(date.fromisoformat(start_date), time.min)
    end = datetime.combine(date.fromisoformat(end_date), time.max).replace(microsecond=0)
    return start, end


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


def _setup_key(setup: SetupSignal, session_date: date) -> Tuple:
    return (
        setup.symbol,
        session_date.isoformat(),
        setup.setup_type,
        setup.direction,
        round(setup.entry_low, 2),
        round(setup.entry_high, 2),
    )


def _event_type(setup: SetupSignal, outcome: str) -> str:
    if setup.status == "alert_ready":
        return "alerted"
    if setup.status == "blocked":
        return "avoided"
    if outcome == "win" and setup.confidence >= 75:
        return "missed"
    return "ignored"


def _outcome_for_setup(setup: SetupSignal, future: List[Candle]) -> Tuple[str, Optional[float]]:
    entry_mid = (setup.entry_low + setup.entry_high) / 2
    risk = abs(entry_mid - setup.stop_loss)
    if risk <= 0:
        return "invalid_risk", None
    triggered = False
    for candle in future:
        if not triggered and candle.low <= setup.entry_high and candle.high >= setup.entry_low:
            triggered = True
        if not triggered:
            continue
        if setup.direction == "LONG":
            stopped = candle.low <= setup.stop_loss
            target_hit = candle.high >= setup.target1
        else:
            stopped = candle.high >= setup.stop_loss
            target_hit = candle.low <= setup.target1
        if stopped:
            return "loss", -1.0
        if target_hit:
            return "win", round(abs(setup.target1 - entry_mid) / risk, 2)
    if triggered:
        return "open", 0.0
    return "not_triggered", None
