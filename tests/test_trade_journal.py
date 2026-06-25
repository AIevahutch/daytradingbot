from datetime import datetime
import json

from trading_bot.journal.delete import remove_trade_entry
from trading_bot.journal.rules import (
    add_trading_rule_entry,
    delete_trading_rule_entry,
    list_trading_rule_entries,
    update_trading_rule_entry,
)
from trading_bot.journal.trade_journal import TradeJournal
from trading_bot.settings import Settings
from trading_bot.storage import SQLiteStore


class ConnectOnlyStore:
    def __init__(self, store):
        self.store = store

    def connect(self):
        return self.store.connect()


def test_trade_journal_edit_trade_updates_source_of_truth(tmp_path):
    settings = Settings(database_path=str(tmp_path / "bot.sqlite"))
    store = SQLiteStore(settings.database_file)
    journal = TradeJournal(store)

    trade_id = journal.add_trade(
        symbol="SPY",
        setup_type="manual",
        direction="LONG",
        opened_at=datetime(2026, 6, 9, 13, 30),
        closed_at=datetime(2026, 6, 9, 14, 0),
        realized_pl=-25.0,
        entry_price=100.0,
        exit_price=99.5,
        quantity=1,
        confidence=80,
        notes="early entry",
        emotional_state="rushed",
        mistake_tags=["FOMO"],
    )

    journal.edit_trade(
        trade_id=trade_id,
        symbol="QQQ",
        setup_type="VWAP reclaim",
        direction="SHORT",
        opened_at=datetime(2026, 6, 9, 15, 0),
        closed_at=datetime(2026, 6, 9, 15, 45),
        took_trade=True,
        realized_pl=125.0,
        entry_price=200.0,
        exit_price=198.0,
        quantity=2,
        confidence=88,
        market_condition="trend",
        notes="corrected after review",
        emotional_state="calm",
        mistake_tags=["poor entry"],
    )

    trade = store.list_trades()[0]

    assert trade["id"] == trade_id
    assert trade["symbol"] == "QQQ"
    assert trade["setup_type"] == "VWAP reclaim"
    assert trade["direction"] == "SHORT"
    assert trade["opened_at"] == "2026-06-09T15:00:00"
    assert trade["closed_at"] == "2026-06-09T15:45:00"
    assert trade["realized_pl"] == 125.0
    assert trade["entry_price"] == 200.0
    assert trade["exit_price"] == 198.0
    assert trade["quantity"] == 2.0
    assert trade["confidence"] == 88
    assert trade["market_condition"] == "trend"
    assert trade["notes"] == "corrected after review"
    assert trade["emotional_state"] == "calm"
    assert json.loads(trade["mistake_tags_json"]) == ["poor entry"]


def test_trade_journal_remove_trade_deletes_related_context(tmp_path):
    settings = Settings(database_path=str(tmp_path / "bot.sqlite"))
    store = SQLiteStore(settings.database_file)
    journal = TradeJournal(store)

    trade_id = journal.add_trade(
        symbol="IWM",
        setup_type="manual",
        direction="LONG",
        opened_at=datetime(2026, 6, 9, 13, 30),
        realized_pl=10.0,
    )
    other_trade_id = journal.add_trade(
        symbol="SPY",
        setup_type="manual",
        direction="LONG",
        opened_at=datetime(2026, 6, 9, 14, 30),
        realized_pl=20.0,
    )
    partial_id = journal.add_partial_exit(
        trade_id=trade_id,
        price=1.25,
        quantity=1,
        realized_pl=5.0,
        exited_at=datetime(2026, 6, 9, 13, 45),
    )
    note_id = journal.add_note(
        "delete this note too",
        trade_id=trade_id,
        symbol="IWM",
        emotional_state="calm",
        tags=["review"],
    )

    assert journal.remove_trade(trade_id)

    remaining = store.list_trades()
    assert [row["id"] for row in remaining] == [other_trade_id]
    rows = {table: store.list_rows(table, 20) for table in ("partial_exits", "journal_notes")}
    assert partial_id not in [row["id"] for row in rows["partial_exits"]]
    assert note_id not in [row["id"] for row in rows["journal_notes"]]
    assert not journal.remove_trade(trade_id)


def test_dashboard_delete_helper_removes_trade_without_journal_method(tmp_path):
    settings = Settings(database_path=str(tmp_path / "bot.sqlite"))
    store = SQLiteStore(settings.database_file)
    journal = TradeJournal(store)
    trade_id = journal.add_trade(
        symbol="SPY",
        setup_type="manual",
        direction="LONG",
        opened_at=datetime(2026, 6, 9, 13, 30),
        realized_pl=0.0,
    )

    assert remove_trade_entry(store, trade_id)
    assert store.list_trades() == []
    assert not remove_trade_entry(store, trade_id)


def test_trading_rulebook_saves_edits_and_removes_rules(tmp_path):
    settings = Settings(database_path=str(tmp_path / "bot.sqlite"))
    store = SQLiteStore(settings.database_file)
    dashboard_store = ConnectOnlyStore(store)

    draft_id = add_trading_rule_entry(
        dashboard_store,
        "Avoid weak-volume chop.",
        category="when_not_to_trade",
        status="draft",
        notes="This prevents emotional entries.",
    )
    commandment_id = add_trading_rule_entry(
        dashboard_store,
        "Only take trades with clean risk/reward.",
        category="risk_management",
        status="commandment",
        commandment_order=1,
        notes="This keeps the math honest.",
    )

    rules = list_trading_rule_entries(dashboard_store)
    assert [row["id"] for row in rules[:2]] == [commandment_id, draft_id]
    assert rules[0]["commandment_order"] == 1

    assert update_trading_rule_entry(
        dashboard_store,
        draft_id,
        "No trades when I feel FOMO.",
        category="psychology",
        status="commandment",
        commandment_order=2,
        notes="Pause before entering.",
    )
    updated = {row["id"]: row for row in list_trading_rule_entries(dashboard_store)}
    assert updated[draft_id]["status"] == "commandment"
    assert updated[draft_id]["commandment_order"] == 2
    assert updated[draft_id]["rule_text"] == "No trades when I feel FOMO."

    assert delete_trading_rule_entry(dashboard_store, commandment_id)
    assert commandment_id not in [row["id"] for row in list_trading_rule_entries(dashboard_store)]
