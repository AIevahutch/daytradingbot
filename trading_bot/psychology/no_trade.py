from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Dict, List

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.9+ includes zoneinfo.
    ZoneInfo = None

from trading_bot.levels.levels import level_map
from trading_bot.models import Candle, Level
from trading_bot.settings import Settings
from trading_bot.strategy.engine import average_volume, trend_bias


class NoTradeEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def evaluate(
        self,
        symbol: str,
        candles: List[Candle],
        levels: List[Level],
        market_biases: Dict[str, str],
        stale_data: bool = False,
    ) -> Dict:
        if stale_data:
            return {
                "is_no_trade": True,
                "market_condition": "low_quality",
                "reason": "stale or missing market data",
                "hard_blocks": ["stale or missing market data"],
            }
        if len(candles) < 20:
            return {
                "is_no_trade": True,
                "market_condition": "low_quality",
                "reason": "not enough intraday structure yet",
                "hard_blocks": ["not enough intraday structure yet"],
            }

        session_block = self._session_quality_block(candles[-1])
        if session_block:
            return session_block

        recent = candles[-12:]
        price = recent[-1].close
        range_pct = (max(c.high for c in recent) - min(c.low for c in recent)) / price * 100
        avg_range_pct = sum((c.high - c.low) / c.close * 100 for c in recent) / len(recent)
        avg_vol = average_volume(candles[:-1]) or 1
        last_vol = candles[-1].volume
        levels_by_name = level_map(levels)
        vwap = levels_by_name.get("vwap")

        if range_pct < float(self.settings.strategy.get("chop_range_pct", 0.35)):
            return {
                "is_no_trade": True,
                "market_condition": "chop",
                "reason": "compressed low-range chop",
                "hard_blocks": ["compressed low-range chop"],
            }
        if last_vol < avg_vol * float(self.settings.strategy.get("low_volume_ratio", 0.65)):
            return {
                "is_no_trade": True,
                "market_condition": "low_volume",
                "reason": "weak relative volume",
                "hard_blocks": ["weak relative volume"],
            }
        if vwap and abs(price - vwap) / vwap * 100 > float(
            self.settings.strategy.get("max_extension_from_vwap_pct", 1.2)
        ):
            return {
                "is_no_trade": True,
                "market_condition": "extended",
                "reason": "price is overextended from VWAP",
                "hard_blocks": ["price is overextended from VWAP"],
            }

        local_bias = trend_bias(candles)
        peers = [bias for ticker, bias in market_biases.items() if ticker != symbol]
        if local_bias != "neutral" and peers and peers.count(local_bias) == 0:
            return {
                "is_no_trade": True,
                "market_condition": "mixed",
                "reason": "SPY/QQQ/IWM confirmation is mixed",
                "hard_blocks": ["SPY/QQQ/IWM confirmation is mixed"],
            }

        condition = "trending" if local_bias in {"bullish", "bearish"} else "balanced"
        if avg_range_pct < 0.08:
            condition = "quiet"
        return {
            "is_no_trade": False,
            "market_condition": condition,
            "reason": "",
            "hard_blocks": [],
        }

    @staticmethod
    def chase_warning(setup) -> str:
        extension = setup.features.get("extension_pct")
        if extension and extension > 0.8:
            return "Price is already extended; wait for the planned entry zone instead of chasing."
        return "Avoid chasing outside the entry zone; let the level confirm first."

    def _session_quality_block(self, candle: Candle) -> Dict:
        regular_start = _parse_time(self.settings.market_hours.get("regular_start", "09:30"))
        regular_end = _parse_time(self.settings.market_hours.get("regular_end", "16:00"))
        clock = _exchange_clock(candle.timestamp, candle.source, self.settings.timezone)
        if not (regular_start <= clock <= regular_end):
            return {}

        minutes_since_open = _minutes_between(regular_start, clock)
        minutes_to_close = _minutes_between(clock, regular_end)
        avoid_open = int(self.settings.strategy.get("avoid_regular_open_minutes", 0))
        avoid_close = int(self.settings.strategy.get("avoid_regular_close_minutes", 0))
        if avoid_open and minutes_since_open < avoid_open:
            reason = "opening range noise; wait for structure to form"
            return {
                "is_no_trade": True,
                "market_condition": "opening_range",
                "reason": reason,
                "hard_blocks": [reason],
            }
        if avoid_close and minutes_to_close <= avoid_close:
            reason = "closing-window noise; avoid late emotional entries"
            return {
                "is_no_trade": True,
                "market_condition": "closing_window",
                "reason": reason,
                "hard_blocks": [reason],
            }
        midday_start_raw = self.settings.strategy.get("avoid_midday_start")
        midday_end_raw = self.settings.strategy.get("avoid_midday_end")
        if midday_start_raw and midday_end_raw:
            midday_start = _parse_time(str(midday_start_raw))
            midday_end = _parse_time(str(midday_end_raw))
            if midday_start <= clock <= midday_end:
                reason = "midday participation lull; avoid lunch-session fakeouts"
                return {
                    "is_no_trade": True,
                    "market_condition": "midday_lull",
                    "reason": reason,
                    "hard_blocks": [reason],
                }
        return {}


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _minutes_between(start: time, end: time) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


def _exchange_clock(timestamp: datetime, source: str, timezone_name: str) -> time:
    if source == "yfinance" and ZoneInfo is not None:
        return timestamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(timezone_name)).time()
    return timestamp.time()
