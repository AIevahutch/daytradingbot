from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional

from trading_bot.models import SetupSignal, utc_now
from trading_bot.replay import _outcome_metrics_for_setup
from trading_bot.signal_sources import (
    CARTER_SIGNAL_SOURCE,
    FAILED_AUCTION_TRAP_SIGNAL_SOURCE,
    LIVE_CARTER_PAPER_SOURCE,
    LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE,
)
from trading_bot.storage import SQLiteStore


CURRENT_CORE_SETUP_TYPE = "Liquidity sweep reversal"
CURRENT_CORE_TIMEFRAMES = {"15m", "30m"}
CARTER_PUT_DIRECTION = "SHORT"


def refresh_live_100_outcomes(
    store: SQLiteStore,
    excluded_setup_types: Optional[Iterable[str]] = None,
) -> Dict[str, int]:
    return refresh_live_source_outcomes(
        store,
        lambda store_obj: list_current_live_100_paper_events(
            store_obj,
            excluded_setup_types,
        ),
    )


def refresh_live_carter_outcomes(store: SQLiteStore) -> Dict[str, int]:
    return refresh_live_source_outcomes(store, list_live_carter_paper_events)


def refresh_live_carter_put_outcomes(store: SQLiteStore) -> Dict[str, int]:
    return refresh_live_source_outcomes(store, list_live_carter_put_paper_events)


def refresh_live_failed_auction_trap_outcomes(store: SQLiteStore) -> Dict[str, int]:
    return refresh_live_source_outcomes(store, list_live_failed_auction_trap_paper_events)


def refresh_live_source_outcomes(
    store: SQLiteStore, list_events: Callable[[SQLiteStore], List[Dict]]
) -> Dict[str, int]:
    events = list_events(store)
    updated = 0
    for event in events:
        metadata = _metadata(event)
        setup = _setup_from_event(event, metadata)
        if setup is None:
            continue
        event_time = datetime.fromisoformat(event["event_time"])
        future = [
            candle
            for candle in store.candles_between(setup.symbol, "1m", event_time, utc_now())
            if candle.timestamp > event_time
        ]
        if not future:
            continue
        managed_setup, management_metadata = _one_r_managed_setup(setup)
        outcome, r_multiple, path_metrics = _outcome_metrics_for_setup(
            managed_setup,
            future,
        )
        merged_metadata = {
            **metadata,
            **management_metadata,
            "path_metrics": path_metrics,
            "evaluated_at": utc_now().replace(microsecond=0).isoformat(),
            "latest_1m_candle_at": future[-1].timestamp.isoformat(),
        }
        if (
            outcome != event.get("outcome")
            or r_multiple != event.get("r_multiple")
            or metadata.get("path_metrics") != path_metrics
        ):
            update_paper_event_outcome(
                store,
                int(event["id"]),
                outcome,
                r_multiple,
                merged_metadata,
            )
            updated += 1
    summary = live_100_summary(list_events(store))
    summary["updated"] = updated
    return summary


