from __future__ import annotations

import time
from typing import Optional

import streamlit as st
from streamlit.runtime.scriptrunner_utils.script_run_context import (
    ScriptRunContext,
    get_script_run_ctx,
)

DEFAULT_REFRESH_INTERVAL_SECONDS = 60
DEFAULT_NAVIGATION_PAUSE_SECONDS = 15


def refresh_interval_seconds(
    interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS,
) -> int:
    return max(int(interval_seconds), 10)


def is_fragment_rerun(ctx: Optional[ScriptRunContext]) -> bool:
    return bool(ctx and ctx.fragment_ids_this_run)


def should_pause_auto_refresh(
    state,
    pause_state_key: Optional[str],
    pause_seconds: int = DEFAULT_NAVIGATION_PAUSE_SECONDS,
    *,
    now: Optional[float] = None,
) -> bool:
    if not pause_state_key:
        return False
    try:
        last_interaction_at = float(state.get(pause_state_key) or 0)
    except (TypeError, ValueError):
        return False
    if last_interaction_at <= 0:
        return False
    current_time = time.monotonic() if now is None else now
    return 0 <= current_time - last_interaction_at < pause_seconds


def enable_dashboard_auto_refresh(
    interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS,
    *,
    pause_state_key: Optional[str] = None,
    pause_seconds: int = DEFAULT_NAVIGATION_PAUSE_SECONDS,
) -> None:
    @st.fragment(run_every=refresh_interval_seconds(interval_seconds))
    def auto_refresh_tick() -> None:
        ctx = get_script_run_ctx(suppress_warning=True)
        if is_fragment_rerun(ctx):
            if should_pause_auto_refresh(st.session_state, pause_state_key, pause_seconds):
                st.empty()
                return
            st.rerun()
        st.empty()

    auto_refresh_tick()
