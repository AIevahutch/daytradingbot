from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from trading_bot.dashboard_db import latest_dashboard_candle, list_dashboard_rows
from trading_bot.storage import SQLiteStore


def create_dashboard_fixture(database_path: Path) -> None:
    with sqlite3.connect(database_path) as conn:
        conn.executescript(
            """
            create table setups (
                id integer primary key autoincrement,
                created_at text not null,
                symbol text not null
            );
            create table candles (
                symbol text not null,
                timeframe text not null,
                timestamp text not null,
                close real not null,
                volume real not null
            );
            insert into setups (created_at, symbol) values ('2026-06-29T13:30:00', 'SPY');
            insert into candles (symbol, timeframe, timestamp, close, volume)
            values ('QQQ', '1m', '2026-06-29T13:30:00', 540.25, 12345);
            """
        )


def test_dashboard_reads_use_readonly_rows(tmp_path):
    database_path = tmp_path / "bot.db"
    create_dashboard_fixture(database_path)

    rows = list_dashboard_rows(database_path, "setups", limit=5)

    assert rows == [{"id": 1, "created_at": "2026-06-29T13:30:00", "symbol": "SPY"}]


def test_dashboard_candle_read_uses_symbol_and_timeframe(tmp_path):
    database_path = tmp_path / "bot.db"
    create_dashboard_fixture(database_path)

    candle = latest_dashboard_candle(database_path, "QQQ", "1m")

    assert candle == {
        "timestamp": "2026-06-29T13:30:00",
        "close": 540.25,
        "volume": 12345.0,
    }


def test_dashboard_reads_timeout_quickly_when_database_is_locked(tmp_path):
    database_path = tmp_path / "bot.db"
    create_dashboard_fixture(database_path)
    blocker = sqlite3.connect(database_path)
    try:
        blocker.execute("begin exclusive")
        started_at = time.monotonic()
        with pytest.raises(sqlite3.OperationalError):
            list_dashboard_rows(database_path, "setups", timeout_seconds=0.05)
        elapsed = time.monotonic() - started_at
    finally:
        blocker.rollback()
        blocker.close()

    assert elapsed < 1.0


def test_dashboard_store_can_skip_schema_initialization(tmp_path):
    database_path = tmp_path / "missing.db"

    SQLiteStore(database_path, initialize=False)

    assert not database_path.exists()
