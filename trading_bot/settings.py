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
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    symbols: List[str] = field(default_factory=lambda: ["SPY", "QQQ", "IWM"])
    database_path: str = "data/trading_bot.sqlite"
    timezone: str = "America/New_York"
    alert_threshold: int = 85
    scan_cadence_seconds: int = 60
    stale_data_minutes: int = 7
    max_alerts_per_symbol_per_day: int = 3
    telegram_max_attempts: int = 3
    telegram_retry_delay_seconds: float = 1.0
    manual_approval_required_for_rule_changes: bool = True
    market_hours: Dict[str, str] = field(
        default_factory=lambda: {
            "premarket_start": "04:00",
            "regular_start": "09:30",
            "regular_end": "16:00",
            "after_hours_end": "20:00",
        }
    )
    strategy: Dict[str, Any] = field(
        default_factory=lambda: {
            "min_risk_reward": 1.5,
            "max_extension_from_vwap_pct": 1.2,
            "low_volume_ratio": 0.65,
            "chop_range_pct": 0.35,
            "duplicate_alert_minutes": 90,
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
            "weak_volume_penalty": -12,
            "chop_penalty": -18,
            "conflicting_timeframes_penalty": -12,
            "overextension_penalty": -10,
            "stale_data_penalty": -30,
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
