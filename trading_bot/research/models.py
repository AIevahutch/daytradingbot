from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from trading_bot.models import utc_now


@dataclass
class ResearchBrief:
    session_date: str
    phase: str
    risk_score: int
    bias: str
    trade_today: bool
    decision: str
    summary: str
    drivers: List[str] = field(default_factory=list)
    hard_blocks: List[str] = field(default_factory=list)
    source_status: Dict[str, str] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    openai_status: str = "not_requested"
    openai_model: Optional[str] = None
    email_status: str = "not_requested"
    email_error: Optional[str] = None
    email_sent_at: Optional[datetime] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "session_date": self.session_date,
            "phase": self.phase,
            "created_at": self.created_at.isoformat(),
            "risk_score": self.risk_score,
            "bias": self.bias,
            "trade_today": self.trade_today,
            "decision": self.decision,
            "summary": self.summary,
            "drivers": self.drivers,
            "hard_blocks": self.hard_blocks,
            "source_status": self.source_status,
            "evidence": self.evidence,
            "openai_status": self.openai_status,
            "openai_model": self.openai_model,
            "email_status": self.email_status,
            "email_error": self.email_error,
            "email_sent_at": self.email_sent_at.isoformat() if self.email_sent_at else None,
        }


@dataclass
class ResearchInput:
    source: str
    status: str
    category: str
    title: str
    detail: str
    impact: int = 0
    bias: str = "neutral"
    url: str = ""
    occurred_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "impact": self.impact,
            "bias": self.bias,
            "url": self.url,
            "occurred_at": self.occurred_at,
            "metadata": self.metadata,
        }
