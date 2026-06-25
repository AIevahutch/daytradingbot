from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value in {"true", "false"}:
        return value == "true"
    if value in {"True", "False"}:
        return value == "True"
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _read_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if line.strip():
            lines.append(line)
    return lines


def _next_content(lines: List[str], start: int):
    for idx in range(start, len(lines)):
        stripped = lines[idx].strip()
        if stripped:
            return idx, stripped
    return None, ""


def _parse_block(lines: List[str], index: int, indent: int):
    _, first = _next_content(lines, index)
    is_list = first.startswith("- ")
    container: Any = [] if is_list else {}

    while index < len(lines):
        line = lines[index]
        current_indent = len(line) - len(line.lstrip(" "))
        if current_indent < indent:
            break
        if current_indent > indent:
            index += 1
            continue

        stripped = line.strip()
        if isinstance(container, list):
            if not stripped.startswith("- "):
                break
            container.append(_parse_scalar(stripped[2:].strip()))
            index += 1
            continue

        if ":" not in stripped:
            index += 1
            continue
        key, raw_value = stripped.split(":", 1)
        raw_value = raw_value.strip()
        if raw_value:
            container[key.strip()] = _parse_scalar(raw_value)
            index += 1
        else:
            nested, next_index = _parse_block(lines, index + 1, indent + 2)
            container[key.strip()] = nested
            index = next_index
    return container, index


def _load_yaml_like(path: Path) -> Dict[str, Any]:
    lines = _read_lines(path)
    parsed, _ = _parse_block(lines, 0, 0)
    return parsed if isinstance(parsed, dict) else {}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed_key = key.strip()
        parsed_value = value.strip().strip('"').strip("'")
        if not os.environ.get(parsed_key):
            os.environ[parsed_key] = parsed_value


