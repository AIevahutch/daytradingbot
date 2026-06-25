from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from trading_bot.models import Candle, Level, Recommendation, SetupSignal, Trade, utc_now
from trading_bot.research.models import ResearchBrief
from trading_bot.signal_sources import (
    CORE_SIGNAL_SOURCE,
    CORE_SOURCE_LABEL,
    FEATURE_ALERT_SOURCE,
    FEATURE_SOURCE_LABEL,
)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _valid_candle(candle: Candle) -> bool:
    values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
    try:
        return all(math.isfinite(float(value)) for value in values)
    except (TypeError, ValueError):
        return False


def _paper_path_metrics(row: Dict) -> Dict[str, Optional[float]]:
    try:
        metadata = json.loads(row.get("metadata_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    path_metrics = metadata.get("path_metrics") or {}
    merged = {**path_metrics, **metadata}
    result: Dict[str, Optional[float]] = {}
    for key in ("mfe_r", "mae_r"):
        value = merged.get(key)
        if value is None:
            result[key] = None
            continue
        try:
            result[key] = float(value)
        except (TypeError, ValueError):
            result[key] = None
    result["tactical_outcome"] = merged.get("tactical_outcome")
    tactical_r = merged.get("tactical_r_multiple")
    if tactical_r is None:
        result["tactical_r_multiple"] = None
    else:
        try:
            result["tactical_r_multiple"] = float(tactical_r)
        except (TypeError, ValueError):
            result["tactical_r_multiple"] = None
    return result


def _paper_metadata(row: Dict) -> Dict:
    try:
        return json.loads(row.get("metadata_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _paper_signal_source(row: Dict) -> str:
    metadata = _paper_metadata(row)
    return str(
        metadata.get("signal_source")
        or metadata.get(FEATURE_ALERT_SOURCE)
        or CORE_SIGNAL_SOURCE
    )


def _paper_source_label(row: Dict) -> str:
    metadata = _paper_metadata(row)
    return str(metadata.get(FEATURE_SOURCE_LABEL) or CORE_SOURCE_LABEL)


def _paper_dimension(row: Dict, dimension: str) -> str:
    metadata = _paper_metadata(row)
    if dimension == "market_regime":
        return str(
            metadata.get("market_regime")
            or metadata.get("market_condition")
            or "unknown"
        )
    if dimension == "timeframe":
        return str(metadata.get("timeframe") or "unknown")
    return str(row.get(dimension) or "unknown")


def _alert_source_clause(source_key: str) -> str:
    source_expr = f"json_extract(s.features_json, '$.{FEATURE_ALERT_SOURCE}')"
    if source_key == CORE_SIGNAL_SOURCE:
        return f"({source_expr} = ? or {source_expr} is null)"
    return f"{source_expr} = ?"


def _max_drawdown_r(rows: List[Dict]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for row in rows:
        equity += float(row.get("r_multiple") or 0)
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return round(max_drawdown, 2)


def _paper_group_summary(rows: List[Dict], key_fn) -> Dict[str, Dict]:
    groups: Dict[str, List[Dict]] = {}
    for row in rows:
        groups.setdefault(str(key_fn(row) or "unknown"), []).append(row)
    return {key: _paper_group_metrics(group) for key, group in sorted(groups.items())}


def _paper_group_metrics(rows: List[Dict]) -> Dict:
    wins = [row for row in rows if float(row.get("r_multiple") or 0) > 0]
    losses = [row for row in rows if float(row.get("r_multiple") or 0) < 0]
    total_r = sum(float(row.get("r_multiple") or 0) for row in rows)
    gross_win = sum(float(row.get("r_multiple") or 0) for row in wins)
    gross_loss = abs(sum(float(row.get("r_multiple") or 0) for row in losses))
    avg_winner = gross_win / len(wins) if wins else 0.0
    avg_loser = (
        sum(float(row.get("r_multiple") or 0) for row in losses) / len(losses)
        if losses
        else 0.0
    )
    return {
        "sample_size": len(rows),
        "win_rate": round(len(wins) / len(rows) * 100, 2) if rows else 0.0,
        "total_r": round(total_r, 2),
        "expectancy_r": round(total_r / len(rows), 2) if rows else 0.0,
        "profit_factor": (
            round(gross_win / gross_loss, 2)
            if gross_loss
            else (float("inf") if gross_win else 0.0)
        ),
        "avg_winner_r": round(avg_winner, 2),
        "avg_loser_r": round(avg_loser, 2),
        "max_drawdown_r": _max_drawdown_r(rows),
    }


class SQLiteStore:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(str(self.database_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                create table if not exists candles (
                    symbol text not null,
                    timeframe text not null,
                    timestamp text not null,
                    open real not null,
                    high real not null,
                    low real not null,
                    close real not null,
                    volume real not null,
                    source text not null,
                    primary key (symbol, timeframe, timestamp)
                );

                create table if not exists levels (
                    id integer primary key autoincrement,
                    symbol text not null,
                    name text not null,
                    price real not null,
                    timeframe text not null,
                    session_date text not null,
                    created_at text not null,
                    metadata_json text not null
                );

                create table if not exists setups (
                    id integer primary key autoincrement,
                    created_at text not null,
                    symbol text not null,
                    setup_type text not null,
                    direction text not null,
                    timeframe text not null,
                    entry_low real not null,
                    entry_high real not null,
                    stop_loss real not null,
                    target1 real not null,
                    target2 real not null,
                    invalidation real not null,
                    confidence integer not null,
                    risk_reward real not null,
                    reasoning text not null,
                    avoid_if text not null,
                    market_condition text not null,
                    status text not null,
                    features_json text not null
                );

                create table if not exists alerts (
                    id integer primary key autoincrement,
                    setup_id integer,
                    created_at text not null,
                    symbol text not null,
                    setup_type text not null,
                    direction text not null,
                    confidence integer not null,
                    message text not null,
                    delivered integer not null,
                    delivery_error text,
                    foreign key (setup_id) references setups(id)
                );

                create table if not exists trades (
                    id integer primary key autoincrement,
                    alert_id integer,
                    symbol text not null,
                    setup_type text not null,
                    direction text not null,
                    opened_at text not null,
                    closed_at text,
                    took_trade integer not null,
                    entry_price real,
                    exit_price real,
                    quantity real,
                    realized_pl real not null,
                    confidence integer,
                    market_condition text not null,
                    notes text not null,
                    emotional_state text not null,
                    mistake_tags_json text not null,
                    foreign key (alert_id) references alerts(id)
                );

                create table if not exists partial_exits (
                    id integer primary key autoincrement,
                    trade_id integer not null,
                    exited_at text not null,
                    price real not null,
                    quantity real not null,
                    realized_pl real not null,
                    notes text not null,
                    foreign key (trade_id) references trades(id)
                );

                create table if not exists journal_notes (
                    id integer primary key autoincrement,
                    trade_id integer,
                    created_at text not null,
                    symbol text,
                    note text not null,
                    emotional_state text,
                    tags_json text not null,
                    foreign key (trade_id) references trades(id)
                );

                create table if not exists trading_rules (
                    id integer primary key autoincrement,
                    created_at text not null,
                    updated_at text not null,
                    rule_text text not null,
                    category text not null,
                    status text not null,
                    commandment_order integer,
                    notes text not null
                );

                create table if not exists daily_market_reviews (
                    id integer primary key autoincrement,
                    session_date text not null unique,
                    market_condition text not null,
                    no_trade_reason text,
                    notes text not null,
                    created_at text not null
                );

                create table if not exists research_briefs (
                    id integer primary key autoincrement,
                    session_date text not null,
                    phase text not null,
                    created_at text not null,
                    risk_score integer not null,
                    bias text not null,
                    trade_today integer not null,
                    decision text not null,
                    summary text not null,
                    drivers_json text not null,
                    hard_blocks_json text not null,
                    source_status_json text not null,
                    evidence_json text not null,
                    openai_status text not null default 'not_requested',
                    openai_model text,
                    email_status text not null default 'not_requested',
                    email_error text,
                    email_sent_at text,
                    unique(session_date, phase)
                );

                create table if not exists research_evidence (
                    id integer primary key autoincrement,
                    brief_id integer not null,
                    source text not null,
                    status text not null,
                    category text not null,
                    title text not null,
                    detail text not null,
                    impact integer not null,
                    bias text not null,
                    url text not null,
                    occurred_at text,
                    metadata_json text not null,
                    foreign key (brief_id) references research_briefs(id)
                );

                create table if not exists research_email_attempts (
                    id integer primary key autoincrement,
                    brief_id integer,
                    attempted_at text not null,
                    to_address text not null,
                    subject text not null,
                    delivered integer not null,
                    error text,
                    provider text not null,
                    foreign key (brief_id) references research_briefs(id)
                );

                create table if not exists strategy_recommendations (
                    id integer primary key autoincrement,
                    created_at text not null,
                    title text not null,
                    rationale text not null,
                    proposed_change text not null,
                    metric text not null,
                    before_value real,
                    after_value real,
                    sample_size integer not null default 0,
                    evidence_quality text not null default 'insufficient',
                    overfitting_risk text not null default 'unknown',
                    status text not null
                );

                create table if not exists approved_rule_changes (
                    id integer primary key autoincrement,
                    recommendation_id integer,
                    approved_at text not null,
                    approved_by text not null,
                    change_summary text not null,
                    applied integer not null default 0,
                    foreign key (recommendation_id) references strategy_recommendations(id)
                );

                create table if not exists score_breakdowns (
                    id integer primary key autoincrement,
                    setup_id integer,
                    created_at text not null,
                    symbol text not null,
                    setup_type text not null,
                    total_score integer not null,
                    threshold integer not null,
                    status text not null,
                    positives_json text not null,
                    penalties_json text not null,
                    hard_blocks_json text not null,
                    breakdown_json text not null,
                    foreign key (setup_id) references setups(id)
                );

                create table if not exists telegram_delivery_attempts (
                    id integer primary key autoincrement,
                    alert_id integer,
                    setup_id integer,
                    attempted_at text not null,
                    symbol text not null,
                    attempt_number integer not null,
                    delivered integer not null,
                    error text,
                    message text not null,
                    foreign key (alert_id) references alerts(id),
                    foreign key (setup_id) references setups(id)
                );

                create table if not exists alert_reviews (
                    id integer primary key autoincrement,
                    alert_id integer not null unique,
                    reviewed_at text not null,
                    review_status text not null,
                    outcome text not null,
                    r_multiple real,
                    notes text not null,
                    emotional_state text not null,
                    mistake_tags_json text not null,
                    foreign key (alert_id) references alerts(id)
                );

                create table if not exists paper_runs (
                    id integer primary key autoincrement,
                    started_at text not null,
                    completed_at text,
                    source text not null,
                    start_date text not null,
                    end_date text not null,
                    symbols_json text not null,
                    status text not null,
                    summary_json text not null
                );

                create table if not exists paper_events (
                    id integer primary key autoincrement,
                    run_id integer not null,
                    event_time text not null,
                    symbol text not null,
                    event_type text not null,
                    setup_type text,
                    direction text,
                    confidence integer,
                    risk_reward real,
                    entry_low real,
                    entry_high real,
                    stop_loss real,
                    target1 real,
                    outcome text not null,
                    r_multiple real,
                    notes text not null,
                    emotional_state text not null,
                    mistake_tags_json text not null,
                    metadata_json text not null,
                    foreign key (run_id) references paper_runs(id)
                );

                create table if not exists scanner_heartbeats (
                    id integer primary key autoincrement,
                    started_at text not null,
                    completed_at text not null,
                    status text not null,
                    alerts_count integer not null,
                    watch_only_count integer not null,
                    no_trade_count integer not null,
                    errors_count integer not null,
                    summary_json text not null
                );
                """
            )
            self._ensure_columns(
                conn,
                "strategy_recommendations",
                {
                    "sample_size": "integer not null default 0",
                    "evidence_quality": "text not null default 'insufficient'",
                    "overfitting_risk": "text not null default 'unknown'",
                },
            )

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
        existing = {row["name"] for row in conn.execute(f"pragma table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"alter table {table} add column {column} {definition}")

    def upsert_candles(self, candles: Iterable[Candle]) -> int:
        rows = [
            (
                c.symbol,
                c.timeframe,
                _iso(c.timestamp),
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                c.source,
            )
            for c in candles
            if _valid_candle(c)
        ]
        if not rows:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                insert or replace into candles
                (symbol, timeframe, timestamp, open, high, low, close, volume, source)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def latest_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Candle]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select * from candles
                where symbol = ? and timeframe = ?
                order by timestamp desc
                limit ?
                """,
                (symbol, timeframe, limit),
            ).fetchall()
        candles = [
            Candle(
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                timestamp=_dt(row["timestamp"]),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                source=row["source"],
            )
            for row in rows
        ]
        return list(reversed(candles))

    def replace_levels(self, symbol: str, session_date: str, levels: Iterable[Level]) -> None:
        rows = [
            (
                level.symbol,
                level.name,
                level.price,
                level.timeframe,
                level.session_date,
                _iso(level.created_at),
                json.dumps(level.metadata),
            )
            for level in levels
        ]
        with self.connect() as conn:
            conn.execute(
                "delete from levels where symbol = ? and session_date = ?",
                (symbol, session_date),
            )
            conn.executemany(
                """
                insert into levels
                (symbol, name, price, timeframe, session_date, created_at, metadata_json)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_latest_levels(self, symbol: str, limit: int = 30) -> List[Level]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select * from levels
                where symbol = ?
                order by session_date desc, created_at desc, id desc
                limit ?
                """,
                (symbol, limit),
            ).fetchall()
        return [
            Level(
                symbol=row["symbol"],
                name=row["name"],
                price=row["price"],
                timeframe=row["timeframe"],
                session_date=row["session_date"],
                created_at=_dt(row["created_at"]),
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def insert_setup(self, setup: SetupSignal) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into setups
                (created_at, symbol, setup_type, direction, timeframe, entry_low, entry_high,
                 stop_loss, target1, target2, invalidation, confidence, risk_reward, reasoning,
                 avoid_if, market_condition, status, features_json)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _iso(setup.created_at),
                    setup.symbol,
                    setup.setup_type,
                    setup.direction,
                    setup.timeframe,
                    setup.entry_low,
                    setup.entry_high,
                    setup.stop_loss,
                    setup.target1,
                    setup.target2,
                    setup.invalidation,
                    setup.confidence,
                    setup.risk_reward,
                    setup.reasoning,
                    setup.avoid_if,
                    setup.market_condition,
                    setup.status,
                    json.dumps(setup.features),
                ),
            )
            setup_id = int(cur.lastrowid)
            breakdown = dict((setup.features or {}).get("score_breakdown") or {})
            if breakdown:
                conn.execute(
                    """
                    insert into score_breakdowns
                    (setup_id, created_at, symbol, setup_type, total_score, threshold, status,
                     positives_json, penalties_json, hard_blocks_json, breakdown_json)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        setup_id,
                        _iso(setup.created_at),
                        setup.symbol,
                        setup.setup_type,
                        setup.confidence,
                        int(breakdown.get("threshold", 0) or 0),
                        setup.status,
                        json.dumps(breakdown.get("positives", [])),
                        json.dumps(breakdown.get("penalties", [])),
                        json.dumps(breakdown.get("hard_blocks", [])),
                        json.dumps(breakdown),
                    ),
                )
            return setup_id

    def insert_alert(
        self,
        setup_id: Optional[int],
        setup: SetupSignal,
        message: str,
        delivered: bool,
        delivery_error: Optional[str] = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into alerts
                (setup_id, created_at, symbol, setup_type, direction, confidence, message,
                 delivered, delivery_error)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    setup_id,
                    _iso(utc_now()),
                    setup.symbol,
                    setup.setup_type,
                    setup.direction,
                    setup.confidence,
                    message,
                    1 if delivered else 0,
                    delivery_error,
                ),
            )
            return int(cur.lastrowid)

    def has_recent_duplicate_alert(
        self, setup: SetupSignal, duplicate_minutes: int
    ) -> bool:
        return self.has_recent_duplicate_alert_for_source(
            setup,
            duplicate_minutes,
            str((setup.features or {}).get(FEATURE_ALERT_SOURCE) or CORE_SIGNAL_SOURCE),
        )

    def has_recent_duplicate_alert_for_source(
        self, setup: SetupSignal, duplicate_minutes: int, source_key: str
    ) -> bool:
        cutoff = utc_now() - timedelta(minutes=duplicate_minutes)
        source_clause = _alert_source_clause(source_key)
        with self.connect() as conn:
            row = conn.execute(
                f"""
                select alerts.id from alerts
                left join setups s on s.id = alerts.setup_id
                where alerts.symbol = ?
                  and alerts.setup_type = ?
                  and alerts.direction = ?
                  and alerts.created_at >= ?
                  and {source_clause}
                order by alerts.created_at desc
                limit 1
                """,
                (
                    setup.symbol,
                    setup.setup_type,
                    setup.direction,
                    _iso(cutoff),
                    source_key,
                ),
            ).fetchone()
        return row is not None

    def has_recent_symbol_alert(self, symbol: str, cooldown_minutes: int) -> bool:
        return self.has_recent_symbol_alert_for_source(
            symbol,
            cooldown_minutes,
            CORE_SIGNAL_SOURCE,
        )

    def has_recent_symbol_alert_for_source(
        self, symbol: str, cooldown_minutes: int, source_key: str
    ) -> bool:
        cutoff = utc_now() - timedelta(minutes=cooldown_minutes)
        source_clause = _alert_source_clause(source_key)
        with self.connect() as conn:
            row = conn.execute(
                f"""
                select alerts.id from alerts
                left join setups s on s.id = alerts.setup_id
                where alerts.symbol = ?
                  and alerts.setup_type != 'Suggested sell/partial'
                  and alerts.created_at >= ?
                  and {source_clause}
                order by alerts.created_at desc
                limit 1
                """,
                (symbol, _iso(cutoff), source_key),
            ).fetchone()
        return row is not None

    def alert_count_today(self, symbol: str) -> int:
        return self.alert_count_today_for_source(symbol, CORE_SIGNAL_SOURCE)

    def alert_count_today_for_source(self, symbol: str, source_key: str) -> int:
        today = utc_now().date().isoformat()
        source_clause = _alert_source_clause(source_key)
        with self.connect() as conn:
            row = conn.execute(
                f"""
                select count(*) as count from alerts
                left join setups s on s.id = alerts.setup_id
                where alerts.symbol = ?
                  and alerts.setup_type != 'Suggested sell/partial'
                  and substr(alerts.created_at, 1, 10) = ?
                  and {source_clause}
                """,
                (symbol, today, source_key),
            ).fetchone()
        return int(row["count"])

    def list_tactical_exit_candidates(self, since: datetime) -> List[Dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select
                    a.id as original_alert_id,
                    a.created_at as original_alert_created_at,
                    s.id as setup_id,
                    s.created_at as setup_created_at,
                    s.symbol,
                    s.setup_type,
                    s.direction,
                    s.timeframe,
                    s.entry_low,
                    s.entry_high,
                    s.stop_loss,
                    s.target1,
                    s.target2,
                    s.invalidation,
                    s.confidence,
                    s.risk_reward,
                    s.reasoning,
                    s.avoid_if,
                    s.market_condition,
                    s.status,
                    s.features_json
                from alerts a
                join setups s on s.id = a.setup_id
                where a.created_at >= ?
                  and a.setup_type = 'Liquidity sweep reversal'
                  and a.delivered = 1
                  and not exists (
                      select 1
                      from alerts exit_alert
                      where exit_alert.setup_id = s.id
                        and exit_alert.setup_type = 'Suggested sell/partial'
                  )
                order by a.created_at asc
                """,
                (_iso(since),),
            ).fetchall()
        return [dict(row) for row in rows]

    def has_tactical_exit_alert_for_setup(self, setup_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                select id from alerts
                where setup_id = ?
                  and setup_type = 'Suggested sell/partial'
                  and delivered = 1
                limit 1
                """,
                (setup_id,),
            ).fetchone()
        return row is not None

    def update_alert_delivery(
        self, alert_id: int, delivered: bool, delivery_error: Optional[str] = None
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                update alerts
                set delivered = ?, delivery_error = ?
                where id = ?
                """,
                (1 if delivered else 0, delivery_error, alert_id),
            )

    def list_failed_alerts(self, limit: int = 50) -> List[Dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select * from alerts
                where delivered = 0
                order by created_at asc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_telegram_attempt(
        self,
        symbol: str,
        message: str,
        delivered: bool,
        attempt_number: int,
        error: Optional[str] = None,
        alert_id: Optional[int] = None,
        setup_id: Optional[int] = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into telegram_delivery_attempts
                (alert_id, setup_id, attempted_at, symbol, attempt_number, delivered, error, message)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    setup_id,
                    _iso(utc_now()),
                    symbol,
                    attempt_number,
                    1 if delivered else 0,
                    error,
                    message,
                ),
            )
            return int(cur.lastrowid)

    def upsert_alert_review(
        self,
        alert_id: int,
        review_status: str,
        outcome: str,
        r_multiple: Optional[float] = None,
        notes: str = "",
        emotional_state: str = "",
        mistake_tags: Optional[List[str]] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into alert_reviews
                (alert_id, reviewed_at, review_status, outcome, r_multiple, notes,
                 emotional_state, mistake_tags_json)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(alert_id) do update set
                    reviewed_at=excluded.reviewed_at,
                    review_status=excluded.review_status,
                    outcome=excluded.outcome,
                    r_multiple=excluded.r_multiple,
                    notes=excluded.notes,
                    emotional_state=excluded.emotional_state,
                    mistake_tags_json=excluded.mistake_tags_json
                """,
                (
                    alert_id,
                    _iso(utc_now()),
                    review_status,
                    outcome,
                    r_multiple,
                    notes,
                    emotional_state,
                    json.dumps(mistake_tags or []),
                ),
            )

    def insert_trade(self, trade: Trade) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into trades
                (alert_id, symbol, setup_type, direction, opened_at, closed_at, took_trade,
                 entry_price, exit_price, quantity, realized_pl, confidence, market_condition,
                 notes, emotional_state, mistake_tags_json)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.alert_id,
                    trade.symbol,
                    trade.setup_type,
                    trade.direction,
                    _iso(trade.opened_at),
                    _iso(trade.closed_at),
                    1 if trade.took_trade else 0,
                    trade.entry_price,
                    trade.exit_price,
                    trade.quantity,
                    trade.realized_pl,
                    trade.confidence,
                    trade.market_condition,
                    trade.notes,
                    trade.emotional_state,
                    json.dumps(trade.mistake_tags or []),
                ),
            )
            return int(cur.lastrowid)

    def update_trade(
        self,
        trade_id: int,
        *,
        symbol: str,
        setup_type: str,
        direction: str,
        opened_at: datetime,
        closed_at: Optional[datetime],
        took_trade: bool,
        entry_price: Optional[float],
        exit_price: Optional[float],
        quantity: Optional[float],
        realized_pl: float,
        confidence: Optional[int],
        market_condition: str,
        notes: str,
        emotional_state: str,
        mistake_tags: Optional[List[str]] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                update trades
                set symbol = ?,
                    setup_type = ?,
                    direction = ?,
                    opened_at = ?,
                    closed_at = ?,
                    took_trade = ?,
                    entry_price = ?,
                    exit_price = ?,
                    quantity = ?,
                    realized_pl = ?,
                    confidence = ?,
                    market_condition = ?,
                    notes = ?,
                    emotional_state = ?,
                    mistake_tags_json = ?
                where id = ?
                """,
                (
                    symbol,
                    setup_type,
                    direction,
                    _iso(opened_at),
                    _iso(closed_at),
                    1 if took_trade else 0,
                    entry_price,
                    exit_price,
                    quantity,
                    realized_pl,
                    confidence,
                    market_condition,
                    notes,
                    emotional_state,
                    json.dumps(mistake_tags or []),
                    trade_id,
                ),
            )

    def delete_trade(self, trade_id: int) -> bool:
        with self.connect() as conn:
            conn.execute("delete from partial_exits where trade_id = ?", (trade_id,))
            conn.execute("delete from journal_notes where trade_id = ?", (trade_id,))
            cur = conn.execute("delete from trades where id = ?", (trade_id,))
            return cur.rowcount > 0

    def insert_partial_exit(
        self,
        trade_id: int,
        exited_at: datetime,
        price: float,
        quantity: float,
        realized_pl: float,
        notes: str = "",
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into partial_exits
                (trade_id, exited_at, price, quantity, realized_pl, notes)
                values (?, ?, ?, ?, ?, ?)
                """,
                (trade_id, _iso(exited_at), price, quantity, realized_pl, notes),
            )
            return int(cur.lastrowid)

    def insert_journal_note(
        self,
        note: str,
        trade_id: Optional[int] = None,
        symbol: Optional[str] = None,
        emotional_state: str = "",
        tags: Optional[List[str]] = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into journal_notes
                (trade_id, created_at, symbol, note, emotional_state, tags_json)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    _iso(utc_now()),
                    symbol,
                    note,
                    emotional_state,
                    json.dumps(tags or []),
                ),
            )
            return int(cur.lastrowid)

    def upsert_daily_review(
        self,
        session_date: str,
        market_condition: str,
        notes: str,
        no_trade_reason: Optional[str] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into daily_market_reviews
                (session_date, market_condition, no_trade_reason, notes, created_at)
                values (?, ?, ?, ?, ?)
                on conflict(session_date) do update set
                    market_condition=excluded.market_condition,
                    no_trade_reason=excluded.no_trade_reason,
                    notes=excluded.notes
                """,
                (session_date, market_condition, no_trade_reason, notes, _iso(utc_now())),
            )

    def upsert_research_brief(self, brief: ResearchBrief) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into research_briefs
                (session_date, phase, created_at, risk_score, bias, trade_today, decision,
                 summary, drivers_json, hard_blocks_json, source_status_json, evidence_json,
                 openai_status, openai_model, email_status, email_error, email_sent_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(session_date, phase) do update set
                    created_at=excluded.created_at,
                    risk_score=excluded.risk_score,
                    bias=excluded.bias,
                    trade_today=excluded.trade_today,
                    decision=excluded.decision,
                    summary=excluded.summary,
                    drivers_json=excluded.drivers_json,
                    hard_blocks_json=excluded.hard_blocks_json,
                    source_status_json=excluded.source_status_json,
                    evidence_json=excluded.evidence_json,
                    openai_status=excluded.openai_status,
                    openai_model=excluded.openai_model,
                    email_status=excluded.email_status,
                    email_error=excluded.email_error,
                    email_sent_at=excluded.email_sent_at
                """,
                (
                    brief.session_date,
                    brief.phase,
                    _iso(brief.created_at),
                    brief.risk_score,
                    brief.bias,
                    1 if brief.trade_today else 0,
                    brief.decision,
                    brief.summary,
                    json.dumps(brief.drivers),
                    json.dumps(brief.hard_blocks),
                    json.dumps(brief.source_status),
                    json.dumps(brief.evidence),
                    brief.openai_status,
                    brief.openai_model,
                    brief.email_status,
                    brief.email_error,
                    _iso(brief.email_sent_at),
                ),
            )
            row = conn.execute(
                "select id from research_briefs where session_date = ? and phase = ?",
                (brief.session_date, brief.phase),
            ).fetchone()
            brief_id = int(row["id"] if row else cur.lastrowid)
            conn.execute("delete from research_evidence where brief_id = ?", (brief_id,))
            conn.executemany(
                """
                insert into research_evidence
                (brief_id, source, status, category, title, detail, impact, bias, url, occurred_at, metadata_json)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        brief_id,
                        str(item.get("source", "")),
                        str(item.get("status", "")),
                        str(item.get("category", "")),
                        str(item.get("title", "")),
                        str(item.get("detail", "")),
                        int(item.get("impact", 0) or 0),
                        str(item.get("bias", "neutral")),
                        str(item.get("url", "")),
                        item.get("occurred_at"),
                        json.dumps(item.get("metadata", {})),
                    )
                    for item in brief.evidence
                ],
            )
            return brief_id

    def update_research_email_status(
        self,
        brief_id: int,
        email_status: str,
        email_error: Optional[str] = None,
        email_sent_at: Optional[datetime] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                update research_briefs
                set email_status = ?, email_error = ?, email_sent_at = ?
                where id = ?
                """,
                (email_status, email_error, _iso(email_sent_at), brief_id),
            )

    def insert_research_email_attempt(
        self,
        brief_id: Optional[int],
        to_address: str,
        subject: str,
        delivered: bool,
        error: Optional[str] = None,
        provider: str = "gmail_smtp",
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into research_email_attempts
                (brief_id, attempted_at, to_address, subject, delivered, error, provider)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    brief_id,
                    _iso(utc_now()),
                    to_address,
                    subject,
                    1 if delivered else 0,
                    error,
                    provider,
                ),
            )
            return int(cur.lastrowid)

    def latest_research_brief(
        self, session_date: Optional[str] = None, phase: Optional[str] = None
    ) -> Optional[Dict]:
        where = []
        params = []
        if session_date:
            where.append("session_date = ?")
            params.append(session_date)
        if phase:
            where.append("phase = ?")
            params.append(phase)
        clause = f"where {' and '.join(where)}" if where else ""
        with self.connect() as conn:
            row = conn.execute(
                f"""
                select * from research_briefs
                {clause}
                order by created_at desc, id desc
                limit 1
                """,
                params,
            ).fetchone()
        return dict(row) if row else None

    def list_rows(self, table: str, limit: int = 200) -> List[Dict]:
        allowed = {
            "candles",
            "levels",
            "setups",
            "alerts",
            "score_breakdowns",
            "telegram_delivery_attempts",
            "alert_reviews",
            "paper_runs",
            "paper_events",
            "scanner_heartbeats",
            "trades",
            "partial_exits",
            "journal_notes",
            "trading_rules",
            "daily_market_reviews",
            "research_briefs",
            "research_evidence",
            "research_email_attempts",
            "strategy_recommendations",
            "approved_rule_changes",
        }
        if table not in allowed:
            raise ValueError(f"Unsupported table: {table}")
        with self.connect() as conn:
            rows = conn.execute(
                f"select * from {table} order by id desc limit ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def list_trades(self) -> List[Dict]:
        with self.connect() as conn:
            rows = conn.execute("select * from trades order by opened_at asc").fetchall()
        return [dict(row) for row in rows]

    def add_trading_rule(
        self,
        rule_text: str,
        category: str = "trade_rule",
        status: str = "draft",
        commandment_order: Optional[int] = None,
        notes: str = "",
    ) -> int:
        now = utc_now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into trading_rules
                (created_at, updated_at, rule_text, category, status, commandment_order, notes)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _iso(now),
                    _iso(now),
                    rule_text.strip(),
                    category or "trade_rule",
                    status or "draft",
                    commandment_order,
                    notes or "",
                ),
            )
            return int(cur.lastrowid)

    def update_trading_rule(
        self,
        rule_id: int,
        rule_text: str,
        category: str = "trade_rule",
        status: str = "draft",
        commandment_order: Optional[int] = None,
        notes: str = "",
    ) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                """
                update trading_rules
                set updated_at = ?,
                    rule_text = ?,
                    category = ?,
                    status = ?,
                    commandment_order = ?,
                    notes = ?
                where id = ?
                """,
                (
                    _iso(utc_now()),
                    rule_text.strip(),
                    category or "trade_rule",
                    status or "draft",
                    commandment_order,
                    notes or "",
                    rule_id,
                ),
            )
            return cur.rowcount > 0

    def delete_trading_rule(self, rule_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("delete from trading_rules where id = ?", (rule_id,))
            return cur.rowcount > 0

    def list_trading_rules(self) -> List[Dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select * from trading_rules
                order by
                    case when status = 'commandment' then 0 else 1 end,
                    commandment_order is null,
                    commandment_order asc,
                    updated_at desc,
                    id desc
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_alerts(self) -> List[Dict]:
        with self.connect() as conn:
            rows = conn.execute("select * from alerts order by created_at asc").fetchall()
        return [dict(row) for row in rows]

    def candles_between(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> List[Candle]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select * from candles
                where symbol = ?
                  and timeframe = ?
                  and timestamp >= ?
                  and timestamp <= ?
                order by timestamp asc
                """,
                (symbol, timeframe, _iso(start), _iso(end)),
            ).fetchall()
        return [
            Candle(
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                timestamp=_dt(row["timestamp"]),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                source=row["source"],
            )
            for row in rows
        ]

    def latest_candle_status(self) -> List[Dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select symbol, timeframe, max(timestamp) as latest_timestamp, count(*) as count
                from candles
                group by symbol, timeframe
                order by symbol, timeframe
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_scan_heartbeat(
        self, started_at: datetime, completed_at: datetime, status: str, summary: Dict
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into scanner_heartbeats
                (started_at, completed_at, status, alerts_count, watch_only_count,
                 no_trade_count, errors_count, summary_json)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _iso(started_at),
                    _iso(completed_at),
                    status,
                    len(summary.get("alerts", [])),
                    len(summary.get("watch_only", [])),
                    len(summary.get("no_trade", [])),
                    len(summary.get("errors", [])),
                    json.dumps(summary),
                ),
            )
            return int(cur.lastrowid)

    def latest_scan_heartbeat(self) -> Optional[Dict]:
        with self.connect() as conn:
            row = conn.execute(
                "select * from scanner_heartbeats order by id desc limit 1"
            ).fetchone()
        return dict(row) if row else None

    def begin_paper_run(
        self, source: str, start_date: str, end_date: str, symbols: List[str]
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into paper_runs
                (started_at, completed_at, source, start_date, end_date, symbols_json,
                 status, summary_json)
                values (?, null, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _iso(utc_now()),
                    source,
                    start_date,
                    end_date,
                    json.dumps(symbols),
                    "running",
                    "{}",
                ),
            )
            return int(cur.lastrowid)

    def get_or_create_paper_run(
        self, source: str, session_date: str, symbols: List[str]
    ) -> int:
        symbols_json = json.dumps(symbols)
        with self.connect() as conn:
            row = conn.execute(
                """
                select id from paper_runs
                where source = ?
                  and start_date = ?
                  and end_date = ?
                  and symbols_json = ?
                  and status = 'running'
                order by id desc
                limit 1
                """,
                (source, session_date, session_date, symbols_json),
            ).fetchone()
            if row:
                return int(row["id"])
            cur = conn.execute(
                """
                insert into paper_runs
                (started_at, completed_at, source, start_date, end_date, symbols_json,
                 status, summary_json)
                values (?, null, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _iso(utc_now()),
                    source,
                    session_date,
                    session_date,
                    symbols_json,
                    "running",
                    "{}",
                ),
            )
            return int(cur.lastrowid)

    def finish_paper_run(self, run_id: int, status: str, summary: Dict) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                update paper_runs
                set completed_at = ?, status = ?, summary_json = ?
                where id = ?
                """,
                (_iso(utc_now()), status, json.dumps(summary), run_id),
            )

    def insert_paper_event(
        self,
        run_id: int,
        event_time: datetime,
        symbol: str,
        event_type: str,
        outcome: str,
        setup_type: Optional[str] = None,
        direction: Optional[str] = None,
        confidence: Optional[int] = None,
        risk_reward: Optional[float] = None,
        entry_low: Optional[float] = None,
        entry_high: Optional[float] = None,
        stop_loss: Optional[float] = None,
        target1: Optional[float] = None,
        r_multiple: Optional[float] = None,
        notes: str = "",
        emotional_state: str = "",
        mistake_tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into paper_events
                (run_id, event_time, symbol, event_type, setup_type, direction, confidence,
                 risk_reward, entry_low, entry_high, stop_loss, target1, outcome, r_multiple,
                 notes, emotional_state, mistake_tags_json, metadata_json)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    _iso(event_time),
                    symbol,
                    event_type,
                    setup_type,
                    direction,
                    confidence,
                    risk_reward,
                    entry_low,
                    entry_high,
                    stop_loss,
                    target1,
                    outcome,
                    r_multiple,
                    notes,
                    emotional_state,
                    json.dumps(mistake_tags or []),
                    json.dumps(metadata or {}),
                ),
            )
            return int(cur.lastrowid)

    def has_paper_event_for_alert(self, alert_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                select id from paper_events
                where json_extract(metadata_json, '$.alert_id') = ?
                limit 1
                """,
                (alert_id,),
            ).fetchone()
        return row is not None

    def has_source_paper_signal(
        self,
        source_key: str,
        mode: str,
        setup: SetupSignal,
    ) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                select id from paper_events
                where event_time = ?
                  and symbol = ?
                  and setup_type = ?
                  and direction = ?
                  and json_extract(metadata_json, '$.timeframe') = ?
                  and json_extract(metadata_json, '$.mode') = ?
                  and (
                    json_extract(metadata_json, '$.signal_source') = ?
                    or json_extract(metadata_json, '$.alert_source') = ?
                  )
                limit 1
                """,
                (
                    _iso(setup.created_at),
                    setup.symbol,
                    setup.setup_type,
                    setup.direction,
                    setup.timeframe,
                    mode,
                    source_key,
                    source_key,
                ),
            ).fetchone()
        return row is not None

    def insert_live_paper_alert(
        self,
        run_id: int,
        alert_id: int,
        setup_id: int,
        setup: SetupSignal,
    ) -> Optional[int]:
        return self.insert_source_paper_alert(
            run_id=run_id,
            alert_id=alert_id,
            setup_id=setup_id,
            setup=setup,
            mode="live_100_alert",
            source_key=CORE_SIGNAL_SOURCE,
            source_label=CORE_SOURCE_LABEL,
            notes="Auto-paper trade from live 100/100 alert. Alert-only; no real order placed.",
        )

    def insert_source_paper_signal(
        self,
        run_id: int,
        setup_id: int,
        setup: SetupSignal,
        mode: str,
        source_key: str,
        source_label: str,
        notes: str,
        metadata: Optional[Dict] = None,
    ) -> Optional[int]:
        if self.has_source_paper_signal(source_key, mode, setup):
            return None
        event_metadata = {
            "mode": mode,
            "paper_only": True,
            "telegram_sent": False,
            "signal_source": source_key,
            FEATURE_ALERT_SOURCE: source_key,
            FEATURE_SOURCE_LABEL: source_label,
            "setup_id": setup_id,
            "target2": setup.target2,
            "invalidation": setup.invalidation,
            "timeframe": setup.timeframe,
            "market_condition": setup.market_condition,
            "market_regime": (setup.features or {}).get(
                "market_regime", setup.market_condition
            ),
            "features": setup.features,
        }
        event_metadata.update(metadata or {})
        return self.insert_paper_event(
            run_id=run_id,
            event_time=setup.created_at,
            symbol=setup.symbol,
            event_type="alerted",
            outcome="open",
            setup_type=setup.setup_type,
            direction=setup.direction,
            confidence=setup.confidence,
            risk_reward=setup.risk_reward,
            entry_low=setup.entry_low,
            entry_high=setup.entry_high,
            stop_loss=setup.stop_loss,
            target1=setup.target1,
            r_multiple=0.0,
            notes=notes,
            metadata=event_metadata,
        )

    def insert_source_paper_alert(
        self,
        run_id: int,
        alert_id: int,
        setup_id: int,
        setup: SetupSignal,
        mode: str,
        source_key: str,
        source_label: str,
        notes: str,
    ) -> Optional[int]:
        if self.has_paper_event_for_alert(alert_id):
            return None
        return self.insert_paper_event(
            run_id=run_id,
            event_time=setup.created_at,
            symbol=setup.symbol,
            event_type="alerted",
            outcome="open",
            setup_type=setup.setup_type,
            direction=setup.direction,
            confidence=setup.confidence,
            risk_reward=setup.risk_reward,
            entry_low=setup.entry_low,
            entry_high=setup.entry_high,
            stop_loss=setup.stop_loss,
            target1=setup.target1,
            r_multiple=0.0,
            notes=notes,
            metadata={
                "mode": mode,
                "signal_source": source_key,
                FEATURE_ALERT_SOURCE: source_key,
                FEATURE_SOURCE_LABEL: source_label,
                "alert_id": alert_id,
                "setup_id": setup_id,
                "target2": setup.target2,
                "invalidation": setup.invalidation,
                "timeframe": setup.timeframe,
                "market_condition": setup.market_condition,
                "market_regime": (setup.features or {}).get("market_regime", setup.market_condition),
                "features": setup.features,
            },
        )

    def list_live_100_paper_events(self, limit: int = 500) -> List[Dict]:
        with self.connect() as conn:
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

    def list_live_source_paper_events(
        self, source_key: str, mode: str, limit: int = 500
    ) -> List[Dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select pe.*, pr.source, pr.start_date, pr.end_date
                from paper_events pe
                join paper_runs pr on pr.id = pe.run_id
                where pe.event_type = 'alerted'
                  and json_extract(pe.metadata_json, '$.mode') = ?
                  and (
                    json_extract(pe.metadata_json, '$.signal_source') = ?
                    or json_extract(pe.metadata_json, '$.alert_source') = ?
                  )
                order by pe.event_time desc, pe.id desc
                limit ?
                """,
                (mode, source_key, source_key, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_paper_event_outcome(
        self,
        event_id: int,
        outcome: str,
        r_multiple: Optional[float],
        metadata: Dict,
        notes: Optional[str] = None,
    ) -> None:
        fields = "outcome = ?, r_multiple = ?, metadata_json = ?"
        params: List = [outcome, r_multiple, json.dumps(metadata)]
        if notes is not None:
            fields += ", notes = ?"
            params.append(notes)
        params.append(event_id)
        with self.connect() as conn:
            conn.execute(
                f"""
                update paper_events
                set {fields}
                where id = ?
                """,
                params,
            )

    def paper_summary(
        self,
        run_id: Optional[int] = None,
        signal_source: Optional[str] = None,
    ) -> Dict:
        clauses = []
        params: List = []
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if signal_source is not None:
            clauses.append(
                """
                (
                  json_extract(metadata_json, '$.signal_source') = ?
                  or json_extract(metadata_json, '$.alert_source') = ?
                )
                """
            )
            params.extend([signal_source, signal_source])
        where = f"where {' and '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            events = conn.execute(
                f"select * from paper_events {where} order by event_time asc", tuple(params)
            ).fetchall()
        rows = [dict(row) for row in events]
        alerted = [row for row in rows if row["event_type"] == "alerted"]
        blocked = [
            row for row in rows if row["event_type"] in {"blocked", "avoided"}
        ]
        suppressed = [row for row in rows if row["event_type"] == "suppressed"]
        ignored = [row for row in rows if row["event_type"] == "ignored"]
        missed = [row for row in rows if row["event_type"] == "missed"]
        open_alerts = [row for row in alerted if row.get("outcome") == "open"]
        closed_alerts = [
            row for row in alerted if row.get("outcome") in {"win", "loss", "breakeven"}
        ]
        alert_metrics = [_paper_path_metrics(row) for row in alerted]
        mfe_values = [
            metric["mfe_r"]
            for metric in alert_metrics
            if metric.get("mfe_r") is not None
        ]
        mae_values = [
            metric["mae_r"]
            for metric in alert_metrics
            if metric.get("mae_r") is not None
        ]
        move_start_threshold_r = 1.0
        move_start_success_count = sum(
            1 for value in mfe_values if value >= move_start_threshold_r
        )
        move_start_rate = (
            round(move_start_success_count / len(mfe_values) * 100, 2)
            if mfe_values
            else 0.0
        )
        wins = [row for row in closed_alerts if float(row.get("r_multiple") or 0) > 0]
        losses = [row for row in closed_alerts if float(row.get("r_multiple") or 0) < 0]
        tactical_closed = [
            metric
            for metric in alert_metrics
            if metric.get("tactical_outcome") in {"win", "loss", "breakeven"}
        ]
        tactical_wins = [
            metric
            for metric in tactical_closed
            if float(metric.get("tactical_r_multiple") or 0) > 0
        ]
        tactical_losses = [
            metric
            for metric in tactical_closed
            if float(metric.get("tactical_r_multiple") or 0) < 0
        ]
        tactical_total_r = round(
            sum(float(metric.get("tactical_r_multiple") or 0) for metric in tactical_closed),
            2,
        )
        tactical_gross_win = sum(
            float(metric.get("tactical_r_multiple") or 0) for metric in tactical_wins
        )
        tactical_gross_loss = abs(
            sum(float(metric.get("tactical_r_multiple") or 0) for metric in tactical_losses)
        )
        total_r = round(sum(float(row.get("r_multiple") or 0) for row in closed_alerts), 2)
        gross_win = sum(float(row.get("r_multiple") or 0) for row in wins)
        gross_loss = abs(sum(float(row.get("r_multiple") or 0) for row in losses))
        win_rate = round(len(wins) / len(closed_alerts) * 100, 2) if closed_alerts else 0.0
        avg_winner_r = round(gross_win / len(wins), 2) if wins else 0.0
        avg_loser_r = (
            round(sum(float(row.get("r_multiple") or 0) for row in losses) / len(losses), 2)
            if losses
            else 0.0
        )
        expectancy_r = (
            round(total_r / len(closed_alerts), 2)
            if closed_alerts
            else 0.0
        )
        max_drawdown_r = _max_drawdown_r(closed_alerts)
        return {
            "event_count": len(rows),
            "alerted_count": len(alerted),
            "closed_alerted_count": len(closed_alerts),
            "open_alerted_count": len(open_alerts),
            "blocked_count": len(blocked),
            "suppressed_count": len(suppressed),
            "ignored_count": len(ignored),
            "avoided_count": len(blocked),
            "missed_count": len(missed),
            "win_rate_sample_size": len(closed_alerts),
            "win_rate": win_rate,
            "closed_win_rate": win_rate,
            "total_r": total_r,
            "expectancy_r": expectancy_r,
            "avg_winner_r": avg_winner_r,
            "avg_loser_r": avg_loser_r,
            "winner_loser_ratio": (
                round(avg_winner_r / abs(avg_loser_r), 2)
                if avg_loser_r
                else (float("inf") if avg_winner_r else 0.0)
            ),
            "max_drawdown_r": max_drawdown_r,
            "profit_factor": (
                round(gross_win / gross_loss, 2)
                if gross_loss
                else (float("inf") if gross_win else 0.0)
            ),
            "move_start_threshold_r": move_start_threshold_r,
            "move_start_sample_size": len(mfe_values),
            "move_start_success_count": move_start_success_count,
            "move_start_rate": move_start_rate,
            "avg_mfe_r": round(sum(mfe_values) / len(mfe_values), 2)
            if mfe_values
            else 0.0,
            "avg_mae_r": round(sum(mae_values) / len(mae_values), 2)
            if mae_values
            else 0.0,
            "tactical_sample_size": len(tactical_closed),
            "tactical_win_rate": round(len(tactical_wins) / len(tactical_closed) * 100, 2)
            if tactical_closed
            else 0.0,
            "tactical_total_r": tactical_total_r,
            "tactical_profit_factor": (
                round(tactical_gross_win / tactical_gross_loss, 2)
                if tactical_gross_loss
                else (float("inf") if tactical_gross_win else 0.0)
            ),
            "source_breakdown": _paper_group_summary(closed_alerts, _paper_signal_source),
            "market_regime_breakdown": _paper_group_summary(
                closed_alerts, lambda row: _paper_dimension(row, "market_regime")
            ),
            "symbol_breakdown": _paper_group_summary(
                closed_alerts, lambda row: _paper_dimension(row, "symbol")
            ),
            "timeframe_breakdown": _paper_group_summary(
                closed_alerts, lambda row: _paper_dimension(row, "timeframe")
            ),
        }

    def insert_recommendation(self, recommendation: Recommendation) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into strategy_recommendations
                (created_at, title, rationale, proposed_change, metric, before_value,
                 after_value, sample_size, evidence_quality, overfitting_risk, status)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _iso(recommendation.created_at),
                    recommendation.title,
                    recommendation.rationale,
                    recommendation.proposed_change,
                    recommendation.metric,
                    recommendation.before_value,
                    recommendation.after_value,
                    recommendation.sample_size,
                    recommendation.evidence_quality,
                    recommendation.overfitting_risk,
                    recommendation.status,
                ),
            )
            return int(cur.lastrowid)
