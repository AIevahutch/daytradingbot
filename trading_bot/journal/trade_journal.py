from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from trading_bot.models import Trade
from trading_bot.storage import SQLiteStore


class TradeJournal:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def add_trade(
        self,
        symbol: str,
        setup_type: str,
        direction: str,
        realized_pl: float,
        opened_at: datetime = None,
        closed_at: Optional[datetime] = None,
        took_trade: bool = True,
        alert_id: Optional[int] = None,
        entry_price: Optional[float] = None,
        exit_price: Optional[float] = None,
        quantity: Optional[float] = None,
        confidence: Optional[int] = None,
        market_condition: str = "unknown",
        notes: str = "",
        emotional_state: str = "",
        mistake_tags: Optional[List[str]] = None,
    ) -> int:
        trade = Trade(
            alert_id=alert_id,
            symbol=symbol,
            setup_type=setup_type,
            direction=direction,
            opened_at=opened_at or datetime.utcnow().replace(microsecond=0),
            closed_at=closed_at,
            took_trade=took_trade,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            realized_pl=realized_pl,
            confidence=confidence,
            market_condition=market_condition,
            notes=notes,
            emotional_state=emotional_state,
            mistake_tags=mistake_tags or [],
        )
        return self.store.insert_trade(trade)

    def add_partial_exit(
        self,
        trade_id: int,
        price: float,
        quantity: float,
        realized_pl: float,
        exited_at: datetime = None,
        notes: str = "",
    ) -> int:
        return self.store.insert_partial_exit(
            trade_id,
            exited_at or datetime.utcnow().replace(microsecond=0),
            price,
            quantity,
            realized_pl,
            notes,
        )

    def add_note(
        self,
        note: str,
        trade_id: Optional[int] = None,
        symbol: Optional[str] = None,
        emotional_state: str = "",
        tags: Optional[List[str]] = None,
    ) -> int:
        return self.store.insert_journal_note(note, trade_id, symbol, emotional_state, tags or [])

