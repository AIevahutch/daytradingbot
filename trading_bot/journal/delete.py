from __future__ import annotations


def remove_trade_entry(store, trade_id: int) -> bool:
    """Delete a journal trade and its attached journal context."""
    if hasattr(store, "delete_trade"):
        return bool(store.delete_trade(trade_id))

    with store.connect() as conn:
        conn.execute("delete from partial_exits where trade_id = ?", (trade_id,))
        conn.execute("delete from journal_notes where trade_id = ?", (trade_id,))
        cur = conn.execute("delete from trades where id = ?", (trade_id,))
        return cur.rowcount > 0
