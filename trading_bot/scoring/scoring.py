from __future__ import annotations

from typing import Dict

from trading_bot.models import SetupSignal
from trading_bot.settings import Settings


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
        if setup.setup_type == "Momentum continuation":
            add_penalty(
                "momentum_continuation_validation",
                int(weights.get("momentum_continuation_penalty", -14)),
            )
        if setup.setup_type.startswith("Strat "):
            add_penalty(
                "strat_continuation_validation",
                int(weights.get("strat_continuation_penalty", -12)),
            )

        no_trade = no_trade or {}
        if no_trade.get("is_no_trade"):
            reason = no_trade.get("reason", "").lower()
            if "chop" in reason:
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
