from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List


def _pl(row: Dict) -> float:
    return float(row.get("realized_pl") or 0)


def calculate_metrics(trades: Iterable[Dict]) -> Dict:
    rows = [row for row in trades if int(row.get("took_trade", 1)) == 1]
    profits = [_pl(row) for row in rows]
    wins = [value for value in profits if value > 0]
    losses = [value for value in profits if value < 0]
    total = sum(profits)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = []
    running = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for row in rows:
        running += _pl(row)
        peak = max(peak, running)
        max_drawdown = min(max_drawdown, running - peak)
        equity.append({"opened_at": row.get("opened_at"), "equity": round(running, 2)})

    return {
        "total_pl": round(total, 2),
        "trade_count": len(rows),
        "win_rate": round(len(wins) / len(rows) * 100, 2) if rows else 0.0,
        "average_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "average_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "expectancy": round(total / len(rows), 2) if rows else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else (float("inf") if gross_win else 0.0),
        "max_drawdown": round(max_drawdown, 2),
        "largest_winner": round(max(wins), 2) if wins else 0.0,
        "largest_loser": round(min(losses), 2) if losses else 0.0,
        "equity_curve": equity,
    }


def period_pl(trades: Iterable[Dict]) -> Dict[str, float]:
    buckets = {"daily": defaultdict(float), "weekly": defaultdict(float), "monthly": defaultdict(float)}
    for row in trades:
        opened = row.get("opened_at")
        if not opened:
            continue
        dt = datetime.fromisoformat(opened)
        value = _pl(row)
        buckets["daily"][dt.date().isoformat()] += value
        iso_year, iso_week, _ = dt.isocalendar()
        buckets["weekly"][f"{iso_year}-W{iso_week:02d}"] += value
        buckets["monthly"][f"{dt.year}-{dt.month:02d}"] += value
    return {name: {k: round(v, 2) for k, v in values.items()} for name, values in buckets.items()}


def breakdowns(trades: Iterable[Dict]) -> Dict[str, Dict[str, Dict]]:
    rows = list(trades)
    result = {
        "by_setup_type": _group_metrics(rows, "setup_type"),
        "by_market_condition": _group_metrics(rows, "market_condition"),
        "by_hour": _group_by_hour(rows),
        "by_confidence_bucket": _group_by_confidence(rows),
    }
    return result


def _group_metrics(rows: List[Dict], key: str) -> Dict[str, Dict]:
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "unknown")].append(row)
    return {name: calculate_metrics(group) for name, group in grouped.items()}


def _group_by_hour(rows: List[Dict]) -> Dict[str, Dict]:
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for row in rows:
        opened = row.get("opened_at")
        if opened:
            hour = datetime.fromisoformat(opened).strftime("%H:00")
            grouped[hour].append(row)
    return {name: calculate_metrics(group) for name, group in grouped.items()}


def _group_by_confidence(rows: List[Dict]) -> Dict[str, Dict]:
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for row in rows:
        confidence = row.get("confidence")
        if confidence is None:
            bucket = "unknown"
        else:
            confidence = int(confidence)
            bucket = f"{confidence // 10 * 10}-{confidence // 10 * 10 + 9}"
        grouped[bucket].append(row)
    return {name: calculate_metrics(group) for name, group in grouped.items()}


def mistake_tag_counts(trades: Iterable[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for row in trades:
        try:
            tags = json.loads(row.get("mistake_tags_json") or "[]")
        except json.JSONDecodeError:
            tags = []
        for tag in tags:
            counts[tag] += 1
    return dict(counts)

