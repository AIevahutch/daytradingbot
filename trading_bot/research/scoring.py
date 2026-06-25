from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Iterable, List

from trading_bot.research.models import ResearchBrief, ResearchInput


def build_research_brief(session_date: date, phase: str, inputs: Iterable[ResearchInput]) -> ResearchBrief:
    items = list(inputs)
    risk_score = 25
    drivers: List[str] = []
    risk_warnings: List[str] = []
    source_status = {}
    bias_votes = Counter()

    for item in items:
        risk_score += item.impact
        source_status[item.source] = worst_status(source_status.get(item.source), item.status)
        if item.bias in {"bullish", "bearish"}:
            weight = max(1, abs(item.impact))
            bias_votes[item.bias] += weight
        if item.impact >= 8 or item.status in {"missing", "warn"}:
            drivers.append(f"{item.title}: {item.detail}")
        if item.category == "macro_calendar" and item.impact >= 30 and phase == "premarket":
            risk_warnings.append(f"{item.title} today; wait for post-release structure.")
        if item.category == "volatility" and item.impact >= 18:
            risk_warnings.append("Elevated volatility; avoid forcing options trades.")

    missing_count = sum(1 for status in source_status.values() if status in {"missing", "warn", "fail"})
    if missing_count >= 3:
        risk_score += 8
        drivers.append("Multiple research sources are missing or degraded.")
    risk_score = max(0, min(100, int(round(risk_score))))

    if bias_votes["bullish"] > bias_votes["bearish"] + 2:
        bias = "bullish"
    elif bias_votes["bearish"] > bias_votes["bullish"] + 2:
        bias = "bearish"
    else:
        bias = "neutral"

    if risk_score >= 65:
        risk_warnings.append("Research risk is high; be careful and only take A+ confirmed setups.")
    trade_today = True
    if risk_score >= 40:
        decision = "trade_with_caution"
    else:
        decision = "trade_allowed"

    if not drivers:
        drivers.append("No major risk driver found in configured research sources.")
    summary = summarize_decision(phase, risk_score, bias, trade_today, drivers)
    return ResearchBrief(
        session_date=session_date.isoformat(),
        phase=phase,
        risk_score=risk_score,
        bias=bias,
        trade_today=trade_today,
        decision=decision,
        summary=summary,
        drivers=drivers[:6],
        hard_blocks=list(dict.fromkeys(risk_warnings)),
        source_status=source_status,
        evidence=[item.as_dict() for item in items],
    )


def worst_status(current: str, new: str) -> str:
    ranking = {"ok": 0, "missing": 1, "warn": 2, "fail": 3}
    if current is None:
        return new
    return new if ranking.get(new, 1) > ranking.get(current, 1) else current


def summarize_decision(phase: str, risk_score: int, bias: str, trade_today: bool, drivers: List[str]) -> str:
    action = "Trade only if an A+ chart setup appears" if trade_today else "Do not trade until risk clears"
    driver_text = drivers[0] if drivers else "No major configured driver"
    return (
        f"{phase_label(phase)} read: risk {risk_score}/100, {bias} bias. "
        f"{action}. Main driver: {driver_text}"
    )


def phase_label(phase: str) -> str:
    return {
        "premarket": "Premarket",
        "morning": "Morning",
        "midday": "Midday",
        "eod": "End of day",
    }.get(phase, phase)
