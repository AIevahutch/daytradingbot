from __future__ import annotations

from typing import Dict, List, Optional

from trading_bot.models import utc_now


def ensure_trading_rules_table(store) -> None:
    with store.connect() as conn:
        conn.execute(
            """
            create table if not exists trading_rules (
                id integer primary key autoincrement,
                created_at text not null,
                updated_at text not null,
                rule_text text not null,
                category text not null,
                status text not null,
                commandment_order integer,
                notes text not null
            )
            """
        )


def add_trading_rule_entry(
    store,
    rule_text: str,
    category: str = "trade_rule",
    status: str = "draft",
    commandment_order: Optional[int] = None,
    notes: str = "",
) -> int:
    if hasattr(store, "add_trading_rule"):
        return int(
            store.add_trading_rule(
                rule_text=rule_text,
                category=category,
                status=status,
                commandment_order=commandment_order,
                notes=notes,
            )
        )

    ensure_trading_rules_table(store)
    now = utc_now().isoformat()
    with store.connect() as conn:
        cur = conn.execute(
            """
            insert into trading_rules
            (created_at, updated_at, rule_text, category, status, commandment_order, notes)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                rule_text.strip(),
                category or "trade_rule",
                status or "draft",
                commandment_order,
                notes or "",
            ),
        )
        return int(cur.lastrowid)


def update_trading_rule_entry(
    store,
    rule_id: int,
    rule_text: str,
    category: str = "trade_rule",
    status: str = "draft",
    commandment_order: Optional[int] = None,
    notes: str = "",
) -> bool:
    if hasattr(store, "update_trading_rule"):
        return bool(
            store.update_trading_rule(
                rule_id=rule_id,
                rule_text=rule_text,
                category=category,
                status=status,
                commandment_order=commandment_order,
                notes=notes,
            )
        )

    ensure_trading_rules_table(store)
    with store.connect() as conn:
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
                utc_now().isoformat(),
                rule_text.strip(),
                category or "trade_rule",
                status or "draft",
                commandment_order,
                notes or "",
                rule_id,
            ),
        )
        return cur.rowcount > 0


def delete_trading_rule_entry(store, rule_id: int) -> bool:
    if hasattr(store, "delete_trading_rule"):
        return bool(store.delete_trading_rule(rule_id))

    ensure_trading_rules_table(store)
    with store.connect() as conn:
        cur = conn.execute("delete from trading_rules where id = ?", (rule_id,))
        return cur.rowcount > 0


def list_trading_rule_entries(store) -> List[Dict]:
    if hasattr(store, "list_trading_rules"):
        return list(store.list_trading_rules())

    ensure_trading_rules_table(store)
    with store.connect() as conn:
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
