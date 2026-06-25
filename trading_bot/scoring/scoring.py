from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from trading_bot.models import SetupSignal
from trading_bot.settings import Settings

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.9+ includes zoneinfo.
    ZoneInfo = None


class ConfidenceScorer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def score(self, setup: SetupSignal, no_trade: Dict = None) -> SetupSignal:
        weights = self.settings.scoring_weights
        features = setup.features or {}
        score = int(weights.get("base_setup", 58))
        positives = [{"factor": "base_setup", "points": score}]
        penalties = []
        hard_blocks = []
        min_risk_reward = float(self.settings.strategy.get("min_risk_reward", 1.5))
        if (setup.features or {}).get("fast_momentum_expansion"):
            min_risk_reward = float(
                self.settings.strategy.get("fast_momentum_min_risk_reward", 1.0)
            )

        def add_positive(name: str, points: int) -> None:
            nonlocal score
            score += points
            positives.append({"factor": name, "points": points})

        def add_penalty(name: str, points: int) -> None:
            nonlocal score
            score += points
            penalties.append({"factor": name, "points": points})

        if features.get("timeframe_aligned"):
            add_positive("timeframe_continuity", int(weights.get("timeframe_continuity", 8)))
        if features.get("level_confluence"):
            add_positive("level_confluence", int(weights.get("level_confluence", 7)))
        if features.get("vwap_confirmed"):
            add_positive("vwap_confirmation", int(weights.get("vwap_confirmation", 7)))
        if features.get("volume_confirmed"):
            add_positive("volume_confirmation", int(weights.get("volume_confirmation", 6)))
        if features.get("market_confirmed"):
            add_positive("market_confirmation", int(weights.get("market_confirmation", 6)))
        if setup.risk_reward >= min_risk_reward:
            add_positive("clean_risk_reward", int(weights.get("clean_risk_reward", 8)))
        else:
            hard_blocks.append(
                f"risk/reward {setup.risk_reward:.2f} is below minimum {min_risk_reward:.2f}"
            )

        market_condition = str(
            (no_trade or {}).get("market_condition") or setup.market_condition or ""
        ).lower()
        if (
            market_condition == "balanced"
            and features.get("level_confluence")
            and features.get("vwap_confirmed")
            and features.get("volume_confirmed")
            and setup.risk_reward >= min_risk_reward
        ):
            add_positive(
                "balanced_quality_bonus",
                int(weights.get("balanced_quality_bonus", 4)),
            )

        if features.get("weak_volume"):
            add_penalty("weak_volume", int(weights.get("weak_volume_penalty", -12)))
            hard_blocks.append("weak relative volume")
        if features.get("conflicting_timeframes"):
            add_penalty(
                "conflicting_timeframes",
                int(weights.get("conflicting_timeframes_penalty", -12)),
            )
            hard_blocks.append("conflicting timeframe setup")
        if features.get("overextended"):
            add_penalty("overextension", int(weights.get("overextension_penalty", -10)))
            hard_blocks.append("price is overextended from VWAP")
        if features.get("stale_data"):
            add_penalty("stale_data", int(weights.get("stale_data_penalty", -30)))
            hard_blocks.append("stale or missing market data")
        all_index_trend_override = _all_index_trend_continuation_override_allowed(
            setup, features, self.settings
        )
        if setup.setup_type == "Momentum continuation":
            if all_index_trend_override:
                add_positive("all_index_trend_continuation", 0)
            else:
                add_penalty(
                    "momentum_continuation_validation",
                    int(weights.get("momentum_continuation_penalty", -14)),
                )
        if setup.setup_type.startswith("Strat "):
            if all_index_trend_override:
                add_positive("all_index_trend_continuation", 0)
            else:
                add_penalty(
                    "strat_continuation_validation",
                    int(weights.get("strat_continuation_penalty", -12)),
                )
        if features.get("fast_momentum_expansion"):
            add_positive(
                "fast_momentum_expansion",
                int(weights.get("fast_momentum_expansion_bonus", 6)),
            )
        fast_momentum_risk_override = _fast_momentum_risk_override_allowed(
            features, self.settings
        )
        risk_override_allowed = fast_momentum_risk_override or all_index_trend_override
        if features.get("vwap_setup") or setup.setup_type in {
            "VWAP reclaim + retest",
            "VWAP rejection + retest",
        }:
            self._apply_vwap_quality_gate(
                setup,
                features,
                add_penalty,
                hard_blocks,
            )
        self._apply_spy_vwap_reclaim_review_gate(
            setup,
            features,
            add_penalty,
            hard_blocks,
        )
        self._apply_strict_index_alignment_gate(
            setup,
            features,
            add_penalty,
            hard_blocks,
        )
        self._apply_level_break_quality_gate(
            setup,
            features,
            market_condition,
            add_penalty,
            hard_blocks,
        )

        no_trade = no_trade or {}
        research = no_trade.get("research") or {}
        if research.get("enabled"):
            if research.get("hard_block"):
                if risk_override_allowed:
                    positives.append(
                        {
                            "factor": (
                                "fast_momentum_risk_override"
                                if fast_momentum_risk_override
                                else "all_index_trend_risk_override"
                            ),
                            "points": 0,
                        }
                    )
                    setup.features["risk_override"] = (
                        "fast_momentum_expansion"
                        if fast_momentum_risk_override
                        else "all_index_trend_continuation"
                    )
                    setup.features["overridden_research_reason"] = research.get(
                        "reason", "research hard block"
                    )
                else:
                    add_penalty(
                        "research_gate",
                        int(research.get("penalty") or weights.get("research_hard_block_penalty", -30)),
                    )
                    hard_blocks.extend(research.get("hard_blocks") or [research.get("reason", "research hard block")])
            else:
                penalty = int(research.get("penalty") or 0)
                if penalty:
                    add_penalty("research_caution", penalty)
                bias = str(research.get("bias") or "neutral").lower()
                direction = str(setup.direction or "").upper()
                contra_bias = (bias == "bearish" and direction == "LONG") or (
                    bias == "bullish" and direction == "SHORT"
                )
                if contra_bias:
                    add_penalty(
                        "research_bias_conflict",
                        int(weights.get("research_bias_conflict_penalty", -6)),
                    )

        if no_trade.get("is_no_trade"):
            reason = no_trade.get("reason", "").lower()
            if risk_override_allowed:
                if features.get("midday_momentum_exception"):
                    add_positive(
                        "midday_momentum_exception",
                        int(weights.get("midday_momentum_exception_bonus", 4)),
                    )
                no_trade = {
                    **no_trade,
                    "is_no_trade": False,
                    "market_condition": "trending",
                    "reason": "",
                    "hard_blocks": [],
                }
            elif _fast_momentum_exception(features, reason, self.settings):
                add_positive(
                    "midday_momentum_exception",
                    int(weights.get("midday_momentum_exception_bonus", 4)),
                )
                no_trade = {
                    **no_trade,
                    "is_no_trade": False,
                    "market_condition": "trending",
                    "reason": "",
                    "hard_blocks": [],
                }
            elif "chop" in reason:
                add_penalty("chop", int(weights.get("chop_penalty", -18)))
            elif "stale" in reason:
                add_penalty("stale_data", int(weights.get("stale_data_penalty", -30)))
            else:
                add_penalty("no_trade_filter", -10)
            hard_blocks.extend(no_trade.get("hard_blocks") or [no_trade.get("reason", "no-trade filter")])

        if setup.risk_reward < 1:
            add_penalty("poor_risk_reward", -18)

        setup.confidence = max(0, min(100, int(round(score))))
        setup.market_condition = no_trade.get("market_condition", setup.market_condition)
        hard_blocks = list(dict.fromkeys(block for block in hard_blocks if block))
        if hard_blocks and setup.confidence >= self.settings.alert_threshold:
            setup.confidence = self.settings.alert_threshold - 1
        if hard_blocks:
            setup.status = "blocked"
        else:
            setup.status = (
                "alert_ready"
                if setup.confidence >= self.settings.alert_threshold
                else "watch_only"
            )
        setup.features["score_breakdown"] = {
            "threshold": self.settings.alert_threshold,
            "no_trade_reason": no_trade.get("reason", ""),
            "research": research,
            "positives": positives,
            "penalties": penalties,
            "hard_blocks": hard_blocks,
            "raw_score": int(round(score)),
            "final_score": setup.confidence,
            "status": setup.status,
        }
        return setup

    def is_alertable(self, setup: SetupSignal) -> bool:
        return setup.status == "alert_ready" and setup.confidence >= self.settings.alert_threshold

    def _apply_strict_index_alignment_gate(
        self,
        setup: SetupSignal,
        features: Dict,
        add_penalty,
        hard_blocks: list,
    ) -> None:
        strategy = self.settings.strategy
        if not strategy.get("strict_index_alignment_for_alerts", True):
            return
        peer_biases = features.get("peer_biases") or {}
        if not peer_biases:
            return
        required_symbols = strategy.get("strict_index_alignment_symbols") or ["SPY", "QQQ"]
        if isinstance(required_symbols, str):
            required_symbols = [
                symbol.strip()
                for symbol in required_symbols.split(",")
                if symbol.strip()
            ]
        expected_bias = "bullish" if str(setup.direction).upper() == "LONG" else "bearish"
        missing_or_misaligned = [
            symbol
            for symbol in required_symbols
            if str(peer_biases.get(symbol, "")).lower() != expected_bias
        ]
        if not missing_or_misaligned:
            return
        add_penalty(
            "strict_index_alignment",
            int(self.settings.scoring_weights.get("strict_index_alignment_penalty", -30)),
        )
        formatted = ", ".join(
            f"{symbol}={str(peer_biases.get(symbol, 'missing')).upper()}"
            for symbol in required_symbols
        )
        hard_blocks.append(
            f"strict index alignment failed for {setup.direction}: {formatted}"
        )

    def _apply_level_break_quality_gate(
        self,
        setup: SetupSignal,
        features: Dict,
        market_condition: str,
        add_penalty,
        hard_blocks: list,
    ) -> None:
        strategy = self.settings.strategy
        if not strategy.get("block_standalone_level_breaks", True):
            return
        setup_name = str(setup.setup_type)
        is_level_break = setup_name.endswith("break + hold") or setup_name.endswith(
            "breakdown + hold"
        )
        if not is_level_break:
            return
        required_condition = str(
            strategy.get("level_break_required_market_condition", "trending")
        ).lower()
        expected_bias = "bullish" if str(setup.direction).upper() == "LONG" else "bearish"
        required_symbols = strategy.get("level_break_required_index_symbols") or [
            "SPY",
            "QQQ",
            "IWM",
        ]
        if isinstance(required_symbols, str):
            required_symbols = [
                symbol.strip()
                for symbol in required_symbols.split(",")
                if symbol.strip()
            ]
        peer_biases = features.get("peer_biases") or {}
        failures = []
        if market_condition != required_condition:
            failures.append(
                f"break-and-hold requires {required_condition} market, got {market_condition or 'unknown'}"
            )
        if not features.get("timeframe_aligned"):
            failures.append("break-and-hold lacks timeframe alignment")
        if not features.get("volume_confirmed"):
            failures.append("break-and-hold lacks volume confirmation")
        if not features.get("vwap_confirmed"):
            failures.append("break-and-hold lacks VWAP support")
        if not features.get("market_confirmed"):
            failures.append("break-and-hold lacks peer market confirmation")
        misaligned = [
            symbol
            for symbol in required_symbols
            if str(peer_biases.get(symbol, "")).lower() != expected_bias
        ]
        if misaligned:
            formatted = ", ".join(
                f"{symbol}={str(peer_biases.get(symbol, 'missing')).upper()}"
                for symbol in required_symbols
            )
            failures.append(
                f"break-and-hold requires all-index {setup.direction} alignment: {formatted}"
            )
        if not failures:
            setup.features["level_break_confirmation"] = "all_index_trending_continuation"
            return
        add_penalty(
            "standalone_level_break",
            int(self.settings.scoring_weights.get("standalone_level_break_penalty", -35)),
        )
        hard_blocks.extend(failures)

    def _apply_vwap_quality_gate(
        self,
        setup: SetupSignal,
        features: Dict,
        add_penalty,
        hard_blocks: list,
    ) -> None:
        strategy = self.settings.strategy
        weights = self.settings.scoring_weights
        quality_penalty = int(weights.get("vwap_quality_penalty", -20))
        whipsaw_penalty = int(weights.get("vwap_whipsaw_penalty", -18))
        opening_penalty = int(weights.get("vwap_opening_noise_penalty", -10))
        min_volume_ratio = float(strategy.get("vwap_min_volume_ratio", 1.2))
        max_entry_extension = float(strategy.get("vwap_max_entry_extension_pct", 0.45))
        max_crosses = int(strategy.get("vwap_max_crosses_lookback", 2))
        opening_noise_minutes = int(strategy.get("vwap_opening_noise_minutes", 90))

        volume_ratio = float(features.get("vwap_volume_ratio") or 0)
        entry_extension = float(features.get("vwap_entry_extension_pct") or 0)
        cross_count = int(features.get("vwap_cross_count") or 0)
        minutes_since_open = _minutes_since_regular_open(setup, features, self.settings)

        quality_failures = []
        if not features.get("timeframe_aligned"):
            quality_failures.append("VWAP retest is not aligned across 15m/30m/1h")
        if not features.get("market_confirmed"):
            quality_failures.append("VWAP retest lacks SPY/QQQ/IWM peer confirmation")
        if not features.get("vwap_favorable_close"):
            quality_failures.append("VWAP candle did not close in the favorable part of its range")
        if not features.get("vwap_body_confirmed"):
            quality_failures.append("VWAP candle body is too small for a clean directional start")
        if volume_ratio < min_volume_ratio:
            quality_failures.append(
                f"VWAP volume ratio {volume_ratio:.2f} is below {min_volume_ratio:.2f}"
            )
        if entry_extension > max_entry_extension:
            quality_failures.append(
                f"VWAP entry extension {entry_extension:.2f}% is above {max_entry_extension:.2f}%"
            )
        if (
            minutes_since_open is not None
            and minutes_since_open < opening_noise_minutes
            and not features.get("level_confluence")
        ):
            quality_failures.append(
                "opening VWAP retest lacks nearby level confluence"
            )
            add_penalty("vwap_opening_noise", opening_penalty)

        if cross_count > max_crosses:
            add_penalty("vwap_whipsaw", whipsaw_penalty)
            hard_blocks.append(
                f"VWAP has crossed {cross_count} times recently; likely chop/whipsaw"
            )

        if quality_failures:
            add_penalty("vwap_quality_gate", quality_penalty)
            hard_blocks.extend(quality_failures)

    def _apply_spy_vwap_reclaim_review_gate(
        self,
        setup: SetupSignal,
        features: Dict,
        add_penalty,
        hard_blocks: list,
    ) -> None:
        strategy = self.settings.strategy
        if not strategy.get("block_weak_spy_vwap_reclaim_longs", True):
            return
        if (
            setup.symbol != "SPY"
            or setup.setup_type != "VWAP reclaim + retest"
            or setup.direction.upper() != "LONG"
        ):
            return

        min_volume_ratio = float(strategy.get("spy_vwap_reclaim_min_volume_ratio", 1.5))
        min_body_ratio = float(strategy.get("spy_vwap_reclaim_min_body_ratio", 0.45))
        min_close_position = float(strategy.get("spy_vwap_reclaim_min_close_position", 0.7))
        volume_ratio = float(features.get("vwap_volume_ratio") or 0)
        body_ratio = float(features.get("vwap_body_ratio") or 0)
        close_position = float(features.get("vwap_close_position") or 0)
        failures = [
            "SPY VWAP reclaim long is blocked pending review; prior replay underperformed"
        ]
        if volume_ratio < min_volume_ratio:
            failures.append(
                f"SPY VWAP reclaim volume ratio {volume_ratio:.2f} is below review minimum {min_volume_ratio:.2f}"
            )
        if body_ratio < min_body_ratio:
            failures.append(
                f"SPY VWAP reclaim body ratio {body_ratio:.2f} is below review minimum {min_body_ratio:.2f}"
            )
        if close_position < min_close_position:
            failures.append(
                f"SPY VWAP reclaim close position {close_position:.2f} is below review minimum {min_close_position:.2f}"
            )
        if not features.get("market_confirmed"):
            failures.append("SPY VWAP reclaim lacks peer confirmation")
        if not features.get("level_confluence"):
            failures.append("SPY VWAP reclaim lacks nearby level confluence")
        add_penalty(
            "spy_vwap_reclaim_review_block",
            int(self.settings.scoring_weights.get("spy_vwap_reclaim_review_penalty", -25)),
        )
        hard_blocks.extend(failures)


