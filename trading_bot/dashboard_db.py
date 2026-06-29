from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import quote


DASHBOARD_TABLES = {
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

TABLE_ORDER_COLUMNS = {
    "candles": "timestamp",
}


def _database_uri(database_path: Path) -> str:
    encoded_path = quote(str(Path(database_path).resolve()), safe="/")
    return f"file:{encoded_path}?mode=ro"


def _connect_readonly(database_path: Path, timeout_seconds: float) -> sqlite3.Connection:
    conn = sqlite3.connect(
        _database_uri(database_path),
        uri=True,
        timeout=timeout_seconds,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("pragma query_only = true")
    return conn


def list_dashboard_rows(
    database_path: Path,
    table: str,
    *,
    limit: int = 200,
    timeout_seconds: float = 0.25,
) -> List[Dict]:
    if table not in DASHBOARD_TABLES:
        raise ValueError(f"Unsupported table: {table}")
    safe_limit = max(1, min(int(limit), 2000))
    order_column = TABLE_ORDER_COLUMNS.get(table, "id")
    with _connect_readonly(database_path, timeout_seconds) as conn:
        rows = conn.execute(
            f"select * from {table} order by {order_column} desc limit ?",
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_dashboard_tables(
    database_path: Path,
    table_limits: Dict[str, int],
    *,
    timeout_seconds: float = 0.25,
) -> Dict[str, List[Dict]]:
    for table in table_limits:
        if table not in DASHBOARD_TABLES:
            raise ValueError(f"Unsupported table: {table}")
    with _connect_readonly(database_path, timeout_seconds) as conn:
        results: Dict[str, List[Dict]] = {}
        for table, limit in table_limits.items():
            safe_limit = max(1, min(int(limit), 2000))
            order_column = TABLE_ORDER_COLUMNS.get(table, "id")
            rows = conn.execute(
                f"select * from {table} order by {order_column} desc limit ?",
                (safe_limit,),
            ).fetchall()
            results[table] = [dict(row) for row in rows]
    return results


def latest_dashboard_scan_heartbeat(
    database_path: Path,
    *,
    timeout_seconds: float = 0.25,
) -> Optional[Dict]:
    with _connect_readonly(database_path, timeout_seconds) as conn:
        row = conn.execute(
            "select * from scanner_heartbeats order by id desc limit 1"
        ).fetchone()
    return dict(row) if row else None


def latest_dashboard_candle(
    database_path: Path,
    symbol: str,
    timeframe: str = "1m",
    *,
    timeout_seconds: float = 0.25,
) -> Optional[Dict]:
    with _connect_readonly(database_path, timeout_seconds) as conn:
        row = conn.execute(
            """
            select timestamp, close, volume
            from candles
            where symbol = ? and timeframe = ?
            order by timestamp desc
            limit 1
            """,
            (symbol, timeframe),
        ).fetchone()
    return dict(row) if row else None


def latest_dashboard_candles(
    database_path: Path,
    symbols: Sequence[str],
    timeframe: str = "1m",
    *,
    timeout_seconds: float = 0.25,
) -> Dict[str, Optional[Dict]]:
    results: Dict[str, Optional[Dict]] = {symbol: None for symbol in symbols}
    if not symbols:
        return results
    with _connect_readonly(database_path, timeout_seconds) as conn:
        for symbol in symbols:
            row = conn.execute(
                """
                select timestamp, close, volume
                from candles
                where symbol = ? and timeframe = ?
                order by timestamp desc
                limit 1
                """,
                (symbol, timeframe),
            ).fetchone()
            results[symbol] = dict(row) if row else None
    return results
