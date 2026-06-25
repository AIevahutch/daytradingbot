from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from trading_bot.data.market_data import completed_candles_for_timeframe
from trading_bot.models import Candle, Level, SetupSignal
from trading_bot.settings import Settings
from trading_bot.signal_sources import (
    FAILED_AUCTION_TRAP_SIGNAL_SOURCE,
    FAILED_AUCTION_TRAP_SOURCE_LABEL,
    tag_alert_source,
)
from trading_bot.strategy.engine import average_volume, candle_range, close_position


UPPER_TRAP_LEVELS = {"previous_day_high", "premarket_high", "opening_range_high"}
LOWER_TRAP_LEVELS = {"previous_day_low", "premarket_low", "opening_range_low"}


@dataclass(frozen=True)
class TrapLevel:
    name: str
    price: float


class FailedAuctionTrapEngine:
    """Dashboard-only lane for failed auctions at major visible levels."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def config(self) -> Dict:
        return self.settings.failed_auction_trap

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", False))

    def is_paper_trackable(self, setup: SetupSignal) -> bool:
        return setup.status == "alert_ready" and setup.confidence >= self.settings.alert_threshold

    def detect(
        self,
        symbol: str,
        context: Dict[str, List[Candle]],
        levels: Optional[Iterable[Level]] = None,
        market_biases: Optional[Dict[str, str]] = None,
        no_trade_state: Optional[Dict] = None,
    ) -> List[SetupSignal]:
        if not self.enabled:
            return []
        if symbol not in set(self.config.get("symbols") or []):
            return []

        major_levels = _major_levels(context, levels or [], self.config)
        if not major_levels:
            return []

        signals: List[SetupSignal] = []
        for timeframe in self.config.get("timeframes", ["5m", "15m"]):
            candles = completed_candles_for_timeframe(context, str(timeframe))
            if len(candles) < 22:
                continue
            last = candles[-1]
            previous = candles[-2]
            if not _within_time_window(last.timestamp, self.config):
                continue
            prior = candles[-21:-1]
            avg_vol = average_volume(prior) or 1
            avg_range = sum(candle_range(candle) for candle in prior) / len(prior)
            volume_ratio = last.volume / avg_vol if avg_vol else 0.0
            range_ratio = candle_range(last) / max(avg_range, 0.0001)
            participation = (
                volume_ratio >= float(self.config.get("min_volume_ratio", 1.2))
                or range_ratio >= float(self.config.get("min_range_ratio", 1.15))
            )
            for level in major_levels:
                candidate = _trap_candidate(
                    symbol=symbol,
                    timeframe=str(timeframe),
                    level=level,
                    candles=candles,
                    previous=previous,
                    last=last,
                    all_levels=major_levels,
                    volume_ratio=volume_ratio,
                    range_ratio=range_ratio,
                    participation=participation,
                    market_biases=market_biases or {},
                    no_trade_state=no_trade_state or {},
                    config=self.config,
                    threshold=self.settings.alert_threshold,
                )
                if candidate is not None:
                    signals.append(candidate)
        return _dedupe_signals(signals)


def _trap_candidate(
    symbol: str,
    timeframe: str,
    level: TrapLevel,
    candles: List[Candle],
    previous: Candle,
    last: Candle,
    all_levels: List[TrapLevel],
    volume_ratio: float,
    range_ratio: float,
    participation: bool,
    market_biases: Dict[str, str],
    no_trade_state: Dict,
    config: Dict,
    threshold: int,
) -> Optional[SetupSignal]:
    direction = _failed_direction(level, previous, last, config)
    if direction is None:
        return None

    trap_extreme = min(previous.low, last.low) if direction == "LONG" else max(previous.high, last.high)
    setup = _build_setup(
        symbol=symbol,
        timeframe=timeframe,
        level=level,
        direction=direction,
        last=last,
        trap_extreme=trap_extreme,
        all_levels=all_levels,
        config=config,
    )
    return _score_setup(
        setup=setup,
        level=level,
        candles=candles,
        previous=previous,
        last=last,
        volume_ratio=volume_ratio,
        range_ratio=range_ratio,
        participation=participation,
        market_biases=market_biases,
        no_trade_state=no_trade_state,
        config=config,
        threshold=threshold,
    )


def _dedupe_signals(signals: List[SetupSignal]) -> List[SetupSignal]:
    chosen: Dict[tuple, SetupSignal] = {}
    for signal in signals:
        key = (signal.symbol, signal.timeframe, signal.direction, signal.created_at)
        current = chosen.get(key)
        if current is None or _signal_rank(signal) > _signal_rank(current):
            chosen[key] = signal
    return list(chosen.values())


def _signal_rank(signal: SetupSignal) -> tuple:
    status_rank = {"alert_ready": 2, "watch_only": 1, "blocked": 0}.get(signal.status, 0)
    priority = {
        "premarket_high": 3,
        "premarket_low": 3,
        "previous_day_high": 2,
        "previous_day_low": 2,
        "opening_range_high": 1,
        "opening_range_low": 1,
    }.get(str((signal.features or {}).get("trap_level_name")), 0)
    return (status_rank, int(signal.confidence or 0), priority)


def _failed_direction(
    level: TrapLevel, previous: Candle, last: Candle, config: Dict
) -> Optional[str]:
    min_break_pct = float(config.get("min_break_pct", 0.015))
    if level.name in LOWER_TRAP_LEVELS:
        break_pct = (level.price - previous.close) / level.price * 100
        if (
            previous.close < level.price
            and last.close > level.price
            and min(previous.low, last.low) < level.price
            and break_pct >= min_break_pct
        ):
            return "LONG"
    if level.name in UPPER_TRAP_LEVELS:
        break_pct = (previous.close - level.price) / level.price * 100
        if (
            previous.close > level.price
            and last.close < level.price
            and max(previous.high, last.high) > level.price
            and break_pct >= min_break_pct
        ):
            return "SHORT"
    return None


def _build_setup(
    symbol: str,
    timeframe: str,
    level: TrapLevel,
    direction: str,
    last: Candle,
    trap_extreme: float,
    all_levels: List[TrapLevel],
    config: Dict,
) -> SetupSignal:
    entry_buffer = last.close * float(config.get("entry_buffer_pct", 0.015)) / 100
    stop_buffer = last.close * float(config.get("stop_buffer_pct", 0.02)) / 100
    entry_low = last.close - entry_buffer
    entry_high = last.close + entry_buffer
    entry_mid = (entry_low + entry_high) / 2
    if direction == "LONG":
        stop = trap_extreme - stop_buffer
        risk = abs(entry_mid - stop)
        target1 = entry_mid + risk * float(config.get("target1_r_multiple", 1.0))
        target2 = entry_mid + risk * float(config.get("target2_r_multiple", 2.0))
    else:
        stop = trap_extreme + stop_buffer
        risk = abs(entry_mid - stop)
        target1 = entry_mid - risk * float(config.get("target1_r_multiple", 1.0))
        target2 = entry_mid - risk * float(config.get("target2_r_multiple", 2.0))

    opposing_level = _next_opposing_level(direction, entry_mid, all_levels)
    clean_1r_path = (
        opposing_level is None
        or (direction == "LONG" and target1 < opposing_level.price)
        or (direction == "SHORT" and target1 > opposing_level.price)
    )
    features = {
        "failed_auction_trap": True,
        "trap_level_name": level.name,
        "trap_level_price": round(level.price, 4),
        "trap_extreme": round(trap_extreme, 4),
        "opposing_level_name": opposing_level.name if opposing_level else None,
        "opposing_level_price": round(opposing_level.price, 4) if opposing_level else None,
        "clean_1r_path": clean_1r_path,
        "target1_r_multiple": float(config.get("target1_r_multiple", 1.0)),
        "target2_r_multiple": float(config.get("target2_r_multiple", 2.0)),
        "tactical_management": True,
        "tactical_exit_r_multiple": 1.0,
    }
    setup = SetupSignal(
        symbol=symbol,
        setup_type="Failed Auction Trap",
        direction=direction,
        timeframe=timeframe,
        created_at=last.timestamp,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop,
        target1=target1,
        target2=target2,
        invalidation=stop,
        confidence=0,
        risk_reward=1.0 if risk > 0 else 0.0,
        reasoning=(
            f"{symbol} broke {level.name.replace('_', ' ')} and closed back inside, "
            "creating a trapped-side reversal candidate."
        ),
        avoid_if=f"{symbol} violates the trap extreme near {trap_extreme:.2f}.",
        market_condition="unknown",
        status="candidate",
        features=features,
    )
    return tag_alert_source(
        setup,
        FAILED_AUCTION_TRAP_SIGNAL_SOURCE,
        FAILED_AUCTION_TRAP_SOURCE_LABEL,
    )


def _score_setup(
    setup: SetupSignal,
    level: TrapLevel,
    candles: List[Candle],
    previous: Candle,
    last: Candle,
    volume_ratio: float,
    range_ratio: float,
    participation: bool,
    market_biases: Dict[str, str],
    no_trade_state: Dict,
    config: Dict,
    threshold: int,
) -> SetupSignal:
    score = int(config.get("base_score", 58))
    positives = [{"factor": "base_failed_auction_trap", "points": score}]
    hard_blocks: List[str] = []
    penalties: List[Dict] = []

    def add_positive(name: str, points: int) -> None:
        nonlocal score
        score += points
        positives.append({"factor": name, "points": points})

    add_positive("major_visible_level", int(config.get("major_level_points", 6)))
    add_positive("closed_back_inside_level", int(config.get("close_back_inside_points", 10)))

    if participation:
        add_positive("participation_confirmation", int(config.get("participation_points", 8)))
    else:
        hard_blocks.append("reclaim/rejection lacks relative volume or range expansion")

    if _index_agreement(setup.direction, market_biases, config):
        add_positive("spy_qqq_directional_agreement", int(config.get("index_agreement_points", 8)))
    else:
        hard_blocks.append("SPY and QQQ do not agree with the trap direction")

    if setup.features.get("clean_1r_path"):
        add_positive("clean_1r_path_before_opposing_level", int(config.get("clean_1r_path_points", 8)))
    else:
        hard_blocks.append("next major opposing level blocks the +1R path")

    market_condition = str(
        no_trade_state.get("market_condition")
        or no_trade_state.get("regime")
        or "unknown"
    ).lower()
    clean_range_exception = _clean_range_edge_exception(
        setup, level, previous, last, participation, config
    )
    if market_condition in {"balanced", "mixed", "chop"}:
        if clean_range_exception:
            add_positive("clean_balanced_range_edge_trap", int(config.get("balanced_exception_points", 4)))
        else:
            hard_blocks.append("balanced/mixed regime without an extremely clean range-edge trap")
    elif no_trade_state.get("is_no_trade") and "stale" in str(no_trade_state.get("reason", "")).lower():
        hard_blocks.append("stale or missing market data")

    setup.market_condition = market_condition
    setup.confidence = max(0, min(100, int(round(score))))
    if hard_blocks and setup.confidence >= threshold:
        setup.confidence = threshold - 1
    setup.status = "alert_ready" if not hard_blocks and setup.confidence >= threshold else "watch_only"
    setup.features.update(
        {
            "volume_ratio": round(volume_ratio, 2),
            "range_ratio": round(range_ratio, 2),
            "participation_confirmed": participation,
            "close_position": round(close_position(last), 3),
            "previous_close": round(previous.close, 4),
            "signal_timestamp": last.timestamp.isoformat(),
            "market_condition": market_condition,
            "market_regime": market_condition,
            "peer_biases": dict(market_biases),
            "score_breakdown": {
                "threshold": threshold,
                "positives": positives,
                "penalties": penalties,
                "hard_blocks": hard_blocks,
                "raw_score": int(round(score)),
                "final_score": setup.confidence,
                "status": setup.status,
                "source_label": FAILED_AUCTION_TRAP_SOURCE_LABEL,
            },
        }
    )
    return setup


def _clean_range_edge_exception(
    setup: SetupSignal,
    level: TrapLevel,
    previous: Candle,
    last: Candle,
    participation: bool,
    config: Dict,
) -> bool:
    if not participation:
        return False
    min_break_pct = float(config.get("min_break_pct", 0.015)) * 1.5
    if setup.direction == "LONG":
        break_pct = (level.price - previous.close) / level.price * 100
        favorable_close = close_position(last) >= 0.55
    else:
        break_pct = (previous.close - level.price) / level.price * 100
        favorable_close = close_position(last) <= 0.45
    return break_pct >= min_break_pct and favorable_close


def _index_agreement(direction: str, market_biases: Dict[str, str], config: Dict) -> bool:
    required = [str(symbol) for symbol in config.get("required_index_symbols", ["SPY", "QQQ"])]
    target = "bullish" if direction == "LONG" else "bearish"
    if not required:
        return True
    return all(str(market_biases.get(symbol) or "").lower() == target for symbol in required)


def _next_opposing_level(
    direction: str, entry_mid: float, levels: List[TrapLevel]
) -> Optional[TrapLevel]:
    if direction == "LONG":
        above = [level for level in levels if level.price > entry_mid]
        return min(above, key=lambda level: level.price) if above else None
    below = [level for level in levels if level.price < entry_mid]
    return max(below, key=lambda level: level.price) if below else None


def _major_levels(
    context: Dict[str, List[Candle]], levels: Iterable[Level], config: Dict
) -> List[TrapLevel]:
    one_minute = sorted(context.get("1m") or [], key=lambda candle: candle.timestamp)
    latest = one_minute[-1] if one_minute else _latest_context_candle(context)
    if latest is None:
        return []
    latest_date = _local_dt(latest.timestamp, config).date()
    computed: Dict[str, float] = {}

    current_day = [
        candle for candle in one_minute if _local_dt(candle.timestamp, config).date() == latest_date
    ]
    regular_by_date: Dict[object, List[Candle]] = {}
    for candle in one_minute:
        local = _local_dt(candle.timestamp, config)
        if time(9, 30) <= local.time() <= time(16, 0):
            regular_by_date.setdefault(local.date(), []).append(candle)
    prior_dates = sorted(day for day in regular_by_date if day < latest_date)
    if prior_dates:
        previous_regular = regular_by_date[prior_dates[-1]]
        computed["previous_day_high"] = max(candle.high for candle in previous_regular)
        computed["previous_day_low"] = min(candle.low for candle in previous_regular)
    else:
        daily = sorted(context.get("1d") or [], key=lambda candle: candle.timestamp)
        if len(daily) >= 2:
            computed["previous_day_high"] = daily[-2].high
            computed["previous_day_low"] = daily[-2].low

    premarket = [
        candle
        for candle in current_day
        if time(4, 0) <= _local_dt(candle.timestamp, config).time() < time(9, 30)
    ]
    if premarket:
        computed["premarket_high"] = max(candle.high for candle in premarket)
        computed["premarket_low"] = min(candle.low for candle in premarket)

    opening_minutes = int(config.get("opening_range_minutes", 15))
    opening_end = (
        datetime.combine(latest_date, time(9, 30)) + timedelta(minutes=opening_minutes)
    ).time()
    latest_local_time = _local_dt(latest.timestamp, config).time()
    if latest_local_time >= opening_end:
        opening = [
            candle
            for candle in current_day
            if time(9, 30) <= _local_dt(candle.timestamp, config).time() < opening_end
        ]
        if opening:
            computed["opening_range_high"] = max(candle.high for candle in opening)
            computed["opening_range_low"] = min(candle.low for candle in opening)

    for level in levels:
        if level.name in UPPER_TRAP_LEVELS or level.name in LOWER_TRAP_LEVELS:
            computed.setdefault(level.name, level.price)

    return [
        TrapLevel(name=name, price=price)
        for name, price in computed.items()
        if price and price > 0
    ]


def _latest_context_candle(context: Dict[str, List[Candle]]) -> Optional[Candle]:
    latest: Optional[Candle] = None
    for candles in context.values():
        for candle in candles:
            if latest is None or candle.timestamp > latest.timestamp:
                latest = candle
    return latest


def _within_time_window(timestamp: datetime, config: Dict) -> bool:
    local_time = _local_dt(timestamp, config).time()
    start = _parse_time(str(config.get("start_time", "09:35")))
    end = _parse_time(str(config.get("end_time", "12:30")))
    return start <= local_time <= end


def _local_dt(timestamp: datetime, config: Dict) -> datetime:
    zone = ZoneInfo(str(config.get("session_timezone") or "America/New_York"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo("UTC"))
    return timestamp.astimezone(zone)


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))
