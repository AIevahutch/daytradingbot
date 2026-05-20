from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time
from typing import Dict, Iterable, List, Optional

from trading_bot.models import Candle, Level


REGULAR_START = time(9, 30)
REGULAR_END = time(16, 0)


def _date_key(candle: Candle) -> str:
    return candle.timestamp.date().isoformat()


def _session_candles(candles: Iterable[Candle], regular_only: bool = True) -> List[Candle]:
    result = []
    for candle in candles:
        t = candle.timestamp.time()
        if not regular_only or (REGULAR_START <= t <= REGULAR_END):
            result.append(candle)
    return result


def compute_vwap(candles: Iterable[Candle]) -> Optional[float]:
    numerator = 0.0
    denominator = 0.0
    for candle in candles:
        typical = (candle.high + candle.low + candle.close) / 3
        volume = max(candle.volume, 0)
        numerator += typical * volume
        denominator += volume
    if denominator <= 0:
        return None
    return numerator / denominator


class LevelEngine:
    def compute_levels(
        self, symbol: str, intraday: List[Candle], daily: List[Candle]
    ) -> List[Level]:
        if not intraday and not daily:
            return []

        latest_date = (
            max((c.timestamp for c in intraday), default=datetime.utcnow()).date().isoformat()
        )
        levels: List[Level] = []

        previous_day = self._previous_regular_day(intraday, latest_date)
        if previous_day:
            levels.extend(
                [
                    Level(symbol, "previous_day_high", max(c.high for c in previous_day), "1d", latest_date),
                    Level(symbol, "previous_day_low", min(c.low for c in previous_day), "1d", latest_date),
                    Level(symbol, "previous_day_close", previous_day[-1].close, "1d", latest_date),
                ]
            )
        elif len(daily) >= 2:
            prior = daily[-2]
            levels.extend(
                [
                    Level(symbol, "previous_day_high", prior.high, "1d", latest_date),
                    Level(symbol, "previous_day_low", prior.low, "1d", latest_date),
                    Level(symbol, "previous_day_close", prior.close, "1d", latest_date),
                ]
            )

        premarket = [
            c
            for c in intraday
            if c.timestamp.date().isoformat() == latest_date and c.timestamp.time() < REGULAR_START
        ]
        if premarket:
            levels.append(Level(symbol, "premarket_high", max(c.high for c in premarket), "session", latest_date))
            levels.append(Level(symbol, "premarket_low", min(c.low for c in premarket), "session", latest_date))

        week_candles = daily[-5:] if len(daily) >= 5 else daily
        if week_candles:
            levels.append(Level(symbol, "weekly_high", max(c.high for c in week_candles), "1w", latest_date))
            levels.append(Level(symbol, "weekly_low", min(c.low for c in week_candles), "1w", latest_date))

        today_regular = [
            c
            for c in _session_candles(intraday)
            if c.timestamp.date().isoformat() == latest_date
        ]
        vwap = compute_vwap(today_regular or intraday)
        if vwap is not None:
            levels.append(Level(symbol, "vwap", vwap, "session", latest_date))

        gap = self._gap_level(symbol, latest_date, today_regular, levels)
        if gap:
            levels.append(gap)

        return levels

    @staticmethod
    def _previous_regular_day(intraday: List[Candle], latest_date: str) -> List[Candle]:
        by_date: Dict[str, List[Candle]] = defaultdict(list)
        for candle in _session_candles(intraday):
            by_date[_date_key(candle)].append(candle)
        prior_dates = sorted(day for day in by_date if day < latest_date)
        if not prior_dates:
            return []
        return sorted(by_date[prior_dates[-1]], key=lambda candle: candle.timestamp)

    @staticmethod
    def _gap_level(
        symbol: str, latest_date: str, today_regular: List[Candle], levels: List[Level]
    ) -> Optional[Level]:
        if not today_regular:
            return None
        previous_close = next((level.price for level in levels if level.name == "previous_day_close"), None)
        if previous_close is None:
            return None
        today_open = today_regular[0].open
        gap_size = today_open - previous_close
        if abs(gap_size) < previous_close * 0.001:
            return None
        return Level(
            symbol=symbol,
            name="gap_fill",
            price=previous_close,
            timeframe="session",
            session_date=latest_date,
            metadata={"gap_direction": "up" if gap_size > 0 else "down", "open": today_open},
        )


def level_map(levels: Iterable[Level]) -> Dict[str, float]:
    mapped: Dict[str, float] = {}
    for level in levels:
        mapped[level.name] = level.price
    return mapped

