from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading_bot.models import SetupSignal


ALERT_FOOTER = (
    "Alert only. Never place trades automatically. Confirm manually on TradingView before acting."
)


def format_alert(setup: SetupSignal) -> str:
    title = f"{setup.symbol} {setup.direction} SETUP"
    return "\n".join(
        [
            title,
            f"Setup: {setup.setup_type}",
            f"Entry: {setup.entry_low:.2f}-{setup.entry_high:.2f}",
            f"Stop: {setup.stop_loss:.2f}",
            f"Target 1: {setup.target1:.2f}",
            f"Target 2: {setup.target2:.2f}",
            f"Invalidation: {setup.invalidation:.2f}",
            f"Confidence: {setup.confidence}/100",
            f"Risk/Reward: {setup.risk_reward:.2f}",
            "",
            "Reason:",
            setup.reasoning,
            "",
            "Avoid if:",
            setup.avoid_if,
            "",
            ALERT_FOOTER,
        ]
    )


@dataclass
class TelegramResult:
    delivered: bool
    error: Optional[str] = None
    attempts: int = 1


class TelegramClient:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
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