def _minutes_since_regular_open(
    setup: SetupSignal, features: Dict, settings: Settings
) -> Optional[int]:
    raw_timestamp = features.get("signal_timestamp") or setup.created_at.isoformat()
    try:
        timestamp = datetime.fromisoformat(str(raw_timestamp))
    except ValueError:
        return None
    if features.get("signal_source") == "yfinance" and ZoneInfo is not None:
        timestamp = timestamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone))
    regular_start = str(settings.market_hours.get("regular_start", "09:30"))
    hour, minute = regular_start.split(":", 1)
    open_minutes = int(hour) * 60 + int(minute)
    current_minutes = timestamp.hour * 60 + timestamp.minute
    return current_minutes - open_minutes


def _fast_momentum_exception(features: Dict, reason: str, settings: Settings) -> bool:
    if not features.get("midday_momentum_exception"):
        return False
    if "midday" not in reason and "mixed" not in reason:
        return False
    min_volume_ratio = float(settings.strategy.get("midday_exception_min_volume_ratio", 2.4))
    min_range_ratio = float(settings.strategy.get("midday_exception_min_range_ratio", 2.0))
    min_move_pct = float(settings.strategy.get("midday_exception_min_move_pct", 0.35))
    return (
        float(features.get("volume_expansion_ratio") or 0) >= min_volume_ratio
        and float(features.get("range_expansion_ratio") or 0) >= min_range_ratio
        and float(features.get("recent_move_pct") or 0) >= min_move_pct
        and bool(features.get("market_confirmed"))
        and bool(features.get("timeframe_aligned"))
    )


