from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import streamlit.components.v1 as components


MIN_REFRESH_INTERVAL_MS = 10_000
DEFAULT_REFRESH_INTERVAL_SECONDS = 60
COMPONENT_NAME = "dashboard_auto_refresh_v2"


def refresh_interval_ms(interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS) -> int:
    return max(int(interval_seconds * 1000), MIN_REFRESH_INTERVAL_MS)


def auto_refresh_asset_path() -> Path:
    return Path(__file__).resolve().parent / "dashboard_auto_refresh"


@lru_cache(maxsize=1)
def _auto_refresh_component():
    return components.declare_component(
        COMPONENT_NAME,
        path=str(auto_refresh_asset_path()),
    )


def enable_dashboard_auto_refresh(
    interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS,
    *,
    key: str = COMPONENT_NAME,
) -> Optional[dict]:
    component = _auto_refresh_component()
    return component(
        interval_ms=refresh_interval_ms(interval_seconds),
        key=key,
        default=None,
    )
