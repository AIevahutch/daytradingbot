from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Dict, Iterable, List, Mapping, Optional
from zoneinfo import ZoneInfo

from trading_bot.models import Candle, SetupSignal


DAY_TRADE_OUTCOME = "expired_daytrade"
DEFAULT_EXIT_TIME = "15:55"
DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_ALLOWED_TIMEFRAMES = {"15m", "30m"}
DEFAULT_SYMBOL_LIMITS = {
    "SPY": {"max_entry_width": 2.50, "max_risk_per_share": 3.00, "max_target_distance": 3.00},
    "QQQ": {"max_entry_width": 4.00, "max_risk_per_share": 5.00, "max_target_distance": 5.00},
    "IWM": {"max_entry_width": 1.25, "max_risk_per_share": 1.50, "max_target_distance": 1.50},
}


@dataclass(frozen=True)
class DayTradeContractAssessment:
    eligible: bool
    reason_codes: List[str]
    metrics: Dict[str, object]

    @property
    def reason(self) -> str:
        return "; ".join(self.reason_codes)


def config_from_settings(settings) -> Dict:
    strategy = getattr(settings, "strategy", {}) or {}
    contract = strategy.get("day_trade_contract") or {}
    return {
        "enabled": bool(contract.get("enabled", True)),
        "timezone": contract.get("timezone") or getattr(settings, "timezone", DEFAULT_TIMEZONE),
        "exit_time": contract.get("exit_time", DEFAULT_EXIT_TIME),
        "allowed_timeframes": set(contract.get("allowed_timeframes") or DEFAULT_ALLOWED_TIMEFRAMES),
        "symbol_limits": {
            **DEFAULT_SYMBOL_LIMITS,
            **(contract.get("symbol_limits") or {}),
        },
    }


def assess_day_trade_contract(
    setup: SetupSignal,
    config: Optional[Mapping] = None,
) -> DayTradeContractAssessment:
    config = _normalise_config(config)
    symbol = str(setup.symbol or "").upper()
    limits = _limits_for_symbol(symbol, config)
    entry_width = abs(float(setup.entry_high) - float(setup.entry_low))
    entry_mid = (float(setup.entry_low) + float(setup.entry_high)) / 2
    risk_per_share = abs(entry_mid - float(setup.stop_loss))
    target_distance = abs(float(setup.target1) - entry_mid)
    allowed_timeframes = set(config.get("allowed_timeframes") or DEFAULT_ALLOWED_TIMEFRAMES)
    reason_codes: List[str] = []

    if not bool(config.get("enabled", True)):
        return DayTradeContractAssessment(
            eligible=True,
            reason_codes=[],
            metrics={
                "eligible": True,
                "enabled": False,
                "entry_width": round(entry_width, 4),
                "risk_per_share": round(risk_per_share, 4),
                "target_distance": round(target_distance, 4),
            },
        )

    if str(setup.timeframe) not in allowed_timeframes:
        reason_codes.append(f"timeframe {setup.timeframe} is not day-trade alertable")
    if entry_width > limits["max_entry_width"]:
        reason_codes.append(
            f"entry zone {entry_width:.2f} is wider than {limits['max_entry_width']:.2f}"
        )
    if risk_per_share > limits["max_risk_per_share"]:
        reason_codes.append(
            f"risk {risk_per_share:.2f} is wider than {limits['max_risk_per_share']:.2f}"
        )
    if target_distance > limits["max_target_distance"]:
        reason_codes.append(
            f"target distance {target_distance:.2f} is wider than {limits['max_target_distance']:.2f}"
        )

    metrics = {
        "eligible": not reason_codes,
        "symbol": symbol,
        "timeframe": str(setup.timeframe),
        "entry_mid": round(entry_mid, 4),
        "entry_width": round(entry_width, 4),
        "risk_per_share": round(risk_per_share, 4),
        "target_distance": round(target_distance, 4),
        "max_entry_width": limits["max_entry_width"],
        "max_risk_per_share": limits["max_risk_per_share"],
        "max_target_distance": limits["max_target_distance"],
        "exit_time": str(config.get("exit_time", DEFAULT_EXIT_TIME)),
        "timezone": str(config.get("timezone", DEFAULT_TIMEZONE)),
        "reason_codes": list(reason_codes),
    }
    return DayTradeContractAssessment(not reason_codes, reason_codes, metrics)


def annotate_day_trade_contract(
    setup: SetupSignal,
    config: Optional[Mapping] = None,
) -> DayTradeContractAssessment:
    assessment = assess_day_trade_contract(setup, config)
    setup.features["day_trade_contract"] = assessment.metrics
    return assessment


