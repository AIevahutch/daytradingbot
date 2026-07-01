from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional

from trading_bot.day_trade_contract import (
    DAY_TRADE_OUTCOME,
    candles_through_day_trade_expiry,
    mark_expired_day_trade,
    tighten_day_trade_signal,
)
from trading_bot.models import SetupSignal, utc_now
from trading_bot.replay import _outcome_metrics_for_setup
from trading_bot.signal_sources import (
    CARTER_SIGNAL_SOURCE,
    FAILED_AUCTION_TRAP_SIGNAL_SOURCE,
    FAILED_AUCTION_TRAP_SOURCE_LABEL,
    FAST_MOMENTUM_SIGNAL_SOURCE,
    FAST_MOMENTUM_SOURCE_LABEL,
    HIGH_POTENTIAL_LIQUIDITY_SWEEP_SIGNAL_SOURCE,
    HIGH_POTENTIAL_LIQUIDITY_SWEEP_SOURCE_LABEL,
    LIVE_CARTER_PAPER_SOURCE,
    LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE,
    LIVE_FAST_MOMENTUM_PAPER_SOURCE,
    LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
)
from trading_bot.storage import SQLiteStore


logger = logging.getLogger(__name__)
CURRENT_CORE_SETUP_TYPE = "Liquidity sweep reversal"
CURRENT_CORE_TIMEFRAMES = {"15m", "30m"}
CARTER_PUT_DIRECTION = "SHORT"
EXPERIMENTAL_LANE_CONFIGS = (
    {
        "paper_source": LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE,
        "signal_source": FAILED_AUCTION_TRAP_SIGNAL_SOURCE,
        "source_label": FAILED_AUCTION_TRAP_SOURCE_LABEL,
    },
    {
        "paper_source": LIVE_FAST_MOMENTUM_PAPER_SOURCE,
        "signal_source": FAST_MOMENTUM_SIGNAL_SOURCE,
        "source_label": FAST_MOMENTUM_SOURCE_LABEL,
    },
    {
        "paper_source": LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
        "signal_source": HIGH_POTENTIAL_LIQUIDITY_SWEEP_SIGNAL_SOURCE,
        "source_label": HIGH_POTENTIAL_LIQUIDITY_SWEEP_SOURCE_LABEL,
    },
)
GRADUATION_MIN_CLOSED_SIGNALS = 25
GRADUATION_MIN_WIN_RATE = 80.0
GRADUATION_MIN_PROFIT_FACTOR = 2.0
GRADUATION_MIN_EXPECTANCY_R = 0.40
GRADUATION_MIN_TRADING_DAYS = 3


def refresh_live_100_outcomes(
    store: SQLiteStore,
    excluded_setup_types: Optional[Iterable[str]] = None,
    day_trade_config: Optional[Dict] = None,
) -> Dict[str, int]:
    return refresh_live_source_outcomes(
        store,
        lambda store_obj: list_current_live_100_paper_events(
            store_obj,
            excluded_setup_types,
        ),
        day_trade_config=day_trade_config,
    )


def refresh_live_carter_outcomes(store: SQLiteStore) -> Dict[str, int]:
    return refresh_live_source_outcomes(store, list_live_carter_paper_events)


def refresh_live_carter_put_outcomes(store: SQLiteStore) -> Dict[str, int]:
    return refresh_live_source_outcomes(store, list_live_carter_put_paper_events)


def refresh_live_failed_auction_trap_outcomes(store: SQLiteStore) -> Dict[str, int]:
    return refresh_live_source_outcomes(store, list_live_failed_auction_trap_paper_events)


def refresh_live_fast_momentum_outcomes(store: SQLiteStore) -> Dict[str, int]:
    return refresh_live_source_outcomes(
        store,
        lambda store_obj: list_live_experimental_lane_paper_events(
            store_obj,
            LIVE_FAST_MOMENTUM_PAPER_SOURCE,
        ),
    )


