from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, Optional

from trading_bot.research.agent import current_session_date
from trading_bot.settings import Settings
from trading_bot.storage import SQLiteStore


def research_gate_context(settings: Settings, store: SQLiteStore, now: Optional[datetime] = None) -> Dict:
    if not settings.research.get("enabled", True):
        return {"enabled": False, "hard_block": False, "reason": ""}
    if not settings.research.get("require_for_alerts", True):
        return {"enabled": True, "hard_block": False, "reason": ""}

    session_date = current_session_date(settings, now).isoformat()
    brief = store.latest_research_brief(session_date=session_date)
    if not brief:
        return {
            "enabled": True,
            "hard_block": True,
            "reason": f"no same-day research brief for {session_date}",
            "hard_blocks": [f"no same-day research brief for {session_date}"],
            "risk_score": None,
            "bias": "neutral",
            "decision": "research_required",
            "phase": None,
        }

    risk_score = int(brief.get("risk_score") or 0)
    risk_warnings = _json_list(brief.get("hard_blocks_json"))
    hard_block_threshold = int(settings.research.get("hard_block_risk_score", 65))
    caution_threshold = int(settings.research.get("caution_risk_score", 40))
    reason = ""
    penalty = 0
    if risk_score >= hard_block_threshold:
        reason = "research risk is high; be careful"
        penalty = 0
    elif risk_score >= caution_threshold:
        reason = "research caution zone"
        penalty = int(settings.research.get("caution_penalty", -8))
    return {
        "enabled": True,
        "hard_block": False,
        "reason": reason,
        "hard_blocks": [],
        "warnings": risk_warnings or ([reason] if reason else []),
        "risk_score": risk_score,
        "bias": brief.get("bias") or "neutral",
        "decision": brief.get("decision") or "",
        "phase": brief.get("phase") or "",
        "penalty": penalty,
        "brief_id": brief.get("id"),
    }


def apply_research_gate(no_trade_state: Dict, gate: Dict) -> Dict:
    if not gate.get("enabled"):
        return no_trade_state
    merged = dict(no_trade_state or {})
    merged["research"] = gate
    if gate.get("hard_block"):
        hard_blocks = list(merged.get("hard_blocks") or [])
        hard_blocks.extend(gate.get("hard_blocks") or [gate.get("reason", "research hard block")])
        merged["is_no_trade"] = True
        merged["market_condition"] = "research_blocked"
        merged["reason"] = gate.get("reason") or "research hard block"
        merged["hard_blocks"] = list(dict.fromkeys(block for block in hard_blocks if block))
    return merged


def _json_list(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []
