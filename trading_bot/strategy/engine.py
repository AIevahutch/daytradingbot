from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional

from trading_bot.levels.levels import level_map
from trading_bot.models import Candle, Level, SetupSignal, utc_now


def average_volume(candles: List[Candle], lookback: int = 20) -> float:
    sample = candles[-lookback:]
    if not sample:
        return 0.0
    return sum(c.volume for c in sample) / len(sample)


def trend_bias(candles: List[Candle], lookback: int = 12) -> str:
    if len(candles) < 3:
        return "neutral"
    sample = candles[-lookback:]
    first = sample[0].close
    last = sample[-1].close
    move_pct = (last - first) / first * 100
    if move_pct > 0.15:
        return "bullish"
    if move_pct < -0.15:
        return "bearish"
    return "neutral"


def classify_strat_bar(previous: Candle, current: Candle) -> str:
    if current.high > previous.high and current.low < previous.low:
        return "3"
    if current.high <= previous.high and current.low >= previous.low:
        return "1"
    if current.high > previous.high:
        return "2u"
    if current.low < previous.low:
        return "2d"
    return "1"


def _risk_reward(direction: str, entry_mid: float, stop: float, target1: float) -> float:
    risk = abs(entry_mid - stop)
    reward = abs(target1 - entry_mid)
    if risk <= 0:
        return 0.0
    return reward / risk


def _build_signal(
    symbol: str,
    setup_type: str,
    direction: str,
    candle: Candle,
    entry_low: float,
    entry_high: float,
    stop_loss: float,
    invalidation: float,
    reasoning: str,
    avoid_if: str,
    features: Dict,
    timeframe: str = "5m",
) -> SetupSignal:
    entry_mid = (entry_low + entry_high) / 2
    risk = abs(entry_mid - stop_loss)
    target1_multiple = float(features.get("target1_r_multiple", 2.0))
    target2_multiple = float(features.get("target2_r_multiple", 3.0))
    if direction == "LONG":
        target1 = entry_mid + risk * target1_multiple
        target2 = entry_mid + risk * target2_multiple
    else:
        target1 = entry_mid - risk * target1_multiple
        target2 = entry_mid - risk * target2_multiple
    rr = _risk_reward(direction, entry_mid, stop_loss, target1)
    return SetupSignal(
        symbol=symbol,
        setup_type=setup_type,
        direction=direction,
        timeframe=timeframe,
        created_at=utc_now(),
        entry_low=min(entry_low, entry_high),
        entry_high=max(entry_low, entry_high),
        stop_loss=stop_loss,
        target1=target1,
        target2=target2,
        invalidation=invalidation,
        risk_reward=round(rr, 2),
        reasoning=reasoning,
        avoid_if=avoid_if,
        features=features,
    )


