from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from trading_bot.signal_sources import (
    CARTER_SIGNAL_SOURCE,
    CORE_SIGNAL_SOURCE,
    FEATURE_ALERT_SOURCE,
)


CORE_TELEGRAM_SETUP_TYPE = "Liquidity sweep reversal"
CORE_TELEGRAM_CONFIDENCE = 100
CORE_TELEGRAM_TIMEFRAMES = {"15m", "30m"}
CARTER_PUT_DIRECTION = "SHORT"
TACTICAL_EXIT_SETUP_TYPE = "Suggested sell/partial"


def is_core_telegram_entry_allowed(setup: Mapping[str, Any]) -> bool:
    return (
        _text(setup.get("status"), "alert_ready") == "alert_ready"
        and _text(setup.get("setup_type")) == CORE_TELEGRAM_SETUP_TYPE
        and _int(setup.get("confidence")) >= CORE_TELEGRAM_CONFIDENCE
        and _text(setup.get("timeframe")) in CORE_TELEGRAM_TIMEFRAMES
    )


def is_carter_put_telegram_entry_allowed(
    setup: Mapping[str, Any],
    *,
    alert_threshold: int,
) -> bool:
    return (
        _text(setup.get("status"), "alert_ready") == "alert_ready"
        and _text(setup.get("setup_type")) == "Carter Squeeze"
        and _text(setup.get("direction")).upper() == CARTER_PUT_DIRECTION
        and _int(setup.get("confidence")) >= alert_threshold
    )


def is_current_approved_telegram_alert(
    alert: Mapping[str, Any],
    setup: Optional[Mapping[str, Any]],
    *,
    alert_threshold: int,
) -> bool:
    """Return whether an alert row belongs in Eva's current Telegram stream."""
    setup_row = setup or {}
    setup_source = _alert_source(setup_row)
    alert_setup_type = _text(alert.get("setup_type"))

    if alert_setup_type == TACTICAL_EXIT_SETUP_TYPE:
        return setup_source == CORE_SIGNAL_SOURCE and is_core_telegram_entry_allowed(
            _merged_entry(alert, setup_row)
        )

    if setup_source == CARTER_SIGNAL_SOURCE:
        return is_carter_put_telegram_entry_allowed(
            _merged_entry(alert, setup_row),
            alert_threshold=alert_threshold,
        )

    if setup_source == CORE_SIGNAL_SOURCE:
        return is_core_telegram_entry_allowed(_merged_entry(alert, setup_row))

    return False


def _merged_entry(alert: Mapping[str, Any], setup: Mapping[str, Any]) -> dict:
    merged = dict(alert)
    for key in (
        "setup_type",
        "direction",
        "timeframe",
        "confidence",
        "status",
        "features_json",
    ):
        value = setup.get(key)
        if value not in (None, ""):
            merged[key] = value
    return merged


def _alert_source(setup: Mapping[str, Any]) -> str:
    features = _features(setup.get("features_json") or setup.get("features") or {})
    return _text(features.get(FEATURE_ALERT_SOURCE), CORE_SIGNAL_SOURCE)


def _features(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text and text.lower() != "nan" else default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
