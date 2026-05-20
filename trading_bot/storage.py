from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from trading_bot.models import Candle, Level, Recommendation, SetupSignal, Trade, utc_now


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


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

                create table if not exists daily_market_reviews (
                    id integer primary key autoincrement,
                    session_date text not null unique,
                    market_condition text not null,
                    no_trade_reason text,
                    notes text not null,
                    created_at text not null
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
        cutoff = utc_now() - timedelta(minutes=duplicate_minutes)
        with self.connect() as conn:
            row = conn.execute(
                """
                select id from alerts
                where symbol = ?
                  and setup_type = ?
                  and direction = ?
                  and created_at >= ?
                order by created_at desc
                limit 1
                """,
                (setup.symbol, setup.setup_type, setup.direction, _iso(cutoff)),
            ).fetchone()
        return row is not None

    def alert_count_today(self, symbol: str) -> int:
        today = utc_now().date().isoformat()
        with self.connect() as conn:
            row = conn.execute(
                """
                select count(*) as count from alerts
                where symbol = ? and substr(created_at, 1, 10) = ?
                """,
                (symbol, today),
            ).fetchone()
        return int(row["count"])

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
            "daily_market_reviews",
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

    def paper_summary(self, run_id: Optional[int] = None) -> Dict:
        where = "where run_id = ?" if run_id is not None else ""
        params = (run_id,) if run_id is not None else ()
        with self.connect() as conn:
            events = conn.execute(
                f"select * from paper_events {where} order by event_time asc", params
            ).fetchall()
        rows = [dict(row) for row in events]
        alerted = [row for row in rows if row["event_type"] == "alerted"]
        avoided = [row for row in rows if row["event_type"] == "avoided"]
        missed = [row for row in rows if row["event_type"] == "missed"]
        wins = [row for row in alerted if float(row.get("r_multiple") or 0) > 0]
        losses = [row for row in alerted if float(row.get("r_multiple") or 0) < 0]
        total_r = round(sum(float(row.get("r_multiple") or 0) for row in alerted), 2)
        gross_win = sum(float(row.get("r_multiple") or 0) for row in wins)
        gross_loss = abs(sum(float(row.get("r_multiple") or 0) for row in losses))
        return {
            "event_count": len(rows),
            "alerted_count": len(alerted),
            "avoided_count": len(avoided),
            "missed_count": len(missed),
            "win_rate": round(len(wins) / len(alerted) * 100, 2) if alerted else 0.0,
            "total_r": total_r,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else (float("inf") if gross_win else 0.0),
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
