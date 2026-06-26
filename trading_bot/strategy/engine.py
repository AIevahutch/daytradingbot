from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional

from trading_bot.data.market_data import completed_candles_for_timeframe
from trading_bot.day_trade_contract import tighten_day_trade_signal
from trading_bot.levels.levels import level_map
from trading_bot.models import Candle, Level, SetupSignal, utc_now


DEFAULT_ALERT_TIMEFRAMES = ["5m", "15m", "30m", "1h"]
FAST_MOMENTUM_TIMEFRAMES = [("1m", 1), ("5m", 5), ("10m", 10)]


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


def fast_intraday_bias(candles_by_tf: Dict[str, List[Candle]], fallback: str) -> str:
    one_minute = candles_by_tf.get("1m") or []
    if len(one_minute) < 25:
        return fallback
    candidate_start = max(20, len(one_minute) - 5)
    for candidate_index in range(candidate_start, len(one_minute)):
        last = one_minute[candidate_index]
        prior = one_minute[candidate_index - 20 : candidate_index]
        recent = one_minute[max(0, candidate_index - 3) : candidate_index + 1]
        if len(prior) < 20 or len(recent) < 4:
            continue
        avg_volume = average_volume(prior) or 1
        avg_range = sum(c.high - c.low for c in prior) / len(prior)
        volume_ratio = last.volume / avg_volume
        range_ratio = candle_range(last) / max(avg_range, 0.0001)
        recent_move_pct = (
            (max(c.high for c in recent) - min(c.low for c in recent))
            / max(last.close, 0.0001)
            * 100
        )
        if volume_ratio < 2.4 or range_ratio < 2.0 or recent_move_pct < 0.35:
            continue
        if last.close > max(c.high for c in prior) and last.close > last.open:
            return "bullish"
        if last.close < min(c.low for c in prior) and last.close < last.open:
            return "bearish"
    return fallback


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


def candle_range(candle: Candle) -> float:
    return max(candle.high - candle.low, 0.0001)


def candle_body_ratio(candle: Candle) -> float:
    return abs(candle.close - candle.open) / candle_range(candle)


def close_position(candle: Candle) -> float:
    return (candle.close - candle.low) / candle_range(candle)