def list_live_100_paper_events(store: SQLiteStore, limit: int = 500) -> List[Dict]:
    if hasattr(store, "list_live_100_paper_events"):
        return store.list_live_100_paper_events(limit)
    with store.connect() as conn:
        rows = conn.execute(
            """
            select pe.*, pr.source, pr.start_date, pr.end_date
            from paper_events pe
            join paper_runs pr on pr.id = pe.run_id
            where pr.source = 'live_100_alerts'
              and pe.event_type = 'alerted'
              and pe.confidence = 100
              and json_extract(pe.metadata_json, '$.mode') = 'live_100_alert'
            order by pe.event_time desc, pe.id desc
            limit ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_current_live_100_paper_events(
    store: SQLiteStore,
    excluded_setup_types: Optional[Iterable[str]] = None,
    limit: int = 500,
) -> List[Dict]:
    excluded = {str(setup_type) for setup_type in excluded_setup_types or []}
    events = list_live_100_paper_events(store, limit)
    return [
        event
        for event in events
        if is_current_core_paper_event(event)
        and str(event.get("setup_type") or "") not in excluded
    ]


def is_current_core_paper_event(event: Dict) -> bool:
    metadata = _metadata(event)
    return (
        str(event.get("setup_type") or "") == CURRENT_CORE_SETUP_TYPE
        and str(metadata.get("timeframe") or "") in CURRENT_CORE_TIMEFRAMES
    )


def is_carter_put_paper_event(event: Dict) -> bool:
    return str(event.get("direction") or "").upper() == CARTER_PUT_DIRECTION


def list_live_carter_put_paper_events(
    store: SQLiteStore, limit: int = 500
) -> List[Dict]:
    return [
        event
        for event in list_live_carter_paper_events(store, limit)
        if is_carter_put_paper_event(event)
    ]


def list_live_carter_paper_events(store: SQLiteStore, limit: int = 500) -> List[Dict]:
    if hasattr(store, "list_live_source_paper_events"):
        return store.list_live_source_paper_events(
            CARTER_SIGNAL_SOURCE,
            LIVE_CARTER_PAPER_SOURCE,
            limit,
        )
    return []


def list_live_failed_auction_trap_paper_events(
    store: SQLiteStore, limit: int = 500
) -> List[Dict]:
    if hasattr(store, "list_live_source_paper_events"):
        return store.list_live_source_paper_events(
            FAILED_AUCTION_TRAP_SIGNAL_SOURCE,
            LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE,
            limit,
        )
    return []


def update_paper_event_outcome(
    store: SQLiteStore,
    event_id: int,
    outcome: str,
    r_multiple: Optional[float],
    metadata: Dict,
    notes: Optional[str] = None,
) -> None:
    if hasattr(store, "update_paper_event_outcome"):
        store.update_paper_event_outcome(event_id, outcome, r_multiple, metadata, notes)
        return
    fields = "outcome = ?, r_multiple = ?, metadata_json = ?"
    params = [outcome, r_multiple, json.dumps(metadata)]
    if notes is not None:
        fields += ", notes = ?"
        params.append(notes)
    params.append(event_id)
    with store.connect() as conn:
        conn.execute(
            f"""
            update paper_events
            set {fields}
            where id = ?
            """,
            params,
        )


def live_100_summary(events: List[Dict]) -> Dict[str, int]:
    wins = [event for event in events if event.get("outcome") == "win"]
    losses = [event for event in events if event.get("outcome") == "loss"]
    open_events = [event for event in events if event.get("outcome") == "open"]
    not_triggered = [event for event in events if event.get("outcome") == "not_triggered"]
    return {
        "alerted": len(events),
        "wins": len(wins),
        "losses": len(losses),
        "open": len(open_events),
        "not_triggered": len(not_triggered),
        "closed": len(wins) + len(losses),
    }


def _metadata(event: Dict) -> Dict:
    try:
        return json.loads(event.get("metadata_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _one_r_managed_setup(setup: SetupSignal) -> tuple:
    entry_mid = (setup.entry_low + setup.entry_high) / 2
    risk = abs(entry_mid - setup.stop_loss)
    if risk <= 0:
        return setup, {"paper_management": "original_target"}
    if setup.direction == "SHORT":
        paper_target = entry_mid - risk
    else:
        paper_target = entry_mid + risk
    managed = SetupSignal(
        symbol=setup.symbol,
        setup_type=setup.setup_type,
        direction=setup.direction,
        timeframe=setup.timeframe,
        created_at=setup.created_at,
        entry_low=setup.entry_low,
        entry_high=setup.entry_high,
        stop_loss=setup.stop_loss,
        target1=paper_target,
        target2=setup.target2,
        invalidation=setup.invalidation,
        confidence=setup.confidence,
        risk_reward=1.0,
        reasoning=setup.reasoning,
        avoid_if=setup.avoid_if,
        market_condition=setup.market_condition,
        status=setup.status,
        features=setup.features,
    )
    return managed, {
        "paper_management": "one_r",
        "paper_target1": round(paper_target, 4),
        "original_target1": setup.target1,
    }


def _setup_from_event(event: Dict, metadata: Dict) -> Optional[SetupSignal]:
    try:
        event_time = datetime.fromisoformat(event["event_time"])
        return SetupSignal(
            symbol=event["symbol"],
            setup_type=event.get("setup_type") or "100/100 alert",
            direction=event.get("direction") or "LONG",
            timeframe=metadata.get("timeframe") or "unknown",
            created_at=event_time,
            entry_low=float(event["entry_low"]),
            entry_high=float(event["entry_high"]),
            stop_loss=float(event["stop_loss"]),
            target1=float(event["target1"]),
            target2=float(metadata.get("target2") or event["target1"]),
            invalidation=float(metadata.get("invalidation") or event["stop_loss"]),
            confidence=int(event.get("confidence") or 100),
            risk_reward=float(event.get("risk_reward") or 0),
            reasoning="Live paper evaluation for a 100/100 alert.",
            avoid_if="",
            market_condition=metadata.get("market_condition") or "unknown",
            status="alert_ready",
            features=metadata.get("features") or {},
        )
    except (TypeError, ValueError, KeyError):
        return None
