from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


@dataclass
class Candle:
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = "unknown"


@dataclass
class Level:
    symbol: str
    name: str
    price: float
    timeframe: str
    session_date: str
    created_at: datetime = field(default_factory=utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SetupSignal:
    symbol: str
    setup_type: str
    direction: str
    timeframe: str
    created_at: datetime
    entry_low: float
    entry_high: float
    stop_loss: float
    target1: float
    target2: float
    invalidation: float
    confidence: int = 0
    risk_reward: float = 0.0
    reasoning: str = ""
    avoid_if: str = ""
    market_condition: str = "unknown"
    status: str = "candidate"
    features: Dict[str, Any] = field(default_factory=dict)

    @property
    def entry_zone(self) -> str:
        return f"{self.entry_low:.2f}-{self.entry_high:.2f}"


@dataclass
class Trade:
    symbol: str
    setup_type: str
    direction: str
    opened_at: datetime
    realized_pl: float
    took_trade: bool = True
    alert_id: Optional[int] = None
    closed_at: Optional[datetime] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    quantity: Optional[float] = None
    confidence: Optional[int] = None
    market_condition: str = "unknown"
    notes: str = ""
    emotional_state: str = ""
    mistake_tags: Optional[list] = None


@dataclass
class Recommendation:
    title: str
    rationale: str
    proposed_change: str
    metric: str
    before_value: Optional[float] = None
    after_value: Optional[float] = None
    sample_size: int = 0
    evidence_quality: str = "insufficient"
    overfitting_risk: str = "unknown"
    status: str = "pending_review"
    created_at: datetime = field(default_factory=utc_now)
