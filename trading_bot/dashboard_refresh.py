from __future__ import annotations

from typing import Optional

import streamlit as st
from streamlit.runtime.scriptrunner_utils.script_run_context import (
    ScriptRunContext,
    get_script_run_ctx,
)

DEFAULT_REFRESH_INTERVAL_SECONDS = 60


def refresh_interval_seconds(
    interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS,
) -> int:
    return max(int(interval_seconds), 10)


def is_fragment_rerun(ctx: Optional[ScriptRunContext]) -> bool:
    return bool(ctx and ctx.fragment_ids_this_run)


def enable_dashboard_auto_refresh(
    interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS,
) -> None:
    @st.fragment(run_every=refresh_interval_seconds(interval_seconds))
    def auto_refresh_tick() -> None:
        ctx = get_script_run_ctx(suppress_warning=True)
        if is_fragment_rerun(ctx):
            st.rerun()
        st.empty()

    auto_refresh_tick()
