from __future__ import annotations

from statistics import mean, pstdev
from typing import Dict, List, Optional, Tuple

from trading_bot.alert_policy import is_carter_put_telegram_entry_allowed
from trading_bot.data.market_data import completed_candles_for_timeframe
from trading_bot.models import Candle, SetupSignal
from trading_bot.settings import Settings
from trading_bot.signal_sources import (
    CARTER_SIGNAL_SOURCE,
    CARTER_SOURCE_LABEL,
    tag_alert_source,
)
from trading_bot.strategy.engine import trend_bias


class CarterSqueezeEngine:
    """Carter-inspired public squeeze methodology, kept separate from core setups."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def config(self) -> Dict:
        return self.settings.carter_squeeze

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", False))

    def is_alertable(self, setup: SetupSignal) -> bool:
        return is_carter_put_telegram_entry_allowed(
            setup.__dict__,
            alert_threshold=self.settings.alert_threshold,
        )

    def detect(
        self,
        symbol: str,
        context: Dict[str, List[Candle]],
        market_biases: Dict[str, str],
        no_trade_state: Optional[Dict] = None,
    ) -> List[SetupSignal]:
        if not self.enabled:
            return []
        if symbol not in set(self.config.get("symbols") or []):
            return []

        timeframe = str(self.config.get("timeframe", "15m"))
        length = int(self.config.get("length", 20))
        min_squeeze_bars = int(self.config.get("min_squeeze_bars", 5))
        candles = completed_candles_for_timeframe(context, timeframe)
        if len(candles) < length + min_squeeze_bars:
            return []

        bands = _squeeze_states(
            candles,
            length=length,
            bb_stddev=float(self.config.get("bb_stddev", 2.0)),
            keltner_atr_multiple=float(self.config.get("keltner_atr_multiple", 1.5)),
        )
        if not bands:
            return []

        last = candles[-1]
        previous_states = bands[-(min_squeeze_bars + 1) : -1]
        squeeze_duration = _trailing_squeeze_duration(bands[:-1])
        compression_active = (
            len(previous_states) >= min_squeeze_bars
            and all(state["squeeze_on"] for state in previous_states[-min_squeeze_bars:])
        )
        if not compression_active:
            return []

        compression_window = candles[-(min_squeeze_bars + 1) : -1]
        compression_high = max(candle.high for candle in compression_window)
        compression_low = min(candle.low for candle in compression_window)
        atr = float(bands[-1]["atr"])
        momentum, prior_momentum = _momentum(candles, length)
        direction = _release_direction(
            last,
            compression_high,
            compression_low,
            momentum,
            prior_momentum,
            atr,
        )
        if direction is None:
            return []

        volume_ratio = _volume_ratio(candles, length)
        setup = _build_carter_setup(
            symbol=symbol,
            timeframe=timeframe,
            context=context,
            candles=candles,
            direction=direction,
            compression_high=compression_high,
            compression_low=compression_low,
            squeeze_duration=squeeze_duration,
            momentum=momentum,
            prior_momentum=prior_momentum,
            volume_ratio=volume_ratio,
            atr=atr,
            market_biases=market_biases,
            no_trade_state=no_trade_state or {},
            config=self.config,
        )
        return [self._score(setup, no_trade_state or {})]

    def _score(self, setup: SetupSignal, no_trade_state: Dict) -> SetupSignal:
        cfg = self.config
        features = setup.features
        score = int(cfg.get("base_score", 52))
        positives = [{"factor": "base_carter_squeeze_setup", "points": score}]
        penalties = []
        hard_blocks = []

        def add_positive(name: str, points: int) -> None:
            nonlocal score
            score += points
            positives.append({"factor": name, "points": points})

        def add_penalty(name: str, points: int) -> None:
            nonlocal score
            score += points
            penalties.append({"factor": name, "points": points})

        min_squeeze_bars = int(cfg.get("min_squeeze_bars", 5))
        if int(features.get("squeeze_duration") or 0) >= min_squeeze_bars:
            add_positive("squeeze_compression", int(cfg.get("squeeze_points", 8)))
        else:
            hard_blocks.append("squeeze duration is below the minimum compression requirement")

        if features.get("squeeze_release"):
            add_positive("squeeze_release", int(cfg.get("release_points", 8)))
        else:
            hard_blocks.append("squeeze has not released")

        if features.get("momentum_confirmed"):
            add_positive("momentum_expansion", int(cfg.get("momentum_points", 10)))
        else:
            hard_blocks.append("momentum does not confirm the release direction")

        if features.get("volume_confirmed"):
            add_positive("volume_confirmation", int(cfg.get("volume_points", 8)))
        else:
            hard_blocks.append(
                f"volume ratio {float(features.get('volume_ratio') or 0):.2f} is below Carter minimum"
            )
        if cfg.get("strict_alerts", True):
            strict_min_volume = float(cfg.get("strict_min_volume_ratio", cfg.get("min_volume_ratio", 1.1)))
            if not features.get("strict_volume_confirmed"):
                hard_blocks.append(
                    f"volume ratio {float(features.get('volume_ratio') or 0):.2f} is below strict Carter alert minimum {strict_min_volume:.2f}"
                )
            if cfg.get("require_all_index_alignment", True) and not features.get("all_indexes_aligned"):
                hard_blocks.append("SPY/QQQ/IWM are not all aligned with the Carter squeeze direction")
            if cfg.get("require_tactical_1r_path", True) and not features.get("clean_1r_path"):
                hard_blocks.append("Carter squeeze does not have a clean +1R management path")

        if features.get("timeframe_conflict"):
            hard_blocks.append("30m/1h timeframe direction conflicts with the squeeze release")
            add_penalty("timeframe_conflict", int(cfg.get("timeframe_conflict_penalty", -20)))
        elif features.get("timeframe_aligned"):
            add_positive("higher_timeframe_alignment", int(cfg.get("timeframe_points", 8)))
        else:
            add_positive("higher_timeframe_neutral", int(cfg.get("neutral_timeframe_points", 3)))

        if features.get("peer_conflict"):
            add_penalty("peer_market_conflict", int(cfg.get("peer_conflict_penalty", -6)))
        elif features.get("market_confirmed"):
            add_positive("peer_market_confirmation", int(cfg.get("market_points", 4)))

        if setup.risk_reward >= float(cfg.get("min_risk_reward", 1.0)):
            add_positive("clean_2r_path", int(cfg.get("risk_reward_points", 8)))
        else:
            hard_blocks.append(
                f"risk/reward {setup.risk_reward:.2f} is below Carter minimum"
            )

        reason = str(no_trade_state.get("reason") or "").lower()
        market_condition = str(no_trade_state.get("market_condition") or "").lower()
        no_trade_blocks = list(no_trade_state.get("hard_blocks") or [])
        if no_trade_state.get("is_no_trade"):
            if any(token in reason for token in ("stale", "missing")):
                hard_blocks.extend(no_trade_blocks or ["stale or missing market data"])
                add_penalty("stale_data", int(cfg.get("hard_block_penalty", -30)))
            elif market_condition in {"opening_range", "closing_window", "low_volume", "research_blocked"}:
                hard_blocks.extend(no_trade_blocks or [no_trade_state.get("reason", "no-trade filter")])
                add_penalty("no_trade_block", int(cfg.get("hard_block_penalty", -30)))
            elif "chop" in reason or market_condition == "chop":
                if not (
                    features.get("squeeze_release")
                    and features.get("momentum_confirmed")
                    and features.get("volume_confirmed")
                ):
                    hard_blocks.append("unconfirmed chop")
                add_penalty("chop_caution", int(cfg.get("chop_penalty", -8)))
            else:
                add_penalty("no_trade_caution", int(cfg.get("caution_penalty", -8)))

        setup.confidence = max(0, min(100, int(round(score))))
        hard_blocks = list(dict.fromkeys(block for block in hard_blocks if block))
        if hard_blocks and setup.confidence >= self.settings.alert_threshold:
            setup.confidence = self.settings.alert_threshold - 1
        setup.status = (
            "blocked"
            if hard_blocks
            else "alert_ready"
            if setup.confidence >= self.settings.alert_threshold
            else "watch_only"
        )
        features["score_breakdown"] = {
            "threshold": self.settings.alert_threshold,
            "positives": positives,
            "penalties": penalties,
            "hard_blocks": hard_blocks,
            "raw_score": int(round(score)),
            "final_score": setup.confidence,
            "status": setup.status,
            "source_label": CARTER_SOURCE_LABEL,
        }
        return setup


def _build_carter_setup(
    symbol: str,
    timeframe: str,
    context: Dict[str, List[Candle]],
    candles: List[Candle],
    direction: str,
    compression_high: float,
    compression_low: float,
    squeeze_duration: int,
    momentum: float,
    prior_momentum: float,
    volume_ratio: float,
    atr: float,
    market_biases: Dict[str, str],
    no_trade_state: Dict,
    config: Dict,
) -> SetupSignal:
    last = candles[-1]
    entry_buffer = max(min(atr * 0.08, last.close * 0.001), last.close * 0.0002)
    entry_low = last.close - entry_buffer
    entry_high = last.close + entry_buffer
    entry_mid = (entry_low + entry_high) / 2
    stop_buffer = atr * float(config.get("stop_atr_buffer", 0.15))
    if direction == "LONG":
        stop = min(compression_low, last.low) - stop_buffer
        target1 = entry_mid + abs(entry_mid - stop) * float(config.get("target1_r_multiple", 1.0))
        target2 = entry_mid + abs(entry_mid - stop) * float(config.get("target2_r_multiple", 2.0))
    else:
        stop = max(compression_high, last.high) + stop_buffer
        target1 = entry_mid - abs(entry_mid - stop) * float(config.get("target1_r_multiple", 1.0))
        target2 = entry_mid - abs(entry_mid - stop) * float(config.get("target2_r_multiple", 2.0))

    risk = abs(entry_mid - stop)
    risk_reward = abs(target1 - entry_mid) / risk if risk > 0 else 0.0
    tactical_multiple = float(config.get("tactical_exit_r_multiple", 1.0))
    tactical_exit_price = None
    if risk > 0:
        if direction == "LONG":
            tactical_exit_price = entry_mid + risk * tactical_multiple
        else:
            tactical_exit_price = entry_mid - risk * tactical_multiple
    confirmation = _timeframe_confirmation(context, direction, config)
    peer_state = _peer_confirmation(symbol, direction, market_biases)
    all_index_state = _all_index_alignment(direction, market_biases, config)
    market_regime = _market_regime(candles, no_trade_state)
    features = {
        "data_source": last.source,
        "squeeze_state": "released",
        "squeeze_duration": squeeze_duration,
        "squeeze_release": True,
        "compression_high": round(compression_high, 4),
        "compression_low": round(compression_low, 4),
        "momentum": round(momentum, 4),
        "prior_momentum": round(prior_momentum, 4),
        "momentum_direction": "bullish" if direction == "LONG" else "bearish",
        "momentum_confirmed": _momentum_confirms(direction, momentum, prior_momentum),
        "volume_ratio": round(volume_ratio, 2),
        "volume_confirmed": volume_ratio >= float(config.get("min_volume_ratio", 1.1)),
        "strict_volume_confirmed": volume_ratio >= float(
            config.get("strict_min_volume_ratio", config.get("min_volume_ratio", 1.1))
        ),
        "timeframe_aligned": confirmation["aligned"],
        "timeframe_conflict": confirmation["conflict"],
        "confirmation_biases": confirmation["biases"],
        "market_confirmed": peer_state["confirmed"],
        "peer_conflict": peer_state["conflict"],
        "all_indexes_aligned": all_index_state["aligned"],
        "required_index_biases": all_index_state["biases"],
        "peer_biases": market_biases,
        "market_regime": market_regime,
        "market_condition": market_regime,
        "target1_r_multiple": float(config.get("target1_r_multiple", 1.0)),
        "target2_r_multiple": float(config.get("target2_r_multiple", 2.0)),
        "tactical_management": tactical_exit_price is not None,
        "tactical_exit_r_multiple": tactical_multiple,
        "tactical_exit_price": round(tactical_exit_price, 4)
        if tactical_exit_price is not None
        else None,
        "tactical_exit_action": "SELL/PARTIAL" if direction == "LONG" else "COVER/PARTIAL",
        "clean_1r_path": risk > 0 and tactical_exit_price is not None,
    }
    setup = SetupSignal(
        symbol=symbol,
        setup_type="Carter Squeeze",
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
        risk_reward=round(risk_reward, 2),
        reasoning=(
            f"{symbol} released from a {squeeze_duration}-bar squeeze on {timeframe}; "
            f"momentum is {features['momentum_direction']} and volume is {volume_ratio:.2f}x average."
        ),
        avoid_if=(
            f"{symbol} falls back inside {compression_low:.2f}-{compression_high:.2f} "
            f"or violates {stop:.2f}."
        ),
        market_condition=market_regime,
        status="candidate",
        features=features,
    )
    return tag_alert_source(setup, CARTER_SIGNAL_SOURCE, CARTER_SOURCE_LABEL)


def _squeeze_states(
    candles: List[Candle],
    length: int,
    bb_stddev: float,
    keltner_atr_multiple: float,
) -> List[Dict[str, float]]:
    states: List[Dict[str, float]] = []
    for index in range(length - 1, len(candles)):
        window = candles[index - length + 1 : index + 1]
        closes = [candle.close for candle in window]
        average_close = mean(closes)
        stddev = pstdev(closes)
        atr = _atr(candles[: index + 1], length)
        bb_upper = average_close + bb_stddev * stddev
        bb_lower = average_close - bb_stddev * stddev
        kc_upper = average_close + keltner_atr_multiple * atr
        kc_lower = average_close - keltner_atr_multiple * atr
        states.append(
            {
                "squeeze_on": bb_upper < kc_upper and bb_lower > kc_lower,
                "atr": atr,
                "bb_upper": bb_upper,
                "bb_lower": bb_lower,
                "kc_upper": kc_upper,
                "kc_lower": kc_lower,
            }
        )
    return states


def _atr(candles: List[Candle], length: int) -> float:
    sample = candles[-length:]
    ranges = []
    previous_close = candles[-length - 1].close if len(candles) > length else sample[0].close
    for candle in sample:
        true_range = max(
            candle.high - candle.low,
            abs(candle.high - previous_close),
            abs(candle.low - previous_close),
        )
        ranges.append(true_range)
        previous_close = candle.close
    return mean(ranges) if ranges else 0.0


def _trailing_squeeze_duration(states: List[Dict[str, float]]) -> int:
    count = 0
    for state in reversed(states):
        if not state["squeeze_on"]:
            break
        count += 1
    return count


def _momentum(candles: List[Candle], length: int) -> Tuple[float, float]:
    closes = [candle.close for candle in candles]
    current_avg = mean(closes[-length:])
    prior_avg = mean(closes[-length - 1 : -1])
    return closes[-1] - current_avg, closes[-2] - prior_avg


def _release_direction(
    candle: Candle,
    compression_high: float,
    compression_low: float,
    momentum: float,
    prior_momentum: float,
    atr: float,
) -> Optional[str]:
    release_buffer = max(atr * 0.05, candle.close * 0.0001)
    if (
        candle.close > compression_high + release_buffer
        and _momentum_confirms("LONG", momentum, prior_momentum)
    ):
        return "LONG"
    if (
        candle.close < compression_low - release_buffer
        and _momentum_confirms("SHORT", momentum, prior_momentum)
    ):
        return "SHORT"
    return None


def _momentum_confirms(direction: str, momentum: float, prior_momentum: float) -> bool:
    if direction == "LONG":
        return momentum > 0 and momentum > prior_momentum
    return momentum < 0 and momentum < prior_momentum


def _volume_ratio(candles: List[Candle], length: int) -> float:
    prior = candles[-length - 1 : -1]
    if not prior:
        return 0.0
    average = mean(candle.volume for candle in prior)
    if average <= 0:
        return 0.0
    return candles[-1].volume / average


def _timeframe_confirmation(context: Dict[str, List[Candle]], direction: str, config: Dict) -> Dict:
    expected = "bullish" if direction == "LONG" else "bearish"
    opposing = "bearish" if direction == "LONG" else "bullish"
    biases = {}
    for timeframe in config.get("confirmation_timeframes") or ["30m", "1h"]:
        candles = completed_candles_for_timeframe(context, str(timeframe))
        biases[str(timeframe)] = trend_bias(candles)
    return {
        "aligned": any(value == expected for value in biases.values()),
        "conflict": any(value == opposing for value in biases.values()),
        "biases": biases,
    }


def _peer_confirmation(symbol: str, direction: str, market_biases: Dict[str, str]) -> Dict:
    expected = "bullish" if direction == "LONG" else "bearish"
    opposing = "bearish" if direction == "LONG" else "bullish"
    peers = {key: value for key, value in market_biases.items() if key != symbol}
    return {
        "confirmed": any(value == expected for value in peers.values()),
        "conflict": any(value == opposing for value in peers.values()),
    }


def _all_index_alignment(direction: str, market_biases: Dict[str, str], config: Dict) -> Dict:
    expected = "bullish" if direction == "LONG" else "bearish"
    required = [
        str(symbol).upper()
        for symbol in (config.get("required_index_symbols") or ["SPY", "QQQ", "IWM"])
    ]
    biases = {
        symbol: str(market_biases.get(symbol) or "").strip().lower()
        for symbol in required
    }
    return {
        "aligned": bool(required) and all(biases[symbol] == expected for symbol in required),
        "biases": biases,
    }


def _market_regime(candles: List[Candle], no_trade_state: Dict) -> str:
    condition = str(no_trade_state.get("market_condition") or "").lower()
    if "chop" in condition or condition in {"midday_lull", "mixed"}:
        return "chop"
    bias = trend_bias(candles)
    if bias in {"bullish", "bearish"}:
        return "trend"
    return "balanced"
