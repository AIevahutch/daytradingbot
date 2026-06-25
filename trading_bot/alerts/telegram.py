from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading_bot.models import SetupSignal
from trading_bot.signal_sources import FEATURE_SOURCE_LABEL
from trading_bot.settings import PROJECT_ROOT, load_env_file


ALERT_FOOTER = (
    "Alert only. Never place trades automatically. Confirm manually on TradingView before acting."
)


def _action_label(direction: str) -> str:
    normalized = direction.upper()
    if normalized == "SHORT":
        return "SELL/SHORT"
    return "BUY"


def tactical_exit_price(setup: SetupSignal) -> Optional[float]:
    features = setup.features or {}
    raw_price = features.get("tactical_exit_price")
    if raw_price is not None:
        try:
            return float(raw_price)
        except (TypeError, ValueError):
            return None
    raw_multiple = features.get("tactical_exit_r_multiple")
    if raw_multiple is None:
        return None
    entry_mid = (setup.entry_low + setup.entry_high) / 2
    risk = abs(entry_mid - setup.stop_loss)
    if risk <= 0:
        return None
    multiple = float(raw_multiple)
    if setup.direction.upper() == "SHORT":
        return entry_mid - risk * multiple
    return entry_mid + risk * multiple


def _management_lines(setup: SetupSignal) -> list[str]:
    features = setup.features or {}
    if not features.get("tactical_management"):
        return []
    price = tactical_exit_price(setup)
    if price is None:
        return []
    multiple = float(features.get("tactical_exit_r_multiple", 1.0))
    action = str(features.get("tactical_exit_action") or "SELL/PARTIAL")
    return [
        f"Suggested {action}: {price:.2f} (+{multiple:g}R)",
        "At that level, consider partial profit and/or tightening the stop. Manual confirmation only.",
    ]


def _index_alignment_line(setup: SetupSignal) -> str:
    features = setup.features or {}
    raw_biases = features.get("peer_biases") or features.get("market_biases") or {}
    if not isinstance(raw_biases, dict):
        raw_biases = {}

    symbols = ("SPY", "QQQ", "IWM")
    biases = {
        symbol: str(raw_biases.get(symbol) or "").strip().lower()
        for symbol in symbols
    }
    expected = "bullish" if setup.direction.upper() == "LONG" else "bearish"
    readable = ", ".join(
        f"{symbol}={biases[symbol].upper() if biases[symbol] else 'UNKNOWN'}"
        for symbol in symbols
    )

    if all(biases[symbol] == expected for symbol in symbols):
        return f"Index alignment: YES - SPY/QQQ/IWM all {expected.upper()}"
    if any(biases.values()):
        return f"Index alignment: NO/MIXED - {readable}"
    if features.get("market_confirmed"):
        return "Index alignment: confirmed by peer ETFs"
    return "Index alignment: not confirmed"


def _research_risk_line(setup: SetupSignal) -> Optional[str]:
    research = ((setup.features or {}).get("score_breakdown") or {}).get("research") or {}
    if not research.get("enabled"):
        return None
    try:
        risk_score = int(research.get("risk_score"))
    except (TypeError, ValueError):
        return None
    if risk_score >= 65:
        return f"Research risk: HIGH ({risk_score}/100) - be careful and confirm manually."
    if risk_score >= 40:
        return f"Research risk: CAUTION ({risk_score}/100) - wait for a clean A+ setup."
    return None