class StrategyEngine:
    def detect(
        self,
        symbol: str,
        candles_by_tf: Dict[str, List[Candle]],
        levels: Iterable[Level],
        market_biases: Optional[Dict[str, str]] = None,
        stale_data: bool = False,
    ) -> List[SetupSignal]:
        five = candles_by_tf.get("5m") or candles_by_tf.get("1m") or []
        fifteen = candles_by_tf.get("15m") or []
        hourly = candles_by_tf.get("1h") or []
        daily = candles_by_tf.get("1d") or []
        if len(five) < 3:
            return []

        levels_by_name = level_map(levels)
        market_biases = market_biases or {}
        signals: List[SetupSignal] = []
        last = five[-1]
        previous = five[-2]
        avg_vol = average_volume(five[:-1]) or 1
        volume_confirmed = last.volume >= avg_vol * 1.05
        weak_volume = last.volume < avg_vol * 0.65

        short_bias = trend_bias(five)
        mid_bias = trend_bias(fifteen) if fifteen else short_bias
        hour_bias = trend_bias(hourly) if hourly else mid_bias
        day_bias = trend_bias(daily) if daily else hour_bias
        bullish_alignment = [short_bias, mid_bias, hour_bias].count("bullish") >= 2
        bearish_alignment = [short_bias, mid_bias, hour_bias].count("bearish") >= 2
        conflicting = "bullish" in {short_bias, mid_bias, hour_bias} and "bearish" in {
            short_bias,
            mid_bias,
            hour_bias,
        }
        peer_confirmation = self._peer_confirmation(symbol, market_biases, short_bias)

        common = {
            "volume_confirmed": volume_confirmed,
            "weak_volume": weak_volume,
            "stale_data": stale_data,
            "conflicting_timeframes": conflicting,
            "market_confirmed": peer_confirmation,
            "day_bias": day_bias,
            "hour_bias": hour_bias,
            "fifteen_bias": mid_bias,
            "five_bias": short_bias,
        }

        vwap = levels_by_name.get("vwap")
        if vwap:
            extension_pct = abs(last.close - vwap) / vwap * 100
            if previous.close < vwap <= last.close and last.low <= vwap * 1.002:
                signals.append(
                    _build_signal(
                        symbol,
                        "VWAP reclaim + retest",
                        "LONG",
                        last,
                        entry_low=max(vwap, last.low),
                        entry_high=last.close,
                        stop_loss=min(previous.low, vwap * 0.998),
                        invalidation=vwap,
                        reasoning=(
                            f"{symbol} reclaimed VWAP and held close enough to the retest zone."
                        ),
                        avoid_if=f"{symbol} loses VWAP or rejects back below the reclaim candle.",
                        features={
                            **common,
                            "timeframe_aligned": bullish_alignment,
                            "level_confluence": self._near_any_level(last.close, levels_by_name),
                            "vwap_confirmed": True,
                            "overextended": extension_pct > 1.2,
                            "extension_pct": round(extension_pct, 3),
                        },
                    )
                )
            if previous.close > vwap >= last.close and last.high >= vwap * 0.998:
                signals.append(
                    _build_signal(
                        symbol,
                        "VWAP rejection + retest",
                        "SHORT",
                        last,
                        entry_low=last.close,
                        entry_high=min(vwap, last.high),
                        stop_loss=max(previous.high, vwap * 1.002),
                        invalidation=vwap,
                        reasoning=f"{symbol} rejected VWAP after losing it, showing sellers defended value.",
                        avoid_if=f"{symbol} reclaims VWAP or holds above the rejection candle.",
                        features={
                            **common,
                            "timeframe_aligned": bearish_alignment,
                            "level_confluence": self._near_any_level(last.close, levels_by_name),
                            "vwap_confirmed": True,
                            "overextended": extension_pct > 1.2,
                            "extension_pct": round(extension_pct, 3),
                        },
                    )
                )

        signals.extend(
            self._level_breaks(symbol, five, levels_by_name, common, bullish_alignment, bearish_alignment)
        )
        signals.extend(self._liquidity_sweeps(symbol, last, levels_by_name, common))
        signals.extend(
            self._momentum_continuation(symbol, five, vwap, common, bullish_alignment, bearish_alignment)
        )
        signals.extend(self._strat_continuity(symbol, five, common, bullish_alignment, bearish_alignment))
        return signals

    @staticmethod
    def _peer_confirmation(symbol: str, market_biases: Dict[str, str], local_bias: str) -> bool:
        if local_bias == "neutral":
            return False
        peers = [bias for ticker, bias in market_biases.items() if ticker != symbol]
        if not peers:
            return False
        return peers.count(local_bias) >= 1

    @staticmethod
    def _near_any_level(price: float, levels_by_name: Dict[str, float], pct: float = 0.18) -> bool:
        for name, level in levels_by_name.items():
            if name == "vwap":
                continue
            if abs(price - level) / level * 100 <= pct:
                return True
        return False

    def _level_breaks(
        self,
        symbol: str,
        candles: List[Candle],
        levels_by_name: Dict[str, float],
        common: Dict,
        bullish_alignment: bool,
        bearish_alignment: bool,
    ) -> List[SetupSignal]:
        last = candles[-1]
        previous = candles[-2]
        signals: List[SetupSignal] = []
        for name in ("previous_day_high", "premarket_high", "weekly_high"):
            level = levels_by_name.get(name)
            if level and previous.close <= level < last.close and last.low <= level * 1.002:
                label = name.replace("_", " ")
                signals.append(
                    _build_signal(
                        symbol,
                        f"{label} break + hold",
                        "LONG",
                        last,
                        entry_low=level,
                        entry_high=last.close,
                        stop_loss=min(previous.low, level * 0.998),
                        invalidation=level,
                        reasoning=f"{symbol} broke above {label} and is trying to hold that level as support.",
                        avoid_if=f"{symbol} loses {label} or the breakout candle fails immediately.",
                        features={
                            **common,
                            "timeframe_aligned": bullish_alignment,
                            "level_confluence": True,
                            "vwap_confirmed": last.close > levels_by_name.get("vwap", 0),
                            "overextended": False,
                        },
                    )
                )
        for name in ("previous_day_low", "premarket_low", "weekly_low"):
            level = levels_by_name.get(name)
            if level and previous.close >= level > last.close and last.high >= level * 0.998:
                label = name.replace("_", " ")
                signals.append(
                    _build_signal(
                        symbol,
                        f"{label} breakdown + hold",
                        "SHORT",
                        last,
                        entry_low=last.close,
                        entry_high=level,
                        stop_loss=max(previous.high, level * 1.002),
                        invalidation=level,
                        reasoning=f"{symbol} broke below {label} and sellers are defending the breakdown.",
                        avoid_if=f"{symbol} reclaims {label} or traps sellers back inside range.",
                        features={
                            **common,
                            "timeframe_aligned": bearish_alignment,
                            "level_confluence": True,
                            "vwap_confirmed": last.close < levels_by_name.get("vwap", float("inf")),
                            "overextended": False,
                        },
                    )
                )
        return signals

    @staticmethod
    def _liquidity_sweeps(
        symbol: str, last: Candle, levels_by_name: Dict[str, float], common: Dict
    ) -> List[SetupSignal]:
        signals: List[SetupSignal] = []
        pdl = levels_by_name.get("previous_day_low")
        pdh = levels_by_name.get("previous_day_high")
        if pdl and last.low < pdl < last.close:
            signals.append(
                _build_signal(
                    symbol,
                    "Liquidity sweep reversal",
                    "LONG",
                    last,
                    entry_low=pdl,
                    entry_high=last.close,
                    stop_loss=last.low,
                    invalidation=last.low,
                    reasoning=f"{symbol} swept below prior day low and reclaimed it, suggesting a failed breakdown.",
                    avoid_if=f"{symbol} loses the sweep low or cannot stay back above prior day low.",
                    features={
                        **common,
                        "timeframe_aligned": not common.get("conflicting_timeframes", False),
                        "level_confluence": True,
                        "vwap_confirmed": last.close > levels_by_name.get("vwap", 0),
                        "overextended": False,
                    },
                )
            )
        if pdh and last.high > pdh > last.close:
            signals.append(
                _build_signal(
                    symbol,
                    "Liquidity sweep reversal",
                    "SHORT",
                    last,
                    entry_low=last.close,
                    entry_high=pdh,
                    stop_loss=last.high,
                    invalidation=last.high,
                    reasoning=f"{symbol} swept above prior day high and failed, suggesting trapped breakout buyers.",
                    avoid_if=f"{symbol} reclaims the sweep high or holds back above prior day high.",
                    features={
                        **common,
                        "timeframe_aligned": not common.get("conflicting_timeframes", False),
                        "level_confluence": True,
                        "vwap_confirmed": last.close < levels_by_name.get("vwap", float("inf")),
                        "overextended": False,
                    },
                )
            )
        return signals

    @staticmethod
    def _momentum_continuation(
        symbol: str,
        candles: List[Candle],
        vwap: Optional[float],
        common: Dict,
        bullish_alignment: bool,
        bearish_alignment: bool,
    ) -> List[SetupSignal]:
        if len(candles) < 16:
            return []
        last = candles[-1]
        recent = candles[-4:]
        base = candles[-10:-4]
        closes = [c.close for c in recent]
        lows = [c.low for c in recent]
        highs = [c.high for c in recent]
        avg_range = sum(c.high - c.low for c in candles[-12:]) / min(len(candles[-12:]), 12)
        if avg_range <= 0:
            return []
        if (
            not common.get("volume_confirmed")
            or not common.get("market_confirmed")
            or common.get("weak_volume")
            or common.get("conflicting_timeframes")
            or common.get("stale_data")
        ):
            return []

        base_high = max(c.high for c in base)
        base_low = min(c.low for c in base)
        base_range_pct = (base_high - base_low) / last.close * 100
        last_range = max(last.high - last.low, 0.0001)
        close_position = (last.close - last.low) / last_range
        vwap_extension_pct = abs(last.close - vwap) / vwap * 100 if vwap else 0.0
        if base_range_pct > 0.45 or vwap_extension_pct > 0.8:
            return []

        signals: List[SetupSignal] = []
        if (
            all(current > previous for previous, current in zip(closes, closes[1:]))
            and bullish_alignment
            and (vwap is None or last.close > vwap)
            and last.close > base_high
            and close_position >= 0.6
        ):
            pullback_low = min(lows)
            if last.close - pullback_low > avg_range * 1.6:
                return signals
            signals.append(
                _build_signal(
                    symbol,
                    "Momentum continuation",
                    "LONG",
                    last,
                    entry_low=last.close - avg_range * 0.35,
                    entry_high=last.close,
                    stop_loss=pullback_low,
                    invalidation=pullback_low,
                    reasoning=f"{symbol} is holding higher closes with aligned intraday momentum.",
                    avoid_if=f"{symbol} breaks the recent pullback low or momentum stalls into chop.",
                    features={
                        **common,
                        "timeframe_aligned": True,
                        "level_confluence": False,
                        "vwap_confirmed": vwap is None or last.close > vwap,
                        "overextended": False,
                        "base_range_pct": round(base_range_pct, 3),
                        "vwap_extension_pct": round(vwap_extension_pct, 3),
                    },
                )
            )
        if (
            all(current < previous for previous, current in zip(closes, closes[1:]))
            and bearish_alignment
            and (vwap is None or last.close < vwap)
            and last.close < base_low
            and close_position <= 0.4
        ):
            pullback_high = max(highs)
            if pullback_high - last.close > avg_range * 1.6:
                return signals
            signals.append(
                _build_signal(
                    symbol,
                    "Momentum continuation",
                    "SHORT",
                    last,
                    entry_low=last.close,
                    entry_high=last.close + avg_range * 0.35,
                    stop_loss=pullback_high,
                    invalidation=pullback_high,
                    reasoning=f"{symbol} is holding lower closes with aligned intraday downside momentum.",
                    avoid_if=f"{symbol} breaks the recent pullback high or sellers lose pace.",
                    features={
                        **common,
                        "timeframe_aligned": True,
                        "level_confluence": False,
                        "vwap_confirmed": vwap is None or last.close < vwap,
                        "overextended": False,
                        "base_range_pct": round(base_range_pct, 3),
                        "vwap_extension_pct": round(vwap_extension_pct, 3),
                    },
                )
            )
        return signals

    @staticmethod
    def _strat_continuity(
        symbol: str,
        candles: List[Candle],
        common: Dict,
        bullish_alignment: bool,
        bearish_alignment: bool,
    ) -> List[SetupSignal]:
        if len(candles) < 4:
            return []
        prior2, prior1, last = candles[-3], candles[-2], candles[-1]
        first = classify_strat_bar(prior2, prior1)
        second = classify_strat_bar(prior1, last)
        signals: List[SetupSignal] = []
        if first == "1" and second == "2u" and bullish_alignment:
            signals.append(
                _build_signal(
                    symbol,
                    "Strat 2-1-2 continuation",
                    "LONG",
                    last,
                    entry_low=prior1.high,
                    entry_high=last.close,
                    stop_loss=prior1.low,
                    invalidation=prior1.low,
                    reasoning=f"{symbol} triggered a Strat 2-1-2 up pattern with timeframe support.",
                    avoid_if=f"{symbol} falls back inside the inside bar or loses timeframe continuity.",
                    features={
                        **common,
                        "timeframe_aligned": True,
                        "level_confluence": False,
                        "vwap_confirmed": True,
                        "overextended": False,
                    },
                )
            )
        if first == "1" and second == "2d" and bearish_alignment:
            signals.append(
                _build_signal(
                    symbol,
                    "Strat 2-1-2 continuation",
                    "SHORT",
                    last,
                    entry_low=last.close,
                    entry_high=prior1.low,
                    stop_loss=prior1.high,
                    invalidation=prior1.high,
                    reasoning=f"{symbol} triggered a Strat 2-1-2 down pattern with timeframe support.",
                    avoid_if=f"{symbol} reclaims the inside bar or downside continuity breaks.",
                    features={
                        **common,
                        "timeframe_aligned": True,
                        "level_confluence": False,
                        "vwap_confirmed": True,
                        "overextended": False,
                    },
                )
            )
        return signals
