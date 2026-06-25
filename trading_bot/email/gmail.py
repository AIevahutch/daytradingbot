from __future__ import annotations

import os
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

from trading_bot.settings import PROJECT_ROOT, Settings, load_env_file


@dataclass
class EmailDeliveryResult:
    delivered: bool
    to_address: str = ""
    subject: str = ""
    error: Optional[str] = None
    provider: str = "gmail_smtp"
    status: str = "failed"


class GmailSMTPClient:
    def __init__(self, settings: Settings):
        load_env_file(PROJECT_ROOT / ".env")
        email_settings = settings.email
        self.host = str(email_settings.get("smtp_host", "smtp.gmail.com"))
        self.port = int(email_settings.get("smtp_port", 587))
        self.username = (
            os.environ.get("GMAIL_SMTP_USERNAME")
            or os.environ.get("GMAIL_ADDRESS")
            or str(email_settings.get("from_address", ""))
        )
        raw_password = os.environ.get("GMAIL_SMTP_PASSWORD") or os.environ.get("GMAIL_APP_PASSWORD", "")
        self.password = re.sub(r"\s+", "", raw_password)
        self.to_address = (
            os.environ.get("RESEARCH_EMAIL_TO")
            or str(email_settings.get("to_address", ""))
            or self.username
        )
        self.from_address = str(email_settings.get("from_address", "")) or self.username
        self.enabled = bool(email_settings.get("enabled", True))

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.host and self.port and self.username and self.password and self.to_address)

    def validate_configuration(self) -> list:
        missing = []
        if not self.enabled:
            missing.append("email.enabled")
        if not self.username:
            missing.append("GMAIL_SMTP_USERNAME or GMAIL_ADDRESS")
        if not self.password:
            missing.append("GMAIL_SMTP_PASSWORD or GMAIL_APP_PASSWORD")
        if not self.to_address:
            missing.append("RESEARCH_EMAIL_TO")
        return missing

    def send(self, subject: str, body: str) -> EmailDeliveryResult:
        if not self.configured:
            missing = ", ".join(self.validate_configuration())
            return EmailDeliveryResult(
                False,
                to_address=self.to_address,
                subject=subject,
                error=f"Email is not configured: {missing}",
                status="not_configured",
            )

        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = self.to_address
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(message)
        except Exception as exc:
            return EmailDeliveryResult(
                False,
                to_address=self.to_address,
                subject=subject,
                error=str(exc),
                status="failed",
            )
        return EmailDeliveryResult(
            True,
            to_address=self.to_address,
            subject=subject,
            status="delivered",
        )