def _fast_momentum_risk_override_allowed(features: Dict, settings: Settings) -> bool:
    if not settings.strategy.get("fast_momentum_overrides_risk_blocks", False):
        return False
    if not features.get("fast_momentum_expansion"):
        return False
    min_volume_ratio = float(settings.strategy.get("midday_exception_min_volume_ratio", 2.4))
    min_range_ratio = float(settings.strategy.get("midday_exception_min_range_ratio", 2.0))
    min_move_pct = float(settings.strategy.get("midday_exception_min_move_pct", 0.35))
    return (
        float(features.get("volume_expansion_ratio") or 0) >= min_volume_ratio
        and float(features.get("range_expansion_ratio") or 0) >= min_range_ratio
        and float(features.get("recent_move_pct") or 0) >= min_move_pct
        and bool(features.get("market_confirmed"))
        and bool(features.get("timeframe_aligned"))
    )


def _all_index_trend_continuation_override_allowed(
    setup: SetupSignal, features: Dict, settings: Settings
) -> bool:
    if not settings.strategy.get("fast_momentum_overrides_risk_blocks", False):
        return False
    if setup.setup_type not in {"Momentum continuation"} and not setup.setup_type.startswith("Strat "):
        return False
    if features.get("stale_data") or features.get("weak_volume") or features.get("overextended"):
        return False
    if features.get("conflicting_timeframes"):
        return False
    if setup.risk_reward < float(settings.strategy.get("fast_momentum_min_risk_reward", 1.0)):
        return False
    if not (
        features.get("timeframe_aligned")
        and features.get("market_confirmed")
        and features.get("vwap_confirmed")
        and features.get("volume_confirmed")
    ):
        return False

    expected_bias = "bullish" if str(setup.direction).upper() == "LONG" else "bearish"
    peer_biases = features.get("peer_biases") or {}
    required_symbols = settings.strategy.get("level_break_required_index_symbols", ["SPY", "QQQ", "IWM"])
    if any(str(peer_biases.get(symbol, "")).lower() != expected_bias for symbol in required_symbols):
        return False

    bias_keys = ("day_bias", "hour_bias", "thirty_bias", "fifteen_bias", "primary_bias")
    return all(str(features.get(key, "")).lower() == expected_bias for key in bias_keys)