def refresh_live_high_potential_liquidity_sweep_outcomes(
    store: SQLiteStore,
) -> Dict[str, int]:
    return refresh_live_source_outcomes(
        store,
        lambda store_obj: list_live_experimental_lane_paper_events(
            store_obj,
            LIVE_HIGH_POTENTIAL_LIQUIDITY_SWEEP_PAPER_SOURCE,
        ),
    )


def current_live_100_snapshot(
    store: SQLiteStore,
    excluded_setup_types: Optional[Iterable[str]] = None,
) -> tuple[Dict[str, int], List[Dict]]:
    events = list_current_live_100_paper_events(store, excluded_setup_types)
    return live_100_summary(events), events


def current_carter_put_snapshot(store: SQLiteStore) -> tuple[Dict[str, int], List[Dict]]:
    events = list_live_carter_put_paper_events(store)
    return live_100_summary(events), events


def current_failed_auction_trap_snapshot(store: SQLiteStore) -> tuple[Dict[str, int], List[Dict]]:
    events = list_live_failed_auction_trap_paper_events(store)
    return live_100_summary(events), events


def refresh_all_live_outcomes(
    store: SQLiteStore,
    excluded_setup_types: Optional[Iterable[str]] = None,
    day_trade_config: Optional[Dict] = None,
) -> Dict[str, Dict]:
    refreshers = {
        "core": lambda: refresh_live_100_outcomes(
            store,
            excluded_setup_types,
            day_trade_config=day_trade_config,
        ),
        "carter_put": lambda: refresh_live_carter_put_outcomes(store),
        "failed_auction_trap": lambda: refresh_live_failed_auction_trap_outcomes(store),
        "fast_momentum": lambda: refresh_live_fast_momentum_outcomes(store),
        "high_potential_liquidity_sweep": lambda: refresh_live_high_potential_liquidity_sweep_outcomes(
            store
        ),
    }
    results: Dict[str, Dict] = {}
    for lane, refresh in refreshers.items():
        try:
            results[lane] = refresh()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            logger.warning("Paper outcome refresh skipped for %s: database is locked", lane)
            results[lane] = {"updated": 0, "error": "database_locked"}
    return results


