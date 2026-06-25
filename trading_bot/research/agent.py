from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Dict, Iterable, List, Optional

from trading_bot.email.gmail import GmailSMTPClient
from trading_bot.models import utc_now
from trading_bot.research.calendar import PHASES, is_trading_day
from trading_bot.research.models import ResearchBrief, ResearchInput
from trading_bot.research.providers import (
    EarningsOptionsProvider,
    EconomicCalendarProvider,
    FearGreedProxyProvider,
    MarketStructureProvider,
    NewsSentimentProvider,
    VolatilityProvider,
)
from trading_bot.research.scoring import build_research_brief
from trading_bot.settings import Settings
from trading_bot.storage import SQLiteStore
from trading_bot.summaries import OpenAISummaryClient, deterministic_summary

logger = logging.getLogger(__name__)


class ResearchAgent:
    def __init__(
        self,
        settings: Settings,
        store: SQLiteStore,
        providers: Optional[Iterable] = None,
        summary_client: Optional[OpenAISummaryClient] = None,
        email_client: Optional[GmailSMTPClient] = None,
    ):
        self.settings = settings
        self.store = store
        self.providers = list(providers) if providers is not None else default_providers()
        self.summary_client = summary_client or OpenAISummaryClient(settings)
        self.email_client = email_client or GmailSMTPClient(settings)

    def run_phase(
        self,
        phase: str,
        *,
        send_email: bool = False,
        session_date: Optional[date] = None,
    ) -> Dict:
        if phase not in PHASES:
            raise ValueError(f"Unsupported research phase: {phase}")
        session_date = session_date or current_session_date(self.settings)
        if not is_trading_day(session_date):
            return {
                "status": "skipped",
                "reason": f"{session_date.isoformat()} is not a trading day.",
                "session_date": session_date.isoformat(),
                "phase": phase,
            }

        brief = self.generate_brief(phase, session_date)
        summary = self.summary_client.generate(brief)
        brief.openai_status = summary.status
        brief.openai_model = summary.model
        brief.summary = summary.body
        brief_id = self.store.upsert_research_brief(brief)

        email_result = None
        if send_email:
            email_result = self.email_client.send(summary.subject, summary.body)
            brief.email_status = email_result.status
            brief.email_error = email_result.error
            brief.email_sent_at = utc_now() if email_result.delivered else None
            self.store.update_research_email_status(
                brief_id,
                brief.email_status,
                brief.email_error,
                brief.email_sent_at,
            )
            self.store.insert_research_email_attempt(
                brief_id=brief_id,
                to_address=email_result.to_address,
                subject=email_result.subject,
                delivered=email_result.delivered,
                error=email_result.error,
                provider=email_result.provider,
            )

        payload = brief.as_dict()
        payload["id"] = brief_id
        payload["email_result"] = email_result.__dict__ if email_result else None
        return payload

    def generate_brief(self, phase: str, session_date: date) -> ResearchBrief:
        inputs: List[ResearchInput] = []
        for provider in self.providers:
            try:
                inputs.extend(provider.collect(session_date, phase, self.settings, self.store))
            except Exception as exc:
                logger.exception("Research provider failed: %s", getattr(provider, "name", provider))
                inputs.append(
                    ResearchInput(
                        source=getattr(provider, "name", provider.__class__.__name__),
                        status="fail",
                        category="provider",
                        title="Research provider failed",
                        detail=str(exc),
                        impact=8,
                    )
                )
        return build_research_brief(session_date, phase, inputs)

    def send_test_email(self) -> Dict:
        summary = deterministic_summary(
            ResearchBrief(
                session_date=current_session_date(self.settings).isoformat(),
                phase="premarket",
                risk_score=0,
                bias="neutral",
                trade_today=False,
                decision="email_test",
                summary="Research email delivery test.",
                drivers=["This is a delivery test only."],
                hard_blocks=["No trading action should be taken from this test."],
                source_status={"email": "test"},
            )
        )
        result = self.email_client.send("Trading Bot Research Email Test", summary.body)
        attempt_id = self.store.insert_research_email_attempt(
            brief_id=None,
            to_address=result.to_address,
            subject=result.subject,
            delivered=result.delivered,
            error=result.error,
            provider=result.provider,
        )
        return {"attempt_id": attempt_id, **result.__dict__}


def default_providers() -> List:
    return [
        EconomicCalendarProvider(),
        MarketStructureProvider(),
        VolatilityProvider(),
        NewsSentimentProvider(),
        EarningsOptionsProvider(),
        FearGreedProxyProvider(),
    ]


def current_session_date(settings: Settings, now: Optional[datetime] = None) -> date:
    now = now or utc_now()
    try:
        from zoneinfo import ZoneInfo

        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(ZoneInfo(settings.timezone)).date()
    except Exception:
        return now.date()


def run_research_schedule(settings: Settings, store: SQLiteStore) -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError as exc:
        raise RuntimeError("apscheduler is required for research scheduling.") from exc

    scheduler = BlockingScheduler(timezone=settings.timezone)
    agent = ResearchAgent(settings, store)
    phase_times = settings.research.get("phase_times", {})
    for phase in PHASES:
        hour, minute = str(phase_times.get(phase, "08:15")).split(":", 1)
        scheduler.add_job(
            _scheduled_phase,
            "cron",
            day_of_week="mon-fri",
            hour=int(hour),
            minute=int(minute),
            args=[settings, store, phase],
            id=f"research_{phase}",
            replace_existing=True,
        )
    logger.info("Starting research schedule: %s", json.dumps(phase_times))
    scheduler.start()


def _scheduled_phase(settings: Settings, store: SQLiteStore, phase: str) -> None:
    session_date = current_session_date(settings)
    if not is_trading_day(session_date):
        logger.info("Skipping %s research on non-trading day %s", phase, session_date)
        return
    ResearchAgent(settings, store).run_phase(phase, send_email=True, session_date=session_date)
