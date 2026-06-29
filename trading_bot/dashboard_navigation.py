from __future__ import annotations

from collections.abc import Sequence
from typing import Any


DASHBOARD_VIEW_QUERY_PARAM = "view"


def normalize_dashboard_view(
    raw_value: Any,
    allowed_views: Sequence[str],
    default_view: str,
) -> str:
    if not allowed_views:
        raise ValueError("allowed_views must not be empty")
    fallback = default_view if default_view in allowed_views else allowed_views[0]
    if isinstance(raw_value, (list, tuple)):
        raw_value = raw_value[0] if raw_value else ""
    value = str(raw_value or "").strip()
    return value if value in allowed_views else fallback


def dashboard_view_index(
    raw_value: Any,
    allowed_views: Sequence[str],
    default_view: str,
) -> int:
    return list(allowed_views).index(
        normalize_dashboard_view(raw_value, allowed_views, default_view)
    )