@dataclass
class Settings:
    symbols: List[str] = field(default_factory=lambda: ["SPY", "QQQ", "IWM"])
    database_path: str = "data/trading_bot.sqlite"
    timezone: str = "America/New_York"
    display_timezone: str = "America/Los_Angeles"
    alert_threshold: int = 80
    alert_timeframes: List[str] = field(default_factory=lambda: ["5m", "15m", "30m", "1h"])
    excluded_setup_types: List[str] = field(default_factory=list)
    scan_cadence_seconds: int = 900
    stale_data_minutes: int = 7
    max_alerts_per_symbol_per_day: int = 3
    telegram_max_attempts: int = 3
    telegram_retry_delay_seconds: float = 1.0
    manual_approval_required_for_rule_changes: bool = True
    research: Dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "require_for_alerts": True,
            "hard_block_risk_score": 65,
            "caution_risk_score": 40,
            "caution_penalty": -8,
            "hard_block_penalty": -30,
            "bias_conflict_penalty": -6,
            "earnings_horizon": "3month",
            "phase_times": {
                "premarket": "08:15",
                "morning": "10:00",
                "midday": "12:00",
                "eod": "14:30",
            },
        }
    )
    openai_summary: Dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "model": "gpt-5.4-mini",
        }
    )
    email: Dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "from_address": "",
            "to_address": "",
        }
    )
    market_hours: Dict[str, str] = field(
        default_factory=lambda: {
            "premarket_start": "04:00",
            "regular_start": "09:30",
            "regular_end": "16:00",
            "after_hours_end": "20:00",
        }
    )
    carter_squeeze: Dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "symbols": ["SPY", "QQQ"],
            "timeframe": "5m",
            "confirmation_timeframes": ["15m", "30m", "1h"],
            "length": 20,
            "bb_stddev": 2.0,
            "keltner_atr_multiple": 1.5,
            "min_squeeze_bars": 5,
            "min_volume_ratio": 1.1,
            "strict_alerts": True,
            "strict_min_volume_ratio": 1.5,
            "require_all_index_alignment": True,
            "required_index_symbols": ["SPY", "QQQ", "IWM"],
            "require_tactical_1r_path": True,
            "tactical_exit_r_multiple": 1.0,
            "min_risk_reward": 1.0,
            "target1_r_multiple": 1.0,
            "target2_r_multiple": 2.0,
            "stop_atr_buffer": 0.15,
            "duplicate_alert_minutes": 90,
            "symbol_alert_cooldown_minutes": 30,
            "max_alerts_per_symbol_per_day": 2,
            "base_score": 52,
            "squeeze_points": 8,
            "release_points": 8,
            "momentum_points": 10,
            "volume_points": 8,
            "timeframe_points": 8,
            "neutral_timeframe_points": 3,
            "market_points": 4,
            "risk_reward_points": 8,
            "hard_block_penalty": -30,
            "caution_penalty": -8,
            "chop_penalty": -8,
            "timeframe_conflict_penalty": -20,
            "peer_conflict_penalty": -6,
        }
    )
    failed_auction_trap: Dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "symbols": ["SPY", "QQQ", "IWM"],
            "timeframes": ["5m", "15m"],
            "session_timezone": "America/New_York",
            "start_time": "09:35",
            "end_time": "12:30",
            "opening_range_minutes": 15,
            "required_index_symbols": ["SPY", "QQQ"],
            "min_volume_ratio": 1.2,
            "min_range_ratio": 1.15,
            "min_break_pct": 0.015,
            "entry_buffer_pct": 0.015,
            "stop_buffer_pct": 0.02,
            "target1_r_multiple": 1.0,
            "target2_r_multiple": 2.0,
            "duplicate_alert_minutes": 90,
            "symbol_alert_cooldown_minutes": 30,
            "max_alerts_per_symbol_per_day": 3,
            "base_score": 58,
            "close_back_inside_points": 10,
            "participation_points": 8,
            "index_agreement_points": 8,
            "clean_1r_path_points": 8,
            "major_level_points": 6,
            "balanced_exception_points": 4,
        }
    )
    strategy: Dict[str, Any] = field(
        default_factory=lambda: {
            "min_risk_reward": 1.0,
            "fast_momentum_min_risk_reward": 1.0,
            "target1_r_multiple": 1.0,
            "target2_r_multiple": 2.0,
            "max_extension_from_vwap_pct": 1.2,
            "low_volume_ratio": 0.65,
            "chop_range_pct": 0.35,
            "duplicate_alert_minutes": 90,
            "symbol_alert_cooldown_minutes": 30,
            "avoid_regular_open_minutes": 15,
            "avoid_regular_close_minutes": 15,
            "avoid_midday_start": "11:30",
            "avoid_midday_end": "13:30",
            "midday_exception_min_volume_ratio": 2.4,
            "midday_exception_min_range_ratio": 2.0,
            "midday_exception_min_move_pct": 0.35,
            "fast_momentum_overrides_risk_blocks": True,
            "strict_index_alignment_for_alerts": True,
            "strict_index_alignment_symbols": ["SPY", "QQQ"],
            "block_standalone_level_breaks": True,
            "level_break_required_market_condition": "trending",
            "level_break_required_index_symbols": ["SPY", "QQQ", "IWM"],
            "vwap_min_volume_ratio": 1.2,
            "vwap_min_body_ratio": 0.35,
            "vwap_min_close_position": 0.62,
            "vwap_max_entry_extension_pct": 0.45,
            "vwap_cross_lookback_bars": 8,
            "vwap_max_crosses_lookback": 2,
            "vwap_opening_noise_minutes": 90,
            "block_weak_spy_vwap_reclaim_longs": True,
            "spy_vwap_reclaim_min_volume_ratio": 1.5,
            "spy_vwap_reclaim_min_body_ratio": 0.45,
            "spy_vwap_reclaim_min_close_position": 0.7,
        }
    )
    scoring_weights: Dict[str, int] = field(
        default_factory=lambda: {
            "base_setup": 58,
            "timeframe_continuity": 8,
            "level_confluence": 7,
            "vwap_confirmation": 7,
            "volume_confirmation": 6,
            "market_confirmation": 6,
            "clean_risk_reward": 8,
            "balanced_quality_bonus": 4,
            "fast_momentum_expansion_bonus": 6,
            "midday_momentum_exception_bonus": 4,
            "weak_volume_penalty": -12,
            "chop_penalty": -18,
            "conflicting_timeframes_penalty": -12,
            "overextension_penalty": -10,
            "stale_data_penalty": -30,
            "momentum_continuation_penalty": -20,
            "strat_continuation_penalty": -20,
            "vwap_quality_penalty": -20,
            "vwap_whipsaw_penalty": -18,
            "vwap_opening_noise_penalty": -10,
            "spy_vwap_reclaim_review_penalty": -25,
            "standalone_level_break_penalty": -35,
            "research_bias_conflict_penalty": -6,
        }
    )

    @property
    def database_file(self) -> Path:
        return (PROJECT_ROOT / self.database_path).resolve()


def load_settings(path: str = "config/settings.yaml") -> Settings:
    load_env_file(PROJECT_ROOT / ".env")
    data = _load_yaml_like(PROJECT_ROOT / path)
    settings = Settings()
    for key, value in data.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    return settings
