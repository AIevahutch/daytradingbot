from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional
from urllib.request import Request, urlopen

from trading_bot.research.models import ResearchBrief
from trading_bot.settings import Settings


MOMENTUM_EXCEPTION_TITLE = "Momentum Exception:"
MOMENTUM_EXCEPTION_NOTE = "\n".join(
    [
        MOMENTUM_EXCEPTION_TITLE,
        "- High research risk does not block alerts anymore; it adds a caution warning to stay selective.",
        "- Fast Momentum Expansion and all-index trend continuation still need SPY/QQQ/IWM alignment.",
        "- Every alert still requires volume confirmation, timeframe alignment, VWAP confirmation, and clean risk/reward.",
        "- This is a heads-up only. Confirm on TradingView before acting.",
    ]
)


@dataclass
class SummaryResult:
    subject: str
    body: str
    status: str
    model: Optional[str] = None
    error: Optional[str] = None


class OpenAISummaryClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = str(settings.openai_summary.get("model", "gpt-5.4-mini"))
        self.api_key = os.environ.get("OPENAI_API_KEY", "")

    def generate(self, brief: ResearchBrief) -> SummaryResult:
        include_fast_momentum_exception = bool(
            self.settings.strategy.get("fast_momentum_overrides_risk_blocks", False)
        )
        fallback = deterministic_summary(
            brief,
            model=self.model,
            include_fast_momentum_exception=include_fast_momentum_exception,
        )
        if not bool(self.settings.openai_summary.get("enabled", True)):
            fallback.status = "disabled"
            return fallback
        if not self.api_key:
            fallback.status = "missing_api_key"
            fallback.error = "OPENAI_API_KEY is not configured."
            return fallback

        instructions = (
            "You write concise trading research emails for an alert-only SPY/QQQ/IWM options dashboard. "
            "Do not recommend specific contracts, strikes, broker actions, or guaranteed outcomes. "
            "Use the provided rule-based decision as the source of truth."
        )
        if include_fast_momentum_exception:
            instructions += (
                " Include a short Momentum Exception note: high research risk does not block alerts anymore; "
                "it adds a caution warning. Confirmed Fast Momentum Expansion and all-index trend continuation "
                "setups still require volume, timeframe, VWAP, risk/reward, and SPY/QQQ/IWM confirmation gates. "
                "Still remind the user to confirm manually."
            )

        payload = {
            "model": self.model,
            "store": False,
            "instructions": instructions,
            "input": json.dumps(brief.as_dict(), sort_keys=True),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "trading_research_email",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "subject": {"type": "string"},
                            "body": {"type": "string"},
                        },
                        "required": ["subject", "body"],
                    },
                }
            },
        }
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            fallback.status = "failed"
            fallback.error = str(exc)
            return fallback

        text = data.get("output_text") or _extract_output_text(data)
        try:
            parsed = json.loads(text)
            return SummaryResult(
                subject=str(parsed["subject"]).strip(),
                body=str(parsed["body"]).strip(),
                status="ok",
                model=self.model,
            )
        except Exception as exc:
            fallback.status = "failed"
            fallback.error = f"Could not parse OpenAI structured summary: {exc}"
            return fallback


def deterministic_summary(
    brief: ResearchBrief,
    model: Optional[str] = None,
    include_fast_momentum_exception: bool = True,
) -> SummaryResult:
    phase = {
        "premarket": "Premarket",
        "morning": "Morning",
        "midday": "Midday",
        "eod": "EOD",
    }.get(brief.phase, brief.phase.title())
    if not brief.trade_today:
        decision = "DO NOT TRADE"
    elif brief.decision == "trade_with_caution":
        decision = "TRADE WITH CAUTION"
    else:
        decision = "TRADE ALLOWED"
    subject = f"{phase} Market Research: {decision} | Risk {brief.risk_score}/100"
    driver_lines = "\n".join(f"- {driver}" for driver in brief.drivers[:5])
    warnings = "\n".join(f"- {block}" for block in brief.hard_blocks) or "- None"
    lines = [
        f"{phase} market research summary",
        "",
        f"Decision: {decision}",
        f"Risk score: {brief.risk_score}/100",
        f"Bias: {brief.bias}",
        "",
        "Why it matters:",
        driver_lines or "- No major configured driver.",
        "",
        "Risk warnings:",
        warnings,
        "",
    ]
    if include_fast_momentum_exception:
        lines.extend([MOMENTUM_EXCEPTION_NOTE, ""])
    lines.append(
        "Reminder: this is alert-only research for SPY/QQQ/IWM options context. Confirm manually before acting."
    )
    body = "\n".join(lines)
    return SummaryResult(subject=subject, body=body, status="fallback", model=model)


def ensure_fast_momentum_exception_note(summary: str, enabled: bool = True) -> str:
    text = str(summary or "").strip()
    if not enabled or MOMENTUM_EXCEPTION_TITLE in text:
        return text
    if not text:
        return MOMENTUM_EXCEPTION_NOTE
    return f"{text}\n\n{MOMENTUM_EXCEPTION_NOTE}"


def _extract_output_text(data: dict) -> str:
    chunks = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(str(content["text"]))
    return "\n".join(chunks)