def vwap_cross_count(candles: List[Candle], vwap: float) -> int:
    signs = []
    for candle in candles:
        if candle.close > vwap:
            signs.append(1)
        elif candle.close < vwap:
            signs.append(-1)
        else:
            signs.append(0)
    compact = [sign for sign in signs if sign != 0]
    return sum(1 for left, right in zip(compact, compact[1:]) if left != right)


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
    timeframe: str = "",
) -> SetupSignal:
    features = dict(features)
    entry_mid = (entry_low + entry_high) / 2
    risk = abs(entry_mid - stop_loss)
    target1_multiple = float(features.get("target1_r_multiple", 1.0))
    target2_multiple = float(features.get("target2_r_multiple", 2.0))
    if direction == "LONG":
        target1 = entry_mid + risk * target1_multiple
        target2 = entry_mid + risk * target2_multiple
    else:
        target1 = entry_mid - risk * target1_multiple
        target2 = entry_mid - risk * target2_multiple
    tactical_exit_multiple = features.get("tactical_exit_r_multiple")
    if tactical_exit_multiple is not None and risk > 0:
        tactical_multiple = float(tactical_exit_multiple)
        tactical_exit = (
            entry_mid + risk * tactical_multiple
            if direction == "LONG"
            else entry_mid - risk * tactical_multiple
        )
        features["tactical_exit_price"] = round(tactical_exit, 4)
        features["tactical_exit_action"] = (
            "SELL/PARTIAL" if direction == "LONG" else "COVER/PARTIAL"
        )
    rr = _risk_reward(direction, entry_mid, stop_loss, target1)
    signal = SetupSignal(
        symbol=symbol,
        setup_type=setup_type,
        direction=direction,
        timeframe=timeframe or str(features.get("primary_timeframe", "15m")),
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
    tighten_day_trade_signal(signal)
    return signal


class StrategyEngine:
    def detect(
        self,
        symbol: str,
        candles_by_tf: Dict[str, List[Candle]],
        levels: Iterable[Level],
        market_biases: Optional[Dict[str, str]] = None,
        stale_data: bool = False,
        alert_timeframes: Optional[List[str]] = None,
        excluded_setup_types: Optional[List[str]] = None,
    ) -> List[SetupSignal]:
        level_list = list(levels)
        signals: List[SetupSignal] = []
        excluded = {str(setup_type) for setup_type in excluded_setup_types or []}
        for timeframe in alert_timeframes or DEFAULT_ALERT_TIMEFRAMES:
            if timeframe not in DEFAULT_ALERT_TIMEFRAMES:
                continue
            primary = completed_candles_for_timeframe(candles_by_tf, timeframe)
            signals.extend(
                self._detect_for_timeframe(
                    symbol,
                    timeframe,
                    primary,
                    candles_by_tf,
                    level_list,
                    market_biases,
                    stale_data,
                )
            )
        if excluded:
            signals = [
                signal for signal in signals if signal.setup_type not in excluded
            ]
        signals.extend(
            self._fast_momentum_expansion(
                symbol,
                candles_by_tf,
                level_list,
                market_biases,
                stale_data,
                excluded,
            )
        )
        return signals

    def _detect_for_timeframe(
        self,
        symbol: str,
        timeframe: str,
        primary: List[Candle],
        candles_by_tf: Dict[str, List[Candle]],
        levels: Iterable[Level],
        market_biases: Optional[Dict[str, str]] = None,
        stale_data: bool = False,
    ) -> List[SetupSignal]:
        fifteen = completed_candles_for_timeframe(candles_by_tf, "15m")
        thirty = completed_candles_for_timeframe(candles_by_tf, "30m")
        hourly = completed_candles_for_timeframe(candles_by_tf, "1h")
        daily = candles_by_tf.get("1d") or []
        if len(primary) < 3:
            return []

        levels_by_name = level_map(levels)
        market_biases = market_biases or {}
        signals: List[SetupSignal] = []
        last = primary[-1]
        previous = primary[-2]
        avg_vol = average_volume(primary[:-1]) or 1
        volume_confirmed = last.volume >= avg_vol * 1.05
        weak_volume = last.volume < avg_vol * 0.65

        primary_bias = trend_bias(primary)
        fifteen_bias = trend_bias(fifteen) if fifteen else primary_bias
        thirty_bias = trend_bias(thirty) if thirty else fifteen_bias
        hour_bias = trend_bias(hourly) if hourly else thirty_bias
        day_bias = trend_bias(daily) if daily else hour_bias
        alignment_biases = [fifteen_bias, thirty_bias, hour_bias]
        bullish_alignment = alignment_biases.count("bullish") >= 2
        bearish_alignment = alignment_biases.count("bearish") >= 2
        conflicting = "bullish" in set(alignment_biases) and "bearish" in set(alignment_biases)
        peer_confirmation = self._peer_confirmation(symbol, market_biases, primary_bias)

        common = {
            "volume_confirmed": volume_confirmed,
            "weak_volume": weak_volume,
            "stale_data": stale_data,
            "conflicting_timeframes": conflicting,
            "market_confirmed": peer_confirmation,
            "primary_timeframe": timeframe,
            "signal_timestamp": last.timestamp.isoformat(),
            "signal_source": last.source,
            "peer_biases": dict(market_biases),
            "day_bias": day_bias,
            "hour_bias": hour_bias,
            "thirty_bias": thirty_bias,
            "fifteen_bias": fifteen_bias,
            "primary_bias": primary_bias,
        }

        vwap = levels_by_name.get("vwap")
        if vwap:
            extension_pct = abs(last.close - vwap) / vwap * 100
            vwap_common = {
                "vwap_setup": True,
                "vwap_volume_ratio": round(last.volume / avg_vol, 3) if avg_vol else 0.0,
                "vwap_body_ratio": round(candle_body_ratio(last), 3),
                "vwap_close_position": round(close_position(last), 3),
                "vwap_cross_count": vwap_cross_count(primary[-8:], vwap),
                "vwap_entry_extension_pct": round(extension_pct, 3),
            }
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
                            **vwap_common,
                            "vwap_direction": "LONG",
                            "vwap_favorable_close": close_position(last) >= 0.62,
                            "vwap_body_confirmed": candle_body_ratio(last) >= 0.35,
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
                            **vwap_common,
                            "vwap_direction": "SHORT",
                            "vwap_favorable_close": close_position(last) <= 0.38,
                            "vwap_body_confirmed": candle_body_ratio(last) >= 0.35,
                            "timeframe_aligned": bearish_alignment,
                            "level_confluence": self._near_any_level(last.close, levels_by_name),
                            "vwap_confirmed": True,
                            "overextended": extension_pct > 1.2,
                            "extension_pct": round(extension_pct, 3),
                        },
                    )
                )

        signals.extend(
            self._level_breaks(symbol, primary, levels_by_name, common, bullish_alignment, bearish_alignment)
        )
        signals.extend(self._liquidity_sweeps(symbol, last, levels_by_name, common))
        signals.extend(
            self._momentum_continuation(symbol, primary, vwap, common, bullish_alignment, bearish_alignment)
        )
        signals.extend(self._strat_continuity(symbol, primary, common, bullish_alignment, bearish_alignment))
        return signals

    @staticmethod
    def _peer_confirmation(symbol: str, market_biases: Dict[str, str], local_bias: str) -> bool:
        if local_bias == "neutral":
            return False
        peers = [bias for ticker, bias in market_biases.items() if ticker != symbol]
        if not peers:
            return False
        return peers.count(local_bias) >= 1

    def _fast_momentum_expansion(
        self,
        symbol: str,
        candles_by_tf: Dict[str, List[Candle]],
        levels: Iterable[Level],
        market_biases: Optional[Dict[str, str]],
        stale_data: bool,
        excluded_setup_types: set,
    ) -> List[SetupSignal]:
        if "Fast momentum expansion" in excluded_setup_types:
            return []
        five = completed_candles_for_timeframe(candles_by_tf, "5m")
        fifteen = completed_candles_for_timeframe(candles_by_tf, "15m")
        thirty = completed_candles_for_timeframe(candles_by_tf, "30m")
        hourly = completed_candles_for_timeframe(candles_by_tf, "1h")

        levels_by_name = level_map(levels)
        local_bias = trend_bias(five or completed_candles_for_timeframe(candles_by_tf, "1m"))
        fifteen_bias = trend_bias(fifteen) if fifteen else local_bias
        thirty_bias = trend_bias(thirty) if thirty else fifteen_bias
        hour_bias = trend_bias(hourly) if hourly else thirty_bias
        peers = market_biases or {}
        bullish_market = self._peer_confirmation(symbol, peers, "bullish")
        bearish_market = self._peer_confirmation(symbol, peers, "bearish")
        vwap = levels_by_name.get("vwap")

        if stale_data:
            return []

        signals: List[SetupSignal] = []
        for timeframe, minutes in FAST_MOMENTUM_TIMEFRAMES:
            candles = completed_candles_for_timeframe(candles_by_tf, timeframe)
            if len(candles) < 25:
                continue
            candidate_start = max(20, len(candles) - 5)
            for candidate_index in range(candidate_start, len(candles)):
                last = candles[candidate_index]
                prior = candles[candidate_index - 20 : candidate_index]
                recent = candles[max(0, candidate_index - 3) : candidate_index + 1]
                if len(prior) < 20 or len(recent) < 4:
                    continue
                prior_high = max(c.high for c in prior)
                prior_low = min(c.low for c in prior)
                avg_volume = average_volume(prior) or 1
                avg_range = sum(c.high - c.low for c in prior) / len(prior)
                last_range = candle_range(last)
                volume_ratio = last.volume / avg_volume
                range_ratio = last_range / max(avg_range, 0.0001)
                recent_low = min(c.low for c in recent)
                recent_high = max(c.high for c in recent)
                recent_move_pct = (recent_high - recent_low) / max(last.close, 0.0001) * 100
                if volume_ratio < 2.4 or range_ratio < 2.0 or recent_move_pct < 0.35:
                    continue
                candles_through_signal = candles[: candidate_index + 1]
                stop_window = candles_through_signal[-3:]
                signal_lag_minutes = (len(candles) - candidate_index - 1) * minutes
                common = {
                    "volume_confirmed": True,
                    "weak_volume": False,
                    "stale_data": stale_data,
                    "conflicting_timeframes": False,
                    "primary_timeframe": timeframe,
                    "signal_timestamp": last.timestamp.isoformat(),
                    "signal_source": last.source,
                    "signal_lag_minutes": signal_lag_minutes,
                    "day_bias": hour_bias,
                    "hour_bias": hour_bias,
                    "thirty_bias": thirty_bias,
                    "fifteen_bias": fifteen_bias,
                    "primary_bias": trend_bias(candles),
                    "peer_biases": dict(peers),
                    "fast_momentum_expansion": True,
                    "midday_momentum_exception": True,
                    "volume_expansion_ratio": round(volume_ratio, 2),
                    "range_expansion_ratio": round(range_ratio, 2),
                    "recent_move_pct": round(recent_move_pct, 3),
                    "target1_r_multiple": 1.0,
                    "target2_r_multiple": 2.0,
                    "tactical_management": True,
                    "tactical_exit_r_multiple": 1.0,
                }
                if (
                    last.close > prior_high
                    and close_position(last) >= 0.60
                    and (vwap is None or last.close > vwap)
                    and bullish_market
                ):
                    stop = min(last.low, min(c.low for c in stop_window))
                    signals.append(
                        _build_signal(
                            symbol,
                            "Fast momentum expansion",
                            "LONG",
                            last,
                            entry_low=last.close - last_range * 0.35,
                            entry_high=last.close,
                            stop_loss=stop,
                            invalidation=stop,
                            reasoning=(
                                f"{symbol} broke the recent {timeframe} intraday range on unusual volume "
                                "with SPY/QQQ/IWM confirmation."
                            ),
                            avoid_if=(
                                f"{symbol} falls back inside the prior range or the momentum candle low fails."
                            ),
                            features={
                                **common,
                                "market_confirmed": True,
                                "timeframe_aligned": True,
                                "level_confluence": True,
                                "vwap_confirmed": vwap is None or last.close > vwap,
                                "overextended": False,
                                "breakout_level": round(prior_high, 4),
                            },
                            timeframe=timeframe,
                        )
                    )
                    break
                if (
                    last.close < prior_low
                    and close_position(last) <= 0.40
                    and (vwap is None or last.close < vwap)
                    and bearish_market
                ):
                    stop = max(last.high, max(c.high for c in stop_window))
                    signals.append(
                        _build_signal(
                            symbol,
                            "Fast momentum expansion",
                            "SHORT",
                            last,
                            entry_low=last.close,
                            entry_high=last.close + last_range * 0.35,
                            stop_loss=stop,
                            invalidation=stop,
                            reasoning=(
                                f"{symbol} broke the recent {timeframe} intraday range lower on unusual volume "
                                "with SPY/QQQ/IWM confirmation."
                            ),
                            avoid_if=(
                                f"{symbol} reclaims the prior range or the momentum candle high fails."
                            ),
                            features={
                                **common,
                                "market_confirmed": True,
                                "timeframe_aligned": True,
                                "level_confluence": True,
                                "vwap_confirmed": vwap is None or last.close < vwap,
                                "overextended": False,
                                "breakdown_level": round(prior_low, 4),
                            },
                            timeframe=timeframe,
                        )
                    )
                    break
        return signals

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
                        "tactical_management": True,
                        "tactical_exit_r_multiple": 1.0,
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
                        "tactical_management": True,
                        "tactical_exit_r_multiple": 1.0,
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