def refresh_live_source_outcomes(
    store: SQLiteStore,
    list_events: Callable[[SQLiteStore], List[Dict]],
    day_trade_config: Optional[Dict] = None,
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
        tighten_day_trade_signal(setup, day_trade_config)
        managed_setup, management_metadata = _one_r_managed_setup(setup)
        day_trade_future = candles_through_day_trade_expiry(
            future,
            event_time,
            day_trade_config,
        )
        if not day_trade_future:
            day_trade_future = future
        outcome, r_multiple, path_metrics = _outcome_metrics_for_setup(
            managed_setup,
            day_trade_future,
        )
        if outcome == "open" and future[-1].timestamp > day_trade_future[-1].timestamp:
            outcome = DAY_TRADE_OUTCOME
            r_multiple = 0.0
            path_metrics = mark_expired_day_trade(
                path_metrics,
                event_time,
                day_trade_config,
            )
        if _has_existing_management_win(store, event, metadata):
            outcome = "win"
            r_multiple = 1.0
            path_metrics = {
                **path_metrics,
                "resolution": "telegram_management_alert",
                "management_alert_override": True,
                "tactical_outcome": "win",
                "tactical_r_multiple": 1.0,
            }
        merged_metadata = {
            **metadata,
            **management_metadata,
            "day_trade_adjustment": setup.features.get("day_trade_adjustment"),
            "day_trade_contract": setup.features.get("day_trade_contract"),
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


def list_live_experimental_lane_paper_events(
    store: SQLiteStore,
    paper_source: str,
    limit: int = 500,
) -> List[Dict]:
    config = _experimental_lane_config(paper_source)
    if config and hasattr(store, "list_live_source_paper_events"):
        return store.list_live_source_paper_events(
            str(config["signal_source"]),
            str(config["paper_source"]),
            limit,
        )
    return []


def experimental_lane_summaries(
    store: SQLiteStore,
    lane_configs: Iterable[Dict] = EXPERIMENTAL_LANE_CONFIGS,
) -> List[Dict]:
    summaries = []
    for config in lane_configs:
        events = list_live_experimental_lane_paper_events(
            store,
            str(config["paper_source"]),
        )
        summaries.append(_experimental_lane_summary(config, events))
    return summaries


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
    expired = [event for event in events if event.get("outcome") == DAY_TRADE_OUTCOME]
    open_events = [event for event in events if event.get("outcome") == "open"]
    not_triggered = [event for event in events if event.get("outcome") == "not_triggered"]
    return {
        "alerted": len(events),
        "wins": len(wins),
        "losses": len(losses),
        "expired_daytrade": len(expired),
        "open": len(open_events),
        "not_triggered": len(not_triggered),
        "closed": len(wins) + len(losses) + len(expired),
    }


def _experimental_lane_config(paper_source: str) -> Optional[Dict]:
    for config in EXPERIMENTAL_LANE_CONFIGS:
        if config["paper_source"] == paper_source:
            return config
    return None


def _experimental_lane_summary(config: Dict, events: List[Dict]) -> Dict:
    open_events = [event for event in events if event.get("outcome") == "open"]
    closed_events = [
        event
        for event in events
        if event.get("outcome") in {"win", "loss", "breakeven", DAY_TRADE_OUTCOME}
    ]
    wins = [
        event
        for event in closed_events
        if float(event.get("r_multiple") or 0) > 0
    ]
    losses = [
        event
        for event in closed_events
        if float(event.get("r_multiple") or 0) < 0
    ]
    not_triggered = [
        event for event in events if event.get("outcome") == "not_triggered"
    ]
    total_r = round(
        sum(float(event.get("r_multiple") or 0) for event in closed_events),
        2,
    )
    gross_win = sum(float(event.get("r_multiple") or 0) for event in wins)
    gross_loss = abs(sum(float(event.get("r_multiple") or 0) for event in losses))
    win_rate = round(len(wins) / len(closed_events) * 100, 2) if closed_events else 0.0
    profit_factor = (
        round(gross_win / gross_loss, 2)
        if gross_loss
        else (float("inf") if gross_win else 0.0)
    )
    expectancy_r = round(total_r / len(closed_events), 2) if closed_events else 0.0
    trading_days = {
        str(event.get("event_time") or "")[:10]
        for event in closed_events
        if event.get("event_time")
    }
    gates = {
        "closed_signals": len(closed_events) >= GRADUATION_MIN_CLOSED_SIGNALS,
        "win_rate": win_rate >= GRADUATION_MIN_WIN_RATE,
        "profit_factor": profit_factor >= GRADUATION_MIN_PROFIT_FACTOR,
        "expectancy_r": expectancy_r >= GRADUATION_MIN_EXPECTANCY_R,
        "trading_days": len(trading_days) >= GRADUATION_MIN_TRADING_DAYS,
    }
    eligible = bool(closed_events) and all(gates.values())
    return {
        "paper_source": config["paper_source"],
        "signal_source": config["signal_source"],
        "source_label": config["source_label"],
        "total_signals": len(events),
        "open_signals": len(open_events),
        "closed_signals": len(closed_events),
        "not_triggered": len(not_triggered),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_r": total_r,
        "profit_factor": profit_factor,
        "expectancy_r": expectancy_r,
        "trading_days": len(trading_days),
        "graduation_status": "Eligible for Eva review"
        if eligible
        else "Collecting evidence",
        "graduation_gates": gates,
    }


def _has_existing_management_win(
    store: SQLiteStore,
    event: Dict,
    metadata: Dict,
) -> bool:
    if not hasattr(store, "has_tactical_exit_alert_for_setup"):
        return False
    setup_ids = [
        metadata.get("original_core_setup_id"),
        metadata.get("setup_id"),
    ]
    for raw_setup_id in setup_ids:
        try:
            setup_id = int(raw_setup_id)
        except (TypeError, ValueError):
            continue
        if store.has_tactical_exit_alert_for_setup(setup_id):
            return True
    return False


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