def format_alert(setup: SetupSignal) -> str:
    features = setup.features or {}
    action = _action_label(setup.direction)
    reason = setup.reasoning.strip() or f"{setup.setup_type} triggered."
    avoid_if = setup.avoid_if.strip() or "price invalidates the setup."
    market_condition = (setup.market_condition or "unknown").strip().upper()
    lines = [
        f"{action} {setup.symbol} because {reason}",
        f"Confidence rate: {setup.confidence}/100",
        f"Market condition: {market_condition}",
        _index_alignment_line(setup),
    ]
    research_line = _research_risk_line(setup)
    if research_line:
        lines.append(research_line)
    lines.extend(
        [
            "",
            f"Setup: {setup.setup_type}",
            f"Direction: {setup.direction}",
            f"Entry zone: {setup.entry_low:.2f}-{setup.entry_high:.2f}",
            f"Stop loss: {setup.stop_loss:.2f}",
            f"Target 1: {setup.target1:.2f}",
            f"Target 2: {setup.target2:.2f}",
            f"Invalidation: {setup.invalidation:.2f}",
            f"Risk/reward: {setup.risk_reward:.2f}",
        ]
    )
    source_label = str(features.get(FEATURE_SOURCE_LABEL) or "").strip()
    if source_label:
        lines.insert(1, f"Signal source: {source_label}")
    management_lines = _management_lines(setup)
    if management_lines:
        lines.extend(["", *management_lines])
    lines.extend(["", f"Avoid if: {avoid_if}", "", ALERT_FOOTER])
    return "\n".join(lines)


def format_carter_squeeze_alert(setup: SetupSignal) -> str:
    message = format_alert(setup)
    return message.replace(
        f"{_action_label(setup.direction)} {setup.symbol} because",
        f"CARTER SQUEEZE {_action_label(setup.direction)} {setup.symbol} because",
        1,
    )


def format_tactical_exit_alert(
    setup: SetupSignal,
    price: Optional[float] = None,
    original_alert_id: Optional[int] = None,
) -> str:
    exit_price = price if price is not None else tactical_exit_price(setup)
    action = "SELL/PARTIAL" if setup.direction.upper() == "LONG" else "COVER/PARTIAL"
    multiple = float((setup.features or {}).get("tactical_exit_r_multiple", 1.0))
    reason = (
        f"{setup.symbol} {setup.setup_type} reached the tactical +{multiple:g}R management level."
    )
    lines = [
        f"SUGGESTED {action} {setup.symbol} because {reason}",
        "",
        f"Original setup: {setup.setup_type}",
        f"Direction: {setup.direction}",
    ]
    if exit_price is not None:
        lines.append(f"Suggested manage price: {exit_price:.2f}")
    lines.extend(
        [
            f"Original stop: {setup.stop_loss:.2f}",
            f"Original target 1: {setup.target1:.2f}",
            "",
            "Consider partial profit and/or tightening the stop. Confirm manually before acting.",
        ]
    )
    if original_alert_id is not None:
        lines.append(f"Original alert id: {original_alert_id}")
    lines.extend(["", ALERT_FOOTER])
    return "\n".join(lines)


@dataclass
class TelegramResult:
    delivered: bool
    error: Optional[str] = None
    attempts: int = 1


class TelegramClient:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        if token is None or chat_id is None:
            load_env_file(PROJECT_ROOT / ".env")
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def validate_configuration(self) -> list:
        missing = []
        if not self.token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        return missing

    def send_message(
        self, text: str, max_attempts: int = 3, retry_delay_seconds: float = 1.0
    ) -> TelegramResult:
        if not self.configured:
            return TelegramResult(False, "Telegram token/chat id are not configured.", attempts=0)
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = urlencode({"chat_id": self.chat_id, "text": text}).encode("utf-8")
        last_error = None
        attempts = max(1, max_attempts)
        for attempt in range(1, attempts + 1):
            request = Request(url, data=payload, method="POST")
            try:
                with urlopen(request, timeout=10) as response:
                    if response.status < 400:
                        return TelegramResult(True, None, attempts=attempt)
                    last_error = f"Telegram HTTP {response.status}"
            except Exception as exc:
                last_error = str(exc)
            if attempt < attempts and retry_delay_seconds > 0:
                time.sleep(retry_delay_seconds)
        return TelegramResult(False, last_error, attempts=attempts)