def tighten_day_trade_signal(
    setup: SetupSignal,
    config: Optional[Mapping] = None,
) -> DayTradeContractAssessment:
    """Compress a valid thesis into practical same-session execution levels."""
    if setup.setup_type != "Liquidity sweep reversal":
        return annotate_day_trade_contract(setup, config)

    before = assess_day_trade_contract(setup, config)
    if before.eligible:
        return annotate_day_trade_contract(setup, config)

    config = _normalise_config(config)
    limits = _limits_for_symbol(str(setup.symbol or "").upper(), config)
    original = {
        "entry_low": setup.entry_low,
        "entry_high": setup.entry_high,
        "stop_loss": setup.stop_loss,
        "target1": setup.target1,
        "target2": setup.target2,
        "invalidation": setup.invalidation,
        "risk_reward": setup.risk_reward,
    }
    original_mid = (float(setup.entry_low) + float(setup.entry_high)) / 2
    original_risk = abs(original_mid - float(setup.stop_loss))
    width = min(
        abs(float(setup.entry_high) - float(setup.entry_low)),
        limits["max_entry_width"],
    )
    risk = min(max(original_risk, 0.01), limits["max_risk_per_share"])

    if str(setup.direction or "").upper() == "SHORT":
        anchor = float(setup.entry_high)
        setup.entry_low = anchor - width
        setup.entry_high = anchor
        entry_mid = (setup.entry_low + setup.entry_high) / 2
        setup.stop_loss = entry_mid + risk
        setup.target1 = entry_mid - risk
        setup.target2 = entry_mid - risk * 2
    else:
        anchor = float(setup.entry_low)
        setup.entry_low = anchor
        setup.entry_high = anchor + width
        entry_mid = (setup.entry_low + setup.entry_high) / 2
        setup.stop_loss = entry_mid - risk
        setup.target1 = entry_mid + risk
        setup.target2 = entry_mid + risk * 2

    setup.invalidation = setup.stop_loss
    setup.risk_reward = round(_risk_reward(setup.direction, entry_mid, setup.stop_loss, setup.target1), 2)
    setup.features["day_trade_adjustment"] = {
        "adjusted": True,
        "reason_codes": before.reason_codes,
        "original": {key: round(float(value), 4) for key, value in original.items()},
        "entry_width_cap": limits["max_entry_width"],
        "risk_cap": limits["max_risk_per_share"],
        "target_model": "target1_1r_target2_2r",
    }
    return annotate_day_trade_contract(setup, config)


def day_trade_expiry_for(
    event_time: datetime,
    config: Optional[Mapping] = None,
) -> datetime:
    config = _normalise_config(config)
    tz = ZoneInfo(str(config.get("timezone", DEFAULT_TIMEZONE)))
    local_event = _as_utc(event_time).astimezone(tz)
    exit_time = _parse_time(str(config.get("exit_time", DEFAULT_EXIT_TIME)))
    local_expiry = datetime.combine(local_event.date(), exit_time, tzinfo=tz)
    return local_expiry.astimezone(timezone.utc).replace(tzinfo=None)


def candles_through_day_trade_expiry(
    candles: Iterable[Candle],
    event_time: datetime,
    config: Optional[Mapping] = None,
) -> List[Candle]:
    expiry = day_trade_expiry_for(event_time, config)
    return [candle for candle in candles if candle.timestamp <= expiry]


def mark_expired_day_trade(
    metrics: Dict[str, object],
    event_time: datetime,
    config: Optional[Mapping] = None,
) -> Dict[str, object]:
    expiry = day_trade_expiry_for(event_time, config)
    updated = dict(metrics)
    updated["resolution"] = DAY_TRADE_OUTCOME
    updated["expired_at"] = expiry.isoformat()
    updated["day_trade_expired"] = True
    if updated.get("tactical_outcome") == "open":
        updated["tactical_outcome"] = DAY_TRADE_OUTCOME
        updated["tactical_r_multiple"] = 0.0
    return updated


def _normalise_config(config: Optional[Mapping]) -> Dict:
    if config is None:
        return {
            "enabled": True,
            "timezone": DEFAULT_TIMEZONE,
            "exit_time": DEFAULT_EXIT_TIME,
            "allowed_timeframes": set(DEFAULT_ALLOWED_TIMEFRAMES),
            "symbol_limits": DEFAULT_SYMBOL_LIMITS,
        }
    normalised = dict(config)
    normalised.setdefault("enabled", True)
    normalised.setdefault("timezone", DEFAULT_TIMEZONE)
    normalised.setdefault("exit_time", DEFAULT_EXIT_TIME)
    normalised.setdefault("allowed_timeframes", set(DEFAULT_ALLOWED_TIMEFRAMES))
    normalised.setdefault("symbol_limits", DEFAULT_SYMBOL_LIMITS)
    return normalised


def _limits_for_symbol(symbol: str, config: Mapping) -> Dict[str, float]:
    limits_by_symbol = config.get("symbol_limits") or DEFAULT_SYMBOL_LIMITS
    raw = limits_by_symbol.get(symbol) or limits_by_symbol.get("DEFAULT") or {}
    defaults = DEFAULT_SYMBOL_LIMITS.get(symbol, DEFAULT_SYMBOL_LIMITS["SPY"])
    return {
        "max_entry_width": float(raw.get("max_entry_width", defaults["max_entry_width"])),
        "max_risk_per_share": float(raw.get("max_risk_per_share", defaults["max_risk_per_share"])),
        "max_target_distance": float(raw.get("max_target_distance", defaults["max_target_distance"])),
    }


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _risk_reward(direction: str, entry_mid: float, stop: float, target1: float) -> float:
    risk = abs(entry_mid - stop)
    reward = abs(target1 - entry_mid)
    if risk <= 0:
        return 0.0
    return reward / risk


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
