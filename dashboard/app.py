from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import re
import sys
from typing import Optional, Union
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.analytics.performance import breakdowns, calculate_metrics, period_pl
from trading_bot.analytics.recommendations import RecommendationEngine
from trading_bot.alert_policy import is_current_approved_telegram_alert
from trading_bot.alerts.telegram import TelegramClient
from trading_bot.dashboard_refresh import enable_dashboard_auto_refresh
from trading_bot.dashboard_db import (
    latest_dashboard_candle,
    latest_dashboard_candles,
    latest_dashboard_scan_heartbeat,
    list_dashboard_rows,
    list_dashboard_tables,
)
from trading_bot.dashboard_navigation import (
    DASHBOARD_VIEW_QUERY_PARAM,
    normalize_dashboard_view,
)
from trading_bot.dashboard_status import lightweight_dashboard_status
from trading_bot.email.gmail import GmailSMTPClient
from trading_bot.health import run_healthcheck
from trading_bot.journal.delete import remove_trade_entry
from trading_bot.journal.rules import (
    add_trading_rule_entry,
    delete_trading_rule_entry,
    list_trading_rule_entries,
    update_trading_rule_entry,
)
from trading_bot.journal.trade_journal import TradeJournal
import trading_bot.live_paper as live_paper
from trading_bot.research.agent import ResearchAgent, current_session_date
from trading_bot.research.calendar import PHASES, PHASE_LABELS, phase_for_datetime
from trading_bot.runtime.scanner_process import (
    DEFAULT_LOG_FILE,
    run_scan_once,
    start_scanner,
    stop_scanner,
    summarize_scan_result,
)
from trading_bot.settings import load_settings
from trading_bot.signal_sources import (
    CORE_SOURCE_LABEL,
    LIVE_CARTER_PAPER_SOURCE,
    LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE,
    LIVE_CORE_100_PAPER_SOURCE,
)
from trading_bot.storage import SQLiteStore
from trading_bot.tradingview import tradingview_url


logger = logging.getLogger(__name__)

st.set_page_config(page_title="SPY/QQQ/IWM Alert Bot", layout="wide")


AUTO_REFRESH_SECONDS = 60
DASHBOARD_CACHE_TTL_SECONDS = 5
DASHBOARD_DB_TIMEOUT_SECONDS = 0.25
EXPERIMENT_PROMOTION_RULES = """Promotion gate for any experimental setup lane:

1. Dashboard-only first. No Telegram alerts and no core-score mixing while it is experimental.
2. Minimum 25 closed paper-tracked signals before promotion review.
3. Win rate must be 80% or better on closed paper signals.
4. Profit factor must be 2.0 or better.
5. Expectancy must be +0.40R per trade or better using the bot's 1R paper target logic.
6. Evidence must span at least 3 trading days.
7. Drawdown must be controlled, and losses must have a clear, filterable reason.
8. SPY and QQQ should agree in direction for high-conviction index alerts.
9. Eva must approve the lane before it becomes Telegram-alertable.
10. Alert-only forever. This bot never auto-trades."""


def enable_auto_refresh(interval_seconds: int = AUTO_REFRESH_SECONDS) -> None:
    enable_dashboard_auto_refresh(interval_seconds)


@st.cache_resource
def get_store(config_mtime: float):
    settings = load_settings()
    return settings, SQLiteStore(
        settings.database_file,
        timeout_seconds=DASHBOARD_DB_TIMEOUT_SECONDS,
        initialize=False,
    )


CONFIG_FILE = PROJECT_ROOT / "config" / "settings.yaml"
settings, store = get_store(CONFIG_FILE.stat().st_mtime if CONFIG_FILE.exists() else 0.0)
journal = TradeJournal(store)
DISPLAY_TZ = ZoneInfo(getattr(settings, "display_timezone", "America/Los_Angeles"))
OPTIONAL_DASHBOARD_TABLES = {
    "research_briefs",
    "research_evidence",
    "research_email_attempts",
}
TELEGRAM_TEST_MESSAGE = (
    "SPY/QQQ/IWM alert bot test message. Telegram delivery is working. "
    "This is an operational test only, not a trade alert."
)
MOMENTUM_EXCEPTION_TITLE = "Momentum Exception:"
MOMENTUM_EXCEPTION_NOTE = "\n".join(
    [
        MOMENTUM_EXCEPTION_TITLE,
        "- High research risk does not block alerts anymore; it adds a caution warning to stay selective.",
        "- Fast Momentum Expansion and all-index trend continuation still need SPY/QQQ/IWM alignment.",
        "- Every alert still requires volume confirmation, timeframe alignment, VWAP confirmation, and clean risk/reward.",
        "- This is a heads-up only. Confirm on TradingView before acting.",
    ]
)


DATE_COLUMNS = {
    "created_at",
    "attempted_at",
    "opened_at",
    "closed_at",
    "started_at",
    "completed_at",
    "reviewed_at",
    "approved_at",
    "event_time",
    "timestamp",
}
DATE_ONLY_COLUMNS = {"session_date", "start_date", "end_date"}
ISO_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
MINUTES_PATTERN = re.compile(r"(\d+(?:\.\d+)?) minutes old")
MISTAKE_TAG_OPTIONS = [
    "FOMO",
    "revenge trade",
    "oversized position",
    "poor entry",
    "ignored stop",
    "emotional trade",
]


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
          --app-bg: #f6f7f5;
          --panel: #ffffff;
          --ink: #151515;
          --muted: #6f746f;
          --line: #e3e5df;
          --blue: #0a84ff;
          --green: #2e7d32;
          --amber: #b7791f;
          --red: #c62828;
        }
        .stApp {
          background: var(--app-bg);
          color: var(--ink);
        }
        .block-container {
          padding-top: 2rem;
          padding-bottom: 3rem;
          max-width: 1240px;
        }
        h1, h2, h3 {
          letter-spacing: 0;
        }
        div[data-testid="stMetric"] {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 14px 16px;
          box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        div[data-testid="stMetricLabel"] p {
          color: var(--muted);
          font-size: 0.83rem;
        }
        div[data-testid="stMetricValue"] {
          font-size: 1.7rem;
        }
        .stButton button,
        .stLinkButton a {
          border-radius: 8px !important;
          min-height: 42px;
          font-weight: 650;
        }
        .stTabs [data-baseweb="tab-list"] {
          gap: 6px;
          border-bottom: 1px solid var(--line);
        }
        .stTabs [data-baseweb="tab"] {
          border-radius: 8px 8px 0 0;
          padding: 10px 14px;
        }
        div[data-testid="stExpander"] {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        div[data-testid="stDataFrame"] {
          border: 1px solid var(--line);
          border-radius: 8px;
          overflow: hidden;
        }
        .app-hero {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 18px 20px;
          margin-bottom: 18px;
          box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
        }
        .eyebrow {
          color: var(--muted);
          font-size: 0.82rem;
          font-weight: 650;
          text-transform: uppercase;
          letter-spacing: .08em;
          margin-bottom: 4px;
        }
        .hero-title {
          font-size: 2.2rem;
          line-height: 1.05;
          font-weight: 760;
          color: var(--ink);
          margin: 0;
        }
        .hero-copy {
          color: var(--muted);
          margin: 8px 0 0 0;
          font-size: 0.98rem;
        }
        .status-row {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          align-items: center;
          margin-top: 12px;
        }
        .pill {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          border-radius: 999px;
          border: 1px solid var(--line);
          background: #fafafa;
          color: var(--ink);
          padding: 5px 10px;
          font-size: 0.82rem;
          font-weight: 650;
          white-space: nowrap;
        }
        .pill.ok {
          background: #edf7ee;
          border-color: #c9e8cd;
          color: var(--green);
        }
        .pill.warn {
          background: #fff7e6;
          border-color: #f1d49a;
          color: var(--amber);
        }
        .pill.fail {
          background: #fff0f0;
          border-color: #f0b8b8;
          color: var(--red);
        }
        .pill.info {
          background: #edf5ff;
          border-color: #bfdcff;
          color: #0757a8;
        }
        .mini-card {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 14px;
          margin-bottom: 12px;
          box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        .card-title {
          font-size: 1.05rem;
          font-weight: 720;
          margin: 0 0 4px 0;
          color: var(--ink);
        }
        .card-meta {
          color: var(--muted);
          font-size: 0.86rem;
          margin: 0;
        }
        .reason-text {
          color: #303331;
          line-height: 1.45;
        }
        .subtle {
          color: var(--muted);
        }
        .analytics-card-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 10px;
          margin: 8px 0 18px 0;
        }
        .analytics-card {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 12px 14px;
          box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
          min-width: 0;
        }
        .analytics-card-title {
          color: var(--ink);
          font-size: 0.95rem;
          font-weight: 720;
          line-height: 1.25;
          margin: 0 0 10px 0;
          overflow-wrap: anywhere;
        }
        .analytics-metric-list {
          display: grid;
          gap: 7px;
        }
        .analytics-metric-row {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 10px;
          border-top: 1px solid #eef1f4;
          padding-top: 7px;
          min-width: 0;
        }
        .analytics-metric-row:first-child {
          border-top: 0;
          padding-top: 0;
        }
        .analytics-metric-label {
          color: var(--muted);
          font-size: 0.78rem;
          line-height: 1.2;
          min-width: 0;
        }
        .analytics-metric-value {
          color: var(--ink);
          font-size: 0.9rem;
          font-weight: 700;
          line-height: 1.2;
          text-align: right;
          overflow-wrap: anywhere;
          min-width: 0;
        }
        .analytics-metric-value.positive {
          color: var(--green);
        }
        .analytics-metric-value.negative {
          color: var(--red);
        }
        .research-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(118px, 1fr));
          gap: 12px;
          margin-bottom: 14px;
        }
        .research-metric {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 14px 16px;
          box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
          min-height: 88px;
        }
        .research-metric-label {
          color: var(--muted);
          font-size: 0.82rem;
          margin: 0 0 8px 0;
        }
        .research-metric-value {
          color: var(--ink);
          font-size: 1.55rem;
          line-height: 1.12;
          font-weight: 650;
          margin: 0;
          overflow-wrap: anywhere;
        }
        @media (max-width: 760px) {
          .research-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def rows(table: str, limit: int = 500):
    try:
        return cached_dashboard_rows(
            str(settings.database_file),
            table,
            int(limit),
            dashboard_database_signature(),
        )
    except ValueError:
        if table in OPTIONAL_DASHBOARD_TABLES:
            logger.warning("Optional dashboard table is unavailable: %s", table)
            return []
        raise
    except (OSError, sqlite3.Error) as exc:
        logger.warning("Dashboard read failed for %s: %s", table, exc)
        if table in OPTIONAL_DASHBOARD_TABLES:
            return []
        st.warning(f"{table} is temporarily unavailable; showing the rest of the dashboard.")
        return []


def df(table: str, limit: int = 500):
    data = rows(table, limit)
    return pd.DataFrame(data) if data else pd.DataFrame()


def dashboard_database_signature() -> tuple[int, int]:
    try:
        stat = Path(settings.database_file).stat()
    except OSError:
        return (0, 0)
    return (int(stat.st_mtime_ns), int(stat.st_size))


@st.cache_data(ttl=DASHBOARD_CACHE_TTL_SECONDS, show_spinner=False)
def cached_dashboard_rows(
    database_path: str,
    table: str,
    limit: int,
    database_signature: tuple[int, int],
) -> list[dict]:
    return list_dashboard_rows(
        Path(database_path),
        table,
        limit=limit,
        timeout_seconds=DASHBOARD_DB_TIMEOUT_SECONDS,
    )


@st.cache_data(ttl=DASHBOARD_CACHE_TTL_SECONDS, show_spinner=False)
def cached_dashboard_tables(
    database_path: str,
    table_limits: tuple[tuple[str, int], ...],
    database_signature: tuple[int, int],
) -> dict[str, list[dict]]:
    return list_dashboard_tables(
        Path(database_path),
        dict(table_limits),
        timeout_seconds=DASHBOARD_DB_TIMEOUT_SECONDS,
    )


@st.cache_data(ttl=DASHBOARD_CACHE_TTL_SECONDS, show_spinner=False)
def cached_latest_dashboard_heartbeat(
    database_path: str,
    database_signature: tuple[int, int],
) -> Optional[dict]:
    return latest_dashboard_scan_heartbeat(
        Path(database_path),
        timeout_seconds=DASHBOARD_DB_TIMEOUT_SECONDS,
    )


@st.cache_data(ttl=DASHBOARD_CACHE_TTL_SECONDS, show_spinner=False)
def cached_latest_dashboard_candle(
    database_path: str,
    symbol: str,
    timeframe: str,
    database_signature: tuple[int, int],
) -> Optional[dict]:
    return latest_dashboard_candle(
        Path(database_path),
        symbol,
        timeframe,
        timeout_seconds=DASHBOARD_DB_TIMEOUT_SECONDS,
    )


@st.cache_data(ttl=DASHBOARD_CACHE_TTL_SECONDS, show_spinner=False)
def cached_latest_dashboard_candles(
    database_path: str,
    symbols: tuple[str, ...],
    timeframe: str,
    database_signature: tuple[int, int],
) -> dict[str, Optional[dict]]:
    return latest_dashboard_candles(
        Path(database_path),
        symbols,
        timeframe,
        timeout_seconds=DASHBOARD_DB_TIMEOUT_SECONDS,
    )


def dashboard_frames(table_limits: dict[str, int]) -> dict[str, pd.DataFrame]:
    try:
        data = cached_dashboard_tables(
            str(settings.database_file),
            tuple(table_limits.items()),
            dashboard_database_signature(),
        )
    except (OSError, sqlite3.Error) as exc:
        logger.warning("Dashboard batch read failed: %s", exc)
        st.warning("Some dashboard data is temporarily unavailable; showing what can load now.")
        data = {}
    return {
        table: pd.DataFrame(data.get(table) or [])
        for table in table_limits
    }


def parse_datetime(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TZ)


def to_storage_datetime(local_date, local_time) -> datetime:
    local_dt = datetime.combine(local_date, local_time).replace(tzinfo=DISPLAY_TZ)
    return local_dt.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)


def optional_float(value):
    value = float(value or 0)
    return value if value > 0 else None


def optional_confidence(value):
    value = int(value or 0)
    return value if value > 0 else None


def safe_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_text(value, default: str = "") -> str:
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    text = str(value or "").strip()
    return text if text and text.lower() != "nan" else default


def display_optional_number(value) -> str:
    try:
        if pd.isna(value):
            return "-"
    except TypeError:
        pass
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def option_index(options, value, default: int = 0) -> int:
    try:
        return options.index(value)
    except ValueError:
        return default


def rerun_dashboard() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


def paper_summary_compat(store_obj, run_id=None, signal_source=None):
    try:
        return store_obj.paper_summary(run_id, signal_source=signal_source)
    except TypeError:
        return SQLiteStore.paper_summary(
            store_obj,
            run_id=run_id,
            signal_source=signal_source,
        )


def parse_date(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None


def relative_time(dt: datetime) -> str:
    now = datetime.now(timezone.utc).astimezone(DISPLAY_TZ)
    seconds = max((now - dt).total_seconds(), 0)
    minutes = int(seconds // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 14:
        return f"{days}d ago"
    weeks = days // 7
    if weeks < 10:
        return f"{weeks}w ago"
    months = days // 30
    return f"{months}mo ago"


def format_datetime(value, include_relative: bool = True) -> str:
    dt = parse_datetime(value)
    if not dt:
        return "-"
    label = dt.strftime("%b %-d, %Y at %-I:%M %p %Z")
    if include_relative:
        label = f"{label} ({relative_time(dt)})"
    return label


def format_date(value) -> str:
    dt = parse_date(value)
    return dt.strftime("%b %-d, %Y") if dt else "-"


def readable_minutes(minutes_text: str) -> str:
    minutes = float(minutes_text)
    if minutes < 60:
        return f"{int(minutes)} minutes old"
    hours = int(minutes // 60)
    if hours < 24:
        return f"{hours} hours old"
    days = int(hours // 24)
    rem_hours = hours % 24
    if rem_hours:
        return f"{days} days, {rem_hours} hours old"
    return f"{days} days old"


def format_text_dates(text: str) -> str:
    text = ISO_PATTERN.sub(lambda match: format_datetime(match.group(0)), str(text))
    return MINUTES_PATTERN.sub(lambda match: readable_minutes(match.group(1)), text)


def format_cadence(seconds: int) -> str:
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def display_df(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    for column in out.columns:
        if column in DATE_COLUMNS or column.endswith("_at"):
            out[column] = out[column].apply(format_datetime)
        elif column in DATE_ONLY_COLUMNS or column.endswith("_date"):
            out[column] = out[column].apply(format_date)
        elif column.endswith("_json"):
            out[column] = out[column].astype(str).str.slice(0, 80)
    out.columns = [column.replace("_", " ").title() for column in out.columns]
    return out


def show_table(frame: pd.DataFrame, *, height: Optional[int] = None) -> None:
    st.dataframe(
        display_df(frame),
        width="stretch",
        hide_index=True,
        height=height,
    )


def format_money(value) -> str:
    numeric = safe_float(value)
    sign = "-" if numeric < 0 else ""
    return f"{sign}${abs(numeric):,.2f}"


def format_percent(value) -> str:
    return f"{safe_float(value):.1f}%"


def format_whole_number(value) -> str:
    return f"{safe_int(value):,}"


def analytics_value_class(raw_value) -> str:
    numeric = safe_float(raw_value)
    if numeric > 0:
        return "positive"
    if numeric < 0:
        return "negative"
    return ""


def render_analytics_card_grid(cards: list[dict]) -> None:
    if not cards:
        st.info("No data")
        return

    html = ['<div class="analytics-card-grid">']
    for card in cards:
        html.append('<div class="analytics-card">')
        html.append(f'<p class="analytics-card-title">{escape(str(card["title"]))}</p>')
        html.append('<div class="analytics-metric-list">')
        for metric in card["metrics"]:
            value_class = metric.get("value_class", "")
            class_attr = f" {escape(value_class)}" if value_class else ""
            html.append(
                '<div class="analytics-metric-row">'
                f'<span class="analytics-metric-label">{escape(str(metric["label"]))}</span>'
                f'<span class="analytics-metric-value{class_attr}">{escape(str(metric["value"]))}</span>'
                "</div>"
            )
        html.append("</div></div>")
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_period_summary_cards(period_name: str, period_values: dict) -> None:
    st.markdown(f"#### {escape(period_name.title())}")
    sorted_values = sorted(period_values.items(), key=lambda item: item[0], reverse=True)
    cards = [
        {
            "title": period,
            "metrics": [
                {
                    "label": "Realized P/L",
                    "value": format_money(value),
                    "value_class": analytics_value_class(value),
                }
            ],
        }
        for period, value in sorted_values
    ]
    render_analytics_card_grid(cards)


def render_breakdown_metric_cards(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("No data")
        return

    cards = []
    for row in frame.to_dict("records"):
        total_pl = row.get("total_pl")
        expectancy = row.get("expectancy")
        drawdown = row.get("max_drawdown")
        cards.append(
            {
                "title": row.get("group") or "unknown",
                "metrics": [
                    {
                        "label": "Total P/L",
                        "value": format_money(total_pl),
                        "value_class": analytics_value_class(total_pl),
                    },
                    {"label": "Trades", "value": format_whole_number(row.get("trade_count"))},
                    {"label": "Win Rate", "value": format_percent(row.get("win_rate"))},
                    {
                        "label": "Expectancy",
                        "value": format_money(expectancy),
                        "value_class": analytics_value_class(expectancy),
                    },
                    {"label": "Profit Factor", "value": format_profit_factor(row.get("profit_factor"))},
                    {
                        "label": "Max DD",
                        "value": format_money(drawdown),
                        "value_class": analytics_value_class(drawdown),
                    },
                ],
            }
        )
    render_analytics_card_grid(cards)


def dashboard_nav_key(view: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", view.lower()).strip("_")
    return f"dashboard_nav_{slug}"


def render_dashboard_navigation(views: list[str], selected: str) -> None:
    nav_cols = st.columns(len(views))
    for nav_col, view in zip(nav_cols, views):
        clicked = nav_col.button(
            view,
            type="primary" if view == selected else "secondary",
            use_container_width=True,
            key=dashboard_nav_key(view),
        )
        if clicked and view != selected:
            st.query_params[DASHBOARD_VIEW_QUERY_PARAM] = view
            rerun_dashboard()


def link_action(label: str, url: str) -> None:
    if hasattr(st, "link_button"):
        st.link_button(label, url, use_container_width=True)
    else:
        st.markdown(f"[{escape(label)}]({url})")


def status_class(status: str) -> str:
    status = str(status or "").lower()
    if status in {"ok", "running", "delivered", "alert_ready", "completed"}:
        return "ok"
    if status in {"fail", "failed", "error"}:
        return "fail"
    if status in {
        "warn",
        "warning",
        "degraded",
        "stopped",
        "missing",
        "missing_api_key",
        "not_configured",
        "disabled",
    }:
        return "warn"
    return "info"


def pill(label: str, status: str = "info") -> str:
    return f'<span class="pill {status_class(status)}">{escape(str(label))}</span>'


def confidence_status(confidence) -> str:
    try:
        value = int(confidence)
    except (TypeError, ValueError):
        return "info"
    if value >= settings.alert_threshold:
        return "ok"
    if value >= 70:
        return "warn"
    return "info"


def render_intro(health_status: str, scanner_running: bool) -> None:
    scanner_label = "Scanner running" if scanner_running else "Scanner stopped"
    st.markdown(
        f"""
        <div class="app-hero">
          <div class="eyebrow">Alert-only trading assistant</div>
          <div class="hero-title">SPY / QQQ / IWM</div>
          <p class="hero-copy">Clean market context, A+ alert filtering, manual TradingView confirmation, and journaled discipline.</p>
          <div class="status-row">
            {pill("Dashboard " + str(health_status).upper(), health_status)}
            {pill(scanner_label, "running" if scanner_running else "stopped")}
            {pill("Telegram configured", "ok")}
            {pill("No auto-trading", "info")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_check_card(check: dict) -> None:
    status = check.get("status", "info")
    name = str(check.get("name", "")).replace("_", " ").title()
    detail = format_text_dates(check.get("detail", ""))
    st.markdown(
        f"""
        <div class="mini-card">
          <div class="status-row" style="margin-top:0;">
            {pill(name, status)}
          </div>
          <p class="card-meta" style="margin-top:8px;">{escape(detail)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_setup_summary(
    row: Union[pd.Series, dict],
    *,
    compact: bool = False,
    candle: Optional[dict] = None,
) -> None:
    value = int(row.get("confidence", 0) or 0)
    status = confidence_status(value)
    source_label = setup_source_label(row)
    symbol = safe_text(row.get("symbol"))
    if candle is None and symbol:
        candle = latest_symbol_candle(symbol)
    market_status = "warn"
    if candle:
        candle_dt = parse_datetime(candle.get("timestamp"))
        age_minutes = (
            max((datetime.now(timezone.utc).astimezone(DISPLAY_TZ) - candle_dt).total_seconds() / 60.0, 0.0)
            if candle_dt
            else float("inf")
        )
        market_status = "ok" if age_minutes <= settings.stale_data_minutes else "warn"
    title = f"{row.get('symbol', '')} {row.get('direction', '')} {row.get('setup_type', '')}"
    meta = (
        f"Setup created {format_datetime(row.get('created_at'))} | "
        f"Risk/reward {float(row.get('risk_reward') or 0):.2f} | "
        f"{row.get('market_condition', 'unknown')}"
    )
    market_meta = ""
    if candle:
        market_meta = (
            f"Latest 1m close {safe_float(candle.get('close')):.2f} | "
            f"{format_datetime(candle.get('timestamp'))}"
        )
    st.markdown(
        f"""
        <div class="mini-card">
          <div class="status-row" style="margin-top:0;">
            {pill(str(value) + "/100", status)}
            {pill(row.get("status", "candidate"), row.get("status", "candidate"))}
            {pill(source_label, "info")}
            {pill("Market data updating", market_status)}
          </div>
          <p class="card-title">{escape(title)}</p>
          <p class="card-meta">{escape(market_meta)}</p>
          <p class="card-meta">{escape(meta)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(min(max(value, 0), 100) / 100)
    if not compact:
        st.markdown(f'<p class="reason-text">{escape(str(row.get("reasoning", "")))}</p>', unsafe_allow_html=True)
        avoid = row.get("avoid_if")
        if avoid:
            st.caption(f"Avoid if: {avoid}")


def active_setup_window_minutes() -> float:
    cadence_minutes = float(settings.scan_cadence_seconds) / 60.0
    return max(20.0, cadence_minutes * 5.0)


def setup_is_active(row: Union[pd.Series, dict]) -> bool:
    created_at = parse_datetime(row.get("created_at"))
    if not created_at:
        return False
    now = datetime.now(timezone.utc).astimezone(DISPLAY_TZ)
    age_minutes = max((now - created_at).total_seconds() / 60.0, 0.0)
    return age_minutes <= active_setup_window_minutes()


def alert_is_active(row: Union[pd.Series, dict]) -> bool:
    created_at = parse_datetime(row.get("created_at"))
    if not created_at:
        return False
    if safe_int(row.get("delivered")) != 1:
        return False
    if safe_int(row.get("confidence")) < settings.alert_threshold:
        return False
    now = datetime.now(timezone.utc).astimezone(DISPLAY_TZ)
    age_minutes = max((now - created_at).total_seconds() / 60.0, 0.0)
    return age_minutes <= max(90.0, active_setup_window_minutes() * 3.0)


def alert_still_matches_market(
    alert_setup: Union[pd.Series, dict],
    latest_context: Optional[Union[pd.Series, dict]],
) -> bool:
    if latest_context is None:
        return True
    try:
        if int(latest_context.get("id") or 0) == int(alert_setup.get("id") or 0):
            return True
    except (TypeError, ValueError):
        pass

    alert_time = parse_datetime(alert_setup.get("alert_created_at")) or parse_datetime(alert_setup.get("created_at"))
    context_time = parse_datetime(latest_context.get("created_at"))
    if alert_time and context_time and context_time <= alert_time:
        return True

    alert_direction = safe_text(alert_setup.get("direction")).upper()
    context_direction = safe_text(latest_context.get("direction")).upper()
    if alert_direction and context_direction and alert_direction != context_direction:
        return False
    return True


def active_alert_setup_for_symbol(
    alerts: pd.DataFrame,
    setups: pd.DataFrame,
    symbol: str,
) -> Optional[pd.Series]:
    if alerts.empty or setups.empty or "setup_id" not in alerts.columns or "id" not in setups.columns:
        return None
    symbol_alerts = alerts[alerts["symbol"] == symbol].copy()
    if symbol_alerts.empty:
        return None
    symbol_alerts = symbol_alerts[symbol_alerts.apply(alert_is_active, axis=1)]
    if symbol_alerts.empty:
        return None
    setup_lookup = setups.set_index("id", drop=False)
    symbol_alerts = symbol_alerts[
        symbol_alerts.apply(
            lambda alert: is_current_approved_telegram_alert(
                alert.to_dict(),
                setup_for_alert(alert, setup_lookup),
                alert_threshold=settings.alert_threshold,
            ),
            axis=1,
        )
    ]
    if symbol_alerts.empty:
        return None
    symbol_alerts = symbol_alerts.sort_values("created_at", ascending=False)
    for _, alert in symbol_alerts.iterrows():
        try:
            setup_id = int(alert.get("setup_id"))
        except (TypeError, ValueError):
            continue
        if setup_id not in setup_lookup.index:
            continue
        setup = setup_lookup.loc[setup_id].copy()
        setup["alert_created_at"] = alert.get("created_at")
        setup["alert_id"] = alert.get("id")
        setup["delivered"] = alert.get("delivered")
        return setup
    return None


def setup_for_alert(alert: Union[pd.Series, dict], setup_lookup: pd.DataFrame) -> dict:
    try:
        setup_id = int(alert.get("setup_id"))
    except (TypeError, ValueError):
        return {}
    if setup_lookup.empty or setup_id not in setup_lookup.index:
        return {}
    setup = setup_lookup.loc[setup_id]
    if isinstance(setup, pd.DataFrame):
        setup = setup.iloc[0]
    return setup.to_dict()


def approved_telegram_alert_rows(
    alerts: pd.DataFrame,
    setups: pd.DataFrame,
    *,
    alert_threshold: int,
) -> pd.DataFrame:
    if alerts.empty or setups.empty or "setup_id" not in alerts.columns or "id" not in setups.columns:
        return pd.DataFrame(columns=alerts.columns)
    setup_lookup = setups.set_index("id", drop=False)
    mask = alerts.apply(
        lambda alert: is_current_approved_telegram_alert(
            alert.to_dict(),
            setup_for_alert(alert, setup_lookup),
            alert_threshold=alert_threshold,
        ),
        axis=1,
    )
    return alerts[mask].copy()


def setup_rows_for_alerts(alerts: pd.DataFrame, fallback_setups: pd.DataFrame) -> pd.DataFrame:
    if alerts.empty or "setup_id" not in alerts.columns:
        return fallback_setups
    setup_ids = sorted(
        {
            safe_int(value)
            for value in alerts["setup_id"].tolist()
            if safe_int(value) > 0
        }
    )
    if not setup_ids:
        return fallback_setups
    placeholders = ",".join("?" for _ in setup_ids)
    with store.connect() as conn:
        rows = conn.execute(
            f"select * from setups where id in ({placeholders})",
            setup_ids,
        ).fetchall()
    exact_setups = pd.DataFrame([dict(row) for row in rows])
    if exact_setups.empty:
        return fallback_setups
    return exact_setups


def render_alert_cards(alerts_frame: pd.DataFrame) -> None:
    recent_alerts = alerts_frame.sort_values("created_at", ascending=False).head(20)
    for _, alert in recent_alerts.iterrows():
        title = (
            f"{alert['symbol']} {alert['direction']} | "
            f"{alert['confidence']}/100 | {format_datetime(alert['created_at'])}"
        )
        with st.expander(title):
            a1, a2, a3 = st.columns(3)
            a1.metric("Setup", alert["setup_type"])
            a2.metric("Confidence", f"{alert['confidence']}/100")
            a3.metric("Delivered", "Yes" if int(alert["delivered"]) else "No")
            link_action(f"Open {alert['symbol']} Chart", tradingview_url(alert["symbol"]))
            st.text(alert["message"])


def prioritize_market_setups(symbol_setups: pd.DataFrame) -> pd.DataFrame:
    if symbol_setups.empty:
        return symbol_setups
    candidates = symbol_setups.copy()
    candidates = candidates[candidates.apply(setup_is_active, axis=1)]
    if candidates.empty:
        return candidates
    status_priority = {"alert_ready": 0, "watch_only": 1, "candidate": 2, "blocked": 3}
    candidates["_status_priority"] = candidates["status"].map(status_priority).fillna(2)
    candidates["_confidence_sort"] = pd.to_numeric(candidates["confidence"], errors="coerce").fillna(0)
    return candidates.sort_values(
        ["created_at", "_status_priority", "_confidence_sort"],
        ascending=[False, True, False],
    )


def latest_symbol_scan_entry(heartbeat: Optional[dict], symbol: str) -> tuple:
    if not heartbeat:
        return "missing", "Scanner has not recorded a recent scan yet."
    try:
        summary = json.loads(heartbeat.get("summary_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        summary = {}
    for key in ("no_trade", "watch_only", "errors", "alerts"):
        prefixes = (f"{symbol}:", f"Core Model {symbol}:", f"Carter Squeeze {symbol}:")
        for item in summary.get(key) or []:
            text = str(item)
            if text.startswith(prefixes):
                return key, text
    return "none", "No fresh setup candidate in the current scanner window."


def latest_symbol_scan_note(heartbeat: Optional[dict], symbol: str) -> str:
    return latest_symbol_scan_entry(heartbeat, symbol)[1]


def heartbeat_no_trade_overrides_setup(
    heartbeat: Optional[dict],
    symbol: str,
    setup: Optional[Union[pd.Series, dict]],
) -> bool:
    if setup is None:
        return False
    scan_key, _ = latest_symbol_scan_entry(heartbeat, symbol)
    if scan_key != "no_trade":
        return False
    heartbeat_time = parse_datetime(heartbeat.get("completed_at") if heartbeat else None)
    setup_time = parse_datetime(setup.get("created_at"))
    return bool(heartbeat_time and setup_time and heartbeat_time > setup_time)


def safe_latest_scan_heartbeat() -> Optional[dict]:
    try:
        return cached_latest_dashboard_heartbeat(
            str(settings.database_file),
            dashboard_database_signature(),
        )
    except (OSError, sqlite3.Error) as exc:
        logger.warning("Dashboard heartbeat read failed: %s", exc)
        return None


def latest_symbol_candle(symbol: str, timeframe: str = "1m") -> Optional[dict]:
    try:
        return cached_latest_dashboard_candle(
            str(settings.database_file),
            symbol,
            timeframe,
            dashboard_database_signature(),
        )
    except (OSError, sqlite3.Error) as exc:
        logger.warning("Dashboard candle read failed for %s %s: %s", symbol, timeframe, exc)
        return None


def latest_symbol_candles(symbols: list[str], timeframe: str = "1m") -> dict[str, Optional[dict]]:
    try:
        return cached_latest_dashboard_candles(
            str(settings.database_file),
            tuple(symbols),
            timeframe,
            dashboard_database_signature(),
        )
    except (OSError, sqlite3.Error) as exc:
        logger.warning("Dashboard candle batch read failed for %s: %s", timeframe, exc)
        return {symbol: None for symbol in symbols}


class DashboardHeartbeatStore:
    def latest_scan_heartbeat(self) -> Optional[dict]:
        return safe_latest_scan_heartbeat()


def dashboard_runtime_status():
    return lightweight_dashboard_status(settings, DashboardHeartbeatStore())


def render_no_trade_card(
    symbol: str,
    note: str,
    candle: Optional[dict] = None,
) -> None:
    candle = candle if candle is not None else latest_symbol_candle(symbol)
    market_label = "Market data unavailable"
    market_status = "warn"
    if candle:
        price = f"{safe_float(candle.get('close')):.2f}"
        freshness = format_datetime(candle.get("timestamp"))
        volume = f"{safe_int(candle.get('volume')):,}"
        meta = f"Last 1m close {price} | {freshness} | Vol {volume}"
        candle_dt = parse_datetime(candle.get("timestamp"))
        if candle_dt:
            age_minutes = max(
                (datetime.now(timezone.utc).astimezone(DISPLAY_TZ) - candle_dt).total_seconds() / 60.0,
                0.0,
            )
            if age_minutes <= settings.stale_data_minutes:
                market_label = "Market data updating"
                market_status = "ok"
            else:
                market_label = "Last stored market data"
    else:
        meta = "No recent 1m candle found."
    st.markdown(
        f"""
        <div class="mini-card">
          <div class="status-row" style="margin-top:0;">
            {pill("NO TRADE", "warn")}
            {pill(market_label, market_status)}
          </div>
          <p class="card-title">{escape(symbol)}: no fresh A+ setup</p>
          <p class="card-meta">{escape(meta)}</p>
          <p class="reason-text" style="margin:8px 0 0 0;">{escape(note)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def send_telegram_test_message() -> tuple:
    telegram = TelegramClient()
    result = telegram.send_message(
        TELEGRAM_TEST_MESSAGE,
        max_attempts=settings.telegram_max_attempts,
        retry_delay_seconds=settings.telegram_retry_delay_seconds,
    )
    store.insert_telegram_attempt(
        symbol="SYSTEM",
        message=TELEGRAM_TEST_MESSAGE,
        delivered=result.delivered,
        attempt_number=result.attempts,
        error=result.error,
    )
    return result.delivered, result.error


def notification_diagnostics() -> dict:
    with store.connect() as conn:
        alerts = dict(
            conn.execute(
                "select count(*) as count, max(created_at) as latest from alerts"
            ).fetchone()
        )
        attempts = dict(
            conn.execute(
                """
                select count(*) as count, max(attempted_at) as latest,
                       sum(case when delivered = 1 then 1 else 0 end) as delivered_count,
                       sum(case when delivered = 0 then 1 else 0 end) as failed_count
                from telegram_delivery_attempts
                """
            ).fetchone()
        )
        setups = dict(
            conn.execute(
                "select count(*) as count, max(created_at) as latest, max(confidence) as max_confidence from setups"
            ).fetchone()
        )
        alert_ready = dict(
            conn.execute(
                """
                select count(*) as count, max(created_at) as latest
                from setups
                where status = 'alert_ready' and confidence >= ?
                """,
                (settings.alert_threshold,),
            ).fetchone()
        )
        blocked_near = dict(
            conn.execute(
                """
                select count(*) as count, max(created_at) as latest
                from setups
                where status = 'blocked' and confidence >= ?
                """,
                (settings.alert_threshold - 1,),
            ).fetchone()
        )
        latest_heartbeat = dict(
            conn.execute(
                """
                select completed_at, status, alerts_count, watch_only_count, no_trade_count, errors_count
                from scanner_heartbeats
                order by id desc
                limit 1
                """
            ).fetchone()
            or {}
        )
        top_setup = dict(
            conn.execute(
                """
                select created_at, symbol, setup_type, direction, confidence, status, market_condition
                from setups
                order by confidence desc, created_at desc
                limit 1
                """
            ).fetchone()
            or {}
        )
    return {
        "alerts": alerts,
        "attempts": attempts,
        "setups": setups,
        "alert_ready": alert_ready,
        "blocked_near": blocked_near,
        "latest_heartbeat": latest_heartbeat,
        "top_setup": top_setup,
    }


def render_notification_diagnostics() -> None:
    diagnostics = notification_diagnostics()
    attempts = diagnostics["attempts"]
    setups = diagnostics["setups"]
    alert_ready = diagnostics["alert_ready"]
    blocked_near = diagnostics["blocked_near"]
    top_setup = diagnostics["top_setup"]
    heartbeat = diagnostics["latest_heartbeat"]

    st.subheader("Notification Diagnostics")
    ncols = st.columns(5)
    ncols[0].metric("Trade Alerts Sent", diagnostics["alerts"].get("count") or 0)
    ncols[1].metric("Telegram Attempts", attempts.get("count") or 0)
    ncols[2].metric("Delivered Tests/Alerts", attempts.get("delivered_count") or 0)
    ncols[3].metric("Highest Score", f"{setups.get('max_confidence') or 0}/100")
    ncols[4].metric("Alert Threshold", f"{settings.alert_threshold}/100")

    if (alert_ready.get("count") or 0) == 0:
        st.info(
            "No Telegram trade alerts have been sent because no setup has reached "
            f"alert-ready status at {settings.alert_threshold}/100 or higher."
        )
    if (blocked_near.get("count") or 0) > 0:
        st.warning(
            f"{blocked_near['count']} setup(s) reached {settings.alert_threshold - 1}/100 while blocked. "
            "That usually means a no-trade filter, stale data, weak volume, opening range, or chop filter stopped it."
        )
    if top_setup:
        with st.expander("Highest Recorded Setup"):
            render_setup_summary(top_setup)
            link_action(f"Open {top_setup['symbol']} Chart", tradingview_url(top_setup["symbol"]))
    if heartbeat:
        st.caption(
            "Latest scan: "
            f"{format_datetime(heartbeat.get('completed_at'))} | "
            f"alerts {heartbeat.get('alerts_count', 0)} | "
            f"watch-only {heartbeat.get('watch_only_count', 0)} | "
            f"no-trade {heartbeat.get('no_trade_count', 0)} | "
            f"errors {heartbeat.get('errors_count', 0)}"
        )
    st.caption(
        "Telegram is limited to core 100/100 Liquidity Sweep Reversal alerts on 15m/30m "
        "and Carter Squeeze puts. Watch-only and experimental setups stay in the dashboard."
    )


def parse_json_value(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def setup_features(row: Union[pd.Series, dict]) -> dict:
    return parse_json_value(row.get("features_json"), {})


def setup_source_label(row: Union[pd.Series, dict]) -> str:
    features = setup_features(row)
    return safe_text(features.get("source_label"), CORE_SOURCE_LABEL)


def research_summary_with_fast_momentum_note(summary: str) -> str:
    text = str(summary or "").strip()
    enabled = bool(settings.strategy.get("fast_momentum_overrides_risk_blocks", False))
    if not enabled or MOMENTUM_EXCEPTION_TITLE in text:
        return text
    if not text:
        return MOMENTUM_EXCEPTION_NOTE
    return f"{text}\n\n{MOMENTUM_EXCEPTION_NOTE}"


def paper_metadata(row) -> dict:
    return parse_json_value(row.get("metadata_json"), {})


def paper_source_label(row) -> str:
    metadata = paper_metadata(row)
    return safe_text(metadata.get("source_label"), CORE_SOURCE_LABEL)


def paper_target_label(row) -> str:
    metadata = paper_metadata(row)
    paper_target = metadata.get("paper_target1")
    if paper_target not in (None, ""):
        return f"{safe_float(paper_target):.2f}"
    return f"{safe_float(row.get('target1')):.2f}"


def experiment_candidate_rows(setups: pd.DataFrame, *, limit: int = 25) -> pd.DataFrame:
    if setups.empty:
        return pd.DataFrame()
    candidates = setups.copy()
    candidates["_status"] = candidates["status"].astype(str).str.lower()
    candidates = candidates[candidates["_status"].isin({"watch_only", "candidate"})]
    if candidates.empty:
        return pd.DataFrame()
    candidates["source_label"] = candidates.apply(setup_source_label, axis=1)
    candidates["created"] = candidates["created_at"].apply(format_datetime)
    candidates["entry"] = candidates.apply(
        lambda row: f"{safe_float(row.get('entry_low')):.2f}-{safe_float(row.get('entry_high')):.2f}",
        axis=1,
    )
    candidates["stop"] = candidates["stop_loss"].apply(lambda value: f"{safe_float(value):.2f}")
    candidates["target"] = candidates["target1"].apply(lambda value: f"{safe_float(value):.2f}")
    candidates["_confidence_sort"] = pd.to_numeric(candidates["confidence"], errors="coerce").fillna(0)
    candidates = candidates.sort_values(
        ["created_at", "_confidence_sort"],
        ascending=[False, False],
    )
    return candidates[
        [
            "created",
            "source_label",
            "symbol",
            "direction",
            "setup_type",
            "timeframe",
            "confidence",
            "status",
            "entry",
            "stop",
            "target",
            "market_condition",
        ]
    ].head(limit)


def latest_watch_only_notes(heartbeats: pd.DataFrame) -> list:
    if heartbeats.empty:
        return []
    latest = heartbeats.sort_values("completed_at", ascending=False).iloc[0]
    try:
        summary = json.loads(latest.get("summary_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in summary.get("watch_only") or []]


def paper_summary_row(label: str, summary: dict) -> dict:
    closed = summary.get("win_rate_sample_size", summary.get("closed_alerted_count", 0))
    return {
        "Source": label,
        "Alerts": summary.get("alerted_count", 0),
        "Closed": closed,
        "Win Rate": f"{summary.get('win_rate', 0):.1f}%" if closed else "No Closed",
        "Total R": f"{summary.get('total_r', 0):.2f}",
        "Profit Factor": summary.get("profit_factor", 0),
        "Avg Winner": f"{summary.get('avg_winner_r', 0):.2f}R",
        "Avg Loser": f"{summary.get('avg_loser_r', 0):.2f}R",
        "Max DD": f"{summary.get('max_drawdown_r', 0):.2f}R",
        "Expectancy": f"{summary.get('expectancy_r', 0):.2f}R",
    }


def format_profit_factor(value) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"
    if numeric == float("inf"):
        return "Inf"
    return f"{numeric:.2f}"


def experimental_lane_summary_rows(summaries: list[dict]) -> pd.DataFrame:
    rows = []
    for summary in summaries:
        gates = summary.get("graduation_gates") or {}
        passed = sum(1 for value in gates.values() if value)
        total = len(gates) or 5
        closed = int(summary.get("closed_signals") or 0)
        rows.append(
            {
                "Lane": summary.get("source_label"),
                "Status": summary.get("graduation_status"),
                "Open": int(summary.get("open_signals") or 0),
                "Closed": closed,
                "Wins": int(summary.get("wins") or 0),
                "Losses": int(summary.get("losses") or 0),
                "Win Rate": f"{summary.get('win_rate', 0):.1f}%" if closed else "No Closed",
                "Profit Factor": format_profit_factor(summary.get("profit_factor")),
                "Expectancy": f"{summary.get('expectancy_r', 0):.2f}R",
                "Trading Days": int(summary.get("trading_days") or 0),
                "Graduation Progress": f"{passed}/{total} gates",
            }
        )
    return pd.DataFrame(rows)


def experimental_lane_events_table(events: list[dict], *, closed: bool) -> pd.DataFrame:
    if not events:
        return pd.DataFrame()
    table = pd.DataFrame(events)
    if table.empty:
        return pd.DataFrame()
    if closed:
        table = table[table["outcome"].isin(["win", "loss", "breakeven", "not_triggered"])]
    else:
        table = table[table["outcome"] == "open"]
    if table.empty:
        return pd.DataFrame()
    table["alert_time"] = table["event_time"].apply(format_datetime)
    table["source_label"] = table.apply(paper_source_label, axis=1)
    table["entry"] = table.apply(
        lambda row: f"{safe_float(row.get('entry_low')):.2f}-{safe_float(row.get('entry_high')):.2f}",
        axis=1,
    )
    table["stop"] = table["stop_loss"].apply(lambda value: f"{safe_float(value):.2f}")
    table["target"] = table.apply(paper_target_label, axis=1)
    table["r"] = table["r_multiple"].apply(lambda value: f"{safe_float(value):.2f}R")
    return table[
        [
            "alert_time",
            "source_label",
            "symbol",
            "direction",
            "setup_type",
            "outcome",
            "confidence",
            "r",
            "entry",
            "stop",
            "target",
        ]
    ].head(50)


def latest_research_by_phase(session_date: Optional[str] = None) -> dict:
    briefs = rows("research_briefs", 50)
    if session_date:
        briefs = [brief for brief in briefs if brief.get("session_date") == session_date]
    by_phase = {}
    for brief in sorted(briefs, key=lambda item: item.get("created_at", ""), reverse=True):
        by_phase.setdefault(brief.get("phase"), brief)
    return by_phase


def current_research_phase_key() -> str:
    now = datetime.now(ZoneInfo(settings.timezone))
    return phase_for_datetime(now, settings.research.get("phase_times", {}))


def run_research_from_dashboard(phase: str) -> str:
    agent = ResearchAgent(settings, store)
    result = agent.run_phase(phase, send_email=True)
    if result.get("status") == "skipped":
        return f"{PHASE_LABELS.get(phase, phase)} skipped: {result.get('reason')}"
    email_status = result.get("email_status", "not_requested")
    return (
        f"{PHASE_LABELS.get(phase, phase)} saved. "
        f"Decision {result.get('decision')} | risk {result.get('risk_score')}/100 | email {email_status}."
    )


def send_research_test_email() -> str:
    result = ResearchAgent(settings, store).send_test_email()
    if result.get("delivered"):
        return "Research test email delivered."
    if result.get("status") == "not_configured":
        return f"Research email needs setup: {result.get('error')}"
    return f"Research test email failed: {result.get('error')}"


def source_chips(source_status: dict, brief: dict) -> str:
    statuses = dict(source_status or {})
    statuses.setdefault("openai_summary", brief.get("openai_status", "not_requested"))
    statuses.setdefault("email_delivery", brief.get("email_status", "not_requested"))
    if not bool(settings.openai_summary.get("enabled", True)):
        statuses["openai_summary"] = "local_summary"
    if missing_research_email_settings():
        statuses["email_delivery"] = "not_configured"
    else:
        latest_email_status = latest_research_email_status()
        if latest_email_status:
            statuses["email_delivery"] = latest_email_status
    labels = {
        "economic_calendar": "Fed/BLS calendar",
        "market_structure": "SPY/QQQ/IWM",
        "volatility": "VIX",
        "news_sentiment": "News",
        "earnings_options": "Earnings/options",
        "fear_greed_proxy": "Fear/greed",
        "openai_summary": "OpenAI summary",
        "email_delivery": "Email",
    }
    return " ".join(
        pill(f"{labels.get(key, key)}: {source_status_label(status, key)}", status)
        for key, status in statuses.items()
    )


def source_status_label(status: str, source: str = "") -> str:
    value = str(status or "unknown").replace("_", " ").strip().title()
    if status == "ok":
        return "OK"
    if status == "missing" and source == "news_sentiment":
        return "Needs Key"
    if status == "missing_api_key" and source == "openai_summary":
        return "Needs OpenAI Key"
    if status in {"disabled", "local_summary"} and source == "openai_summary":
        return "Local Summary"
    if status == "not_configured" and source == "email_delivery":
        return "Needs Setup"
    if status == "ready" and source == "email_delivery":
        return "Ready"
    if status == "not_requested":
        return "Not Run"
    return value or "Unknown"


def latest_research_email_status() -> Optional[str]:
    attempts = rows("research_email_attempts", 1)
    if not attempts:
        return "ready"
    return "delivered" if int(attempts[0].get("delivered") or 0) else "failed"


def missing_research_email_settings() -> list:
    if not bool(settings.email.get("enabled", True)):
        return []
    return GmailSMTPClient(settings).validate_configuration()


def research_setup_warnings() -> list:
    warnings = []
    if bool(settings.openai_summary.get("enabled", True)) and not os.environ.get("OPENAI_API_KEY"):
        warnings.append(
            "OpenAI summary needs OPENAI_API_KEY in .env. Until then, the bot uses the safe local summary."
        )
    missing_email = missing_research_email_settings()
    if missing_email:
        warnings.append(
            "Email needs setup: "
            + ", ".join(missing_email)
            + ". Research emails will not send until these are added to .env."
        )
    return warnings


def render_research_phase_card(phase: str, brief: Optional[dict]) -> None:
    label = PHASE_LABELS.get(phase, phase.title())
    if not brief:
        st.markdown(
            f"""
            <div class="mini-card">
              <p class="card-title">{escape(label)}</p>
              <p class="card-meta">No brief recorded yet.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    drivers = parse_json_value(brief.get("drivers_json"), [])
    risk_warnings = parse_json_value(brief.get("hard_blocks_json"), [])
    st.markdown(
        f"""
        <div class="mini-card">
          <div class="status-row" style="margin-top:0;">
            {pill(label, brief.get("decision", "info"))}
            {pill(str(brief.get("risk_score", "-")) + "/100 risk", "fail" if int(brief.get("risk_score") or 0) >= 65 else "warn" if int(brief.get("risk_score") or 0) >= 40 else "ok")}
            {pill(str(brief.get("bias", "neutral")), "info")}
          </div>
          <p class="card-meta">{escape(format_datetime(brief.get("created_at")))}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for driver in drivers[:3]:
        st.caption(driver)
    if risk_warnings:
        st.warning("Risk warning: " + " | ".join(str(block) for block in risk_warnings[:2]))


def render_research_tab() -> None:
    message = st.session_state.pop("research_action_message", None)
    if message:
        st.info(message)

    session_date = current_session_date(settings).isoformat()
    by_phase = latest_research_by_phase(session_date)
    current_phase_key = current_research_phase_key()
    latest = by_phase.get(current_phase_key) or store.latest_research_brief(session_date=session_date)
    st.subheader("Research")
    st.caption(
        "Research phase cards are snapshots. Updating a phase overwrites that phase with the market conditions at the time you run it."
    )
    for setup_warning in research_setup_warnings():
        st.warning(setup_warning)

    if not latest:
        st.info("No market research brief has been generated yet.")
        latest = {}

    trade_today = bool(latest.get("trade_today")) if latest else False
    decision_label = "Yes" if trade_today else "No"
    current_phase = PHASE_LABELS.get(str(latest.get("phase", "")), "-") if latest else "-"
    risk_value = f"{latest.get('risk_score', '-')}/100" if latest else "-"
    bias_value = str(latest.get("bias", "-")).title() if latest else "-"
    snapshot_time = format_datetime(latest.get("created_at")) if latest else "-"
    st.markdown(
        f"""
        <div class="research-grid">
          <div class="research-metric">
            <p class="research-metric-label">Trade Today?</p>
            <p class="research-metric-value">{escape(decision_label)}</p>
          </div>
          <div class="research-metric">
            <p class="research-metric-label">Risk Score</p>
            <p class="research-metric-value">{escape(risk_value)}</p>
          </div>
          <div class="research-metric">
            <p class="research-metric-label">Bias</p>
            <p class="research-metric-value">{escape(bias_value)}</p>
          </div>
          <div class="research-metric">
            <p class="research-metric-label">Active Snapshot</p>
            <p class="research-metric-value">{escape(current_phase)}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Active research snapshot saved: {snapshot_time}")

    if latest:
        source_status = parse_json_value(latest.get("source_status_json"), {})
        research_summary = research_summary_with_fast_momentum_note(str(latest.get("summary", "")))
        st.markdown(
            f"""
            <div class="mini-card">
              <p class="card-title">Why This Matters</p>
              <p class="reason-text">{escape(research_summary)}</p>
              <div class="status-row">{source_chips(source_status, latest)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    allow_non_current_phase_update = st.checkbox(
        "Allow overwriting a non-current phase snapshot",
        value=False,
        help="Use this only when you intentionally want to replace an old phase with the current market snapshot.",
    )
    action_cols = st.columns(len(PHASES) + 1)
    for index, phase in enumerate(PHASES):
        is_current_phase = phase == current_phase_key
        disabled = not is_current_phase and not allow_non_current_phase_update
        label = (
            f"Run Current {PHASE_LABELS[phase]}"
            if is_current_phase
            else f"Overwrite {PHASE_LABELS[phase]}"
        )
        if action_cols[index].button(
            label,
            use_container_width=True,
            key=f"research_run_{phase}",
            disabled=disabled,
        ):
            st.session_state["research_action_message"] = run_research_from_dashboard(phase)
            st.rerun()
    if action_cols[len(PHASES)].button("Send Test Email", use_container_width=True, key="research_test_email"):
        st.session_state["research_action_message"] = send_research_test_email()
        st.rerun()

    phase_cols = st.columns(len(PHASES))
    for index, phase in enumerate(PHASES):
        with phase_cols[index]:
            render_research_phase_card(phase, by_phase.get(phase))

    if latest:
        with st.expander("Raw Research Evidence"):
            evidence = parse_json_value(latest.get("evidence_json"), [])
            if evidence:
                show_table(pd.DataFrame(evidence), height=360)
            else:
                st.info("No raw evidence recorded.")


scanner_stale_after_seconds = max(settings.scan_cadence_seconds * 10, 1800)
runtime_preview = dashboard_runtime_status()

inject_styles()
render_intro(runtime_preview.status, runtime_preview.scanner_running)

DASHBOARD_VIEWS = [
    "Health",
    "Research",
    "Market",
    "Alerts",
    "Journal",
    "Performance",
    "Breakdowns",
    "Paper",
    "Improve",
]
requested_view_param = st.query_params.get(DASHBOARD_VIEW_QUERY_PARAM)
selected_view = normalize_dashboard_view(
    requested_view_param,
    DASHBOARD_VIEWS,
    "Market",
)
if requested_view_param != selected_view:
    st.query_params[DASHBOARD_VIEW_QUERY_PARAM] = selected_view
render_dashboard_navigation(DASHBOARD_VIEWS, selected_view)
enable_auto_refresh()

if selected_view == "Health":
    st.subheader("Scanner Controls")
    control_message = None

    c1, c2, c3, c4, c5 = st.columns(5)
    if c1.button("Start Scanner", use_container_width=True, key="health_start_scanner"):
        result = start_scanner()
        control_message = ("success" if result.running else "warning", result.message)
    if c2.button("Stop Scanner", use_container_width=True, key="health_stop_scanner"):
        result = stop_scanner()
        control_message = ("success", result.message)
    if c3.button("Run Scan Now", use_container_width=True, key="health_run_scan_now"):
        with st.spinner("Running one scanner cycle..."):
            result = run_scan_once()
        scan_summary = summarize_scan_result(result)
        if scan_summary.success:
            st.success(scan_summary.status_message)
        else:
            st.error(scan_summary.status_message)
        if scan_summary.stdout:
            st.code(scan_summary.stdout)
        if scan_summary.diagnostics:
            if scan_summary.success:
                st.warning("Scan completed with nonfatal diagnostics.")
                with st.expander("Technical diagnostics"):
                    st.code(scan_summary.diagnostics)
            else:
                st.code(scan_summary.diagnostics)
    if c4.button("Refresh Status", use_container_width=True, key="health_refresh_status"):
        st.cache_data.clear()
        with st.spinner("Refreshing live status..."):
            st.session_state["full_healthcheck_result"] = run_healthcheck(settings, store)
        control_message = (
            "success",
            "status refreshed from live scanner, database, and watchdog state",
        )
    if c5.button("Send Test", use_container_width=True, key="health_send_telegram_test"):
        delivered, error = send_telegram_test_message()
        if delivered:
            control_message = ("success", "Telegram test delivered.")
        else:
            control_message = ("warning", f"Telegram test failed: {error}")

    runtime_status = dashboard_runtime_status()
    pcols = st.columns(5)
    pcols[0].metric("Scanner", "Running" if runtime_status.scanner_running else "Stopped")
    pcols[1].metric("PID", runtime_status.scanner_pid or "-")
    pcols[2].metric(
        "Last Scan",
        format_datetime(runtime_status.latest_heartbeat_completed_at)
        if runtime_status.latest_heartbeat_completed_at
        else "-",
    )
    pcols[3].metric("Cadence", format_cadence(int(settings.scan_cadence_seconds)))
    pcols[4].metric("Alert Frames", ", ".join(settings.alert_timeframes))
    st.caption(f"Process log: {DEFAULT_LOG_FILE}")

    if control_message:
        level, message = control_message
        if level == "success":
            st.success(message)
        else:
            st.warning(message)

    st.subheader("Runtime Health")
    if st.button("Run Full Healthcheck", use_container_width=True, key="health_run_full_check"):
        with st.spinner("Running full healthcheck..."):
            st.session_state["full_healthcheck_result"] = run_healthcheck(settings, store)

    health = st.session_state.get("full_healthcheck_result")
    if health:
        hcols = st.columns(4)
        hcols[0].metric("System", health["status"].upper())
        hcols[1].metric("Checked", format_datetime(health["checked_at"]))
        hcols[2].metric("Database", Path(health["database"]).name)
        hcols[3].metric("Dashboard Refreshed", format_datetime(datetime.now(timezone.utc)))

        for check in health["checks"]:
            render_check_card(check)
    else:
        st.info("Full healthcheck is on demand so the dashboard can open quickly.")

    render_notification_diagnostics()

    with st.expander("Recent Scanner Heartbeats"):
        heartbeats = df("scanner_heartbeats", 20)
        if heartbeats.empty:
            st.info("No scanner heartbeat recorded yet.")
        else:
            show_table(
                heartbeats[
                    [
                        "completed_at",
                        "status",
                        "alerts_count",
                        "watch_only_count",
                        "no_trade_count",
                        "errors_count",
                    ]
                ],
                height=360,
            )

if selected_view == "Research":
    render_research_tab()

if selected_view == "Market":
    st.subheader("Market Monitor")
    market_data = dashboard_frames(
        {
            "setups": 300,
            "alerts": 200,
            "levels": 240,
            "daily_market_reviews": 30,
        }
    )
    latest_setups = market_data["setups"]
    latest_alerts = market_data["alerts"]
    latest_levels = market_data["levels"]
    latest_reviews = market_data["daily_market_reviews"]
    latest_heartbeat = safe_latest_scan_heartbeat()
    latest_candles = latest_symbol_candles(list(settings.symbols))

    chart_cols = st.columns(len(settings.symbols))
    for index, symbol in enumerate(settings.symbols):
        with chart_cols[index]:
            link_action(f"Open {symbol} Chart", tradingview_url(symbol))

    cols = st.columns(3)
    for idx, symbol in enumerate(settings.symbols):
        symbol_setups = (
            latest_setups[latest_setups["symbol"] == symbol]
            if not latest_setups.empty
            else pd.DataFrame()
        )
        if not symbol_setups.empty:
            symbol_setups = prioritize_market_setups(symbol_setups)
        active_alert_setup = active_alert_setup_for_symbol(latest_alerts, latest_setups, symbol)
        latest_context = symbol_setups.iloc[0] if not symbol_setups.empty else None
        no_trade_overrides_context = heartbeat_no_trade_overrides_setup(
            latest_heartbeat,
            symbol,
            latest_context,
        )
        if no_trade_overrides_context:
            latest_context = None
            symbol_setups = pd.DataFrame()
        if active_alert_setup is not None and not alert_still_matches_market(active_alert_setup, latest_context):
            active_alert_setup = None
        symbol_levels = (
            latest_levels[latest_levels["symbol"] == symbol]
            if not latest_levels.empty
            else pd.DataFrame()
        )
        with cols[idx]:
            st.markdown(f"### {symbol}")
            symbol_candle = latest_candles.get(symbol)
            setup_view, alert_view, levels_view = st.tabs(["Current Setup", "Active Alert", "Levels"])
            with setup_view:
                if latest_context is not None:
                    render_setup_summary(latest_context, compact=True, candle=symbol_candle)
                    with st.expander("Current Setup Details"):
                        render_setup_summary(latest_context, candle=symbol_candle)
                        link_action(f"Open {symbol} on TradingView", tradingview_url(symbol))
                else:
                    render_no_trade_card(
                        symbol,
                        latest_symbol_scan_note(latest_heartbeat, symbol),
                        symbol_candle,
                    )
            with alert_view:
                if active_alert_setup is not None:
                    st.caption(
                        f"Active Telegram alert from {format_datetime(active_alert_setup.get('alert_created_at'))}"
                    )
                    render_setup_summary(active_alert_setup, compact=True, candle=symbol_candle)
                    with st.expander("Active Alert Details"):
                        render_setup_summary(active_alert_setup, candle=symbol_candle)
                        link_action(f"Open {symbol} on TradingView", tradingview_url(symbol))
                else:
                    st.info("No active Telegram alert for this symbol.")
                    st.caption(latest_symbol_scan_note(latest_heartbeat, symbol))
                    link_action(f"Open {symbol} on TradingView", tradingview_url(symbol))
            with levels_view:
                if symbol_levels.empty:
                    st.info("No key levels recorded yet.")
                else:
                    compact = symbol_levels[["name", "price", "timeframe", "session_date"]].head(8)
                    show_table(compact, height=260)
                    link_action(f"Open {symbol} on TradingView", tradingview_url(symbol))

    st.subheader("No-Trade / Daily Review")
    if latest_reviews.empty:
        st.info("No daily market reviews recorded yet.")
    else:
        show_table(latest_reviews.sort_values("created_at", ascending=False), height=340)

if selected_view == "Alerts":
    st.subheader("Alerts")
    alerts = df("alerts", 200)
    setups = df("setups", 300)
    attempts = df("telegram_delivery_attempts", 200)
    alert_setups = setup_rows_for_alerts(alerts, setups)
    approved_alerts = approved_telegram_alert_rows(
        alerts,
        alert_setups,
        alert_threshold=settings.alert_threshold,
    )
    legacy_alerts = (
        alerts[~alerts["id"].isin(approved_alerts["id"])]
        if not alerts.empty and not approved_alerts.empty
        else alerts.copy()
        if approved_alerts.empty
        else pd.DataFrame(columns=alerts.columns)
    )

    st.markdown("#### Approved Telegram Alerts")
    st.caption(
        "Current rule: core 100/100 Liquidity Sweep Reversal on 15m/30m, "
        "Carter Squeeze puts, and management alerts only for approved Telegram entries."
    )
    if approved_alerts.empty:
        st.info("No current-rule Telegram alerts have been recorded yet.")
    else:
        render_alert_cards(approved_alerts)

    st.markdown("#### Legacy / Excluded Telegram Attempts")
    st.caption(
        "Older alerts or attempts that do not meet the current Telegram rule. "
        "Use these for audit/history, not as approved alert quality."
    )
    if legacy_alerts.empty:
        st.info("No legacy or excluded Telegram attempts in the recent history.")
    else:
        render_alert_cards(legacy_alerts)

    st.subheader("Watch-Only Setups")
    if setups.empty:
        st.info("No setup candidates yet.")
    else:
        watch = setups.sort_values("created_at", ascending=False).head(25)
        for _, setup in watch.iterrows():
            title = (
                f"{setup['symbol']} {setup['direction']} {setup['setup_type']} | "
                f"{setup['confidence']}/100 | {format_datetime(setup['created_at'])}"
            )
            with st.expander(title):
                render_setup_summary(setup)
                link_action(f"Open {setup['symbol']} Chart", tradingview_url(setup["symbol"]))

    with st.expander("Telegram Delivery Attempts"):
        if attempts.empty:
            st.info("No Telegram delivery attempts recorded yet.")
        else:
            show_table(attempts.sort_values("attempted_at", ascending=False), height=360)

    st.subheader("Alert Review")
    if approved_alerts.empty:
        st.info("No alert to review yet.")
    else:
        alert_options = approved_alerts.sort_values("created_at", ascending=False).copy()
        alert_options["label"] = alert_options.apply(
            lambda row: (
                f"#{row['id']} {row['symbol']} {row['direction']} "
                f"{row['confidence']}/100 - {format_datetime(row['created_at'])}"
            ),
            axis=1,
        )
        with st.form("alert_review_form", clear_on_submit=True):
            alert_label = st.selectbox("Alert", alert_options["label"].tolist(), key="alert_review_alert")
            alert_id = int(alert_options[alert_options["label"] == alert_label].iloc[0]["id"])
            col1, col2, col3 = st.columns(3)
            review_status = col1.selectbox("Status", ["needs_review", "taken", "ignored", "avoided"], key="alert_review_status")
            outcome = col2.selectbox("Outcome", ["pending", "win", "loss", "breakeven", "not_triggered"], key="alert_review_outcome")
            r_multiple = col3.number_input("R multiple", step=0.25, key="alert_review_r_multiple")
            emotional_state = st.text_input("Review emotional state", key="alert_review_emotional_state")
            mistake_tags = st.multiselect(
                "Review mistake tags",
                MISTAKE_TAG_OPTIONS,
                key="alert_review_mistake_tags",
            )
            notes = st.text_area("Alert review notes", key="alert_review_notes")
            submitted = st.form_submit_button("Save Alert Review")
            if submitted:
                store.upsert_alert_review(
                    alert_id=alert_id,
                    review_status=review_status,
                    outcome=outcome,
                    r_multiple=r_multiple,
                    notes=notes,
                    emotional_state=emotional_state,
                    mistake_tags=mistake_tags,
                )
                st.success("Alert review saved.")
                st.cache_resource.clear()

    reviews = df("alert_reviews", 200)
    if not reviews.empty:
        with st.expander("Saved Alert Reviews"):
            show_table(reviews.sort_values("reviewed_at", ascending=False), height=360)

if selected_view == "Journal":
    st.subheader("Manual Trade Journal")
    if st.session_state.get("journal_flash"):
        st.success(st.session_state.pop("journal_flash"))

    st.markdown("### Eva's Index Alert Trading Bot Commandments")
    st.caption("Capture what you are learning, then promote the strongest rules into your permanent trading commandments.")
    rules = list_trading_rule_entries(store)
    commandments = [
        rule
        for rule in rules
        if safe_text(rule.get("status")) == "commandment"
    ]
    commandments = sorted(
        commandments,
        key=lambda rule: (
            safe_int(rule.get("commandment_order")) or 99,
            safe_text(rule.get("updated_at")),
        ),
    )[:10]

    if commandments:
        st.markdown("#### Eva's 10 Commandments")
        for index, rule in enumerate(commandments, start=1):
            order = safe_int(rule.get("commandment_order")) or index
            st.markdown(f"**{order}.** {safe_text(rule.get('rule_text'))}")
            notes_text = safe_text(rule.get("notes"))
            if notes_text:
                st.caption(notes_text)
    else:
        st.info("No commandments yet. Add a rule below and mark it as a commandment when it earns a permanent spot.")

    with st.form("trading_rule_form", clear_on_submit=True):
        rule_text = st.text_area(
            "New rule or lesson",
            placeholder="Example: I do not trade the first 15 minutes unless structure is extremely clean.",
            key="trading_rule_text",
        )
        rule_cols = st.columns(3)
        rule_category = rule_cols[0].selectbox(
            "Category",
            ["when_to_trade", "when_not_to_trade", "risk_management", "psychology", "execution"],
            key="trading_rule_category",
        )
        make_commandment = rule_cols[1].checkbox(
            "Add to commandments",
            key="trading_rule_make_commandment",
        )
        commandment_order = rule_cols[2].number_input(
            "Commandment number",
            min_value=1,
            max_value=10,
            value=min(len(commandments) + 1, 10),
            step=1,
            disabled=not make_commandment,
            key="trading_rule_order",
        )
        rule_notes = st.text_input(
            "Why this rule matters",
            key="trading_rule_notes",
        )
        save_rule = st.form_submit_button("Save Rule")
        if save_rule:
            if not rule_text.strip():
                st.warning("Type the rule before saving it.")
            else:
                add_trading_rule_entry(
                    store,
                    rule_text=rule_text,
                    category=rule_category,
                    status="commandment" if make_commandment else "draft",
                    commandment_order=int(commandment_order) if make_commandment else None,
                    notes=rule_notes,
                )
                st.session_state["journal_flash"] = "Trading rule saved."
                st.cache_resource.clear()
                rerun_dashboard()

    if rules:
        with st.expander("Rule Library", expanded=False):
            for rule in rules:
                rule_id = int(rule["id"])
                with st.form(f"trading_rule_edit_{rule_id}"):
                    current_status = safe_text(rule.get("status"), "draft")
                    current_category = safe_text(rule.get("category"), "when_to_trade")
                    category_options = [
                        "when_to_trade",
                        "when_not_to_trade",
                        "risk_management",
                        "psychology",
                        "execution",
                    ]
                    status_options = ["draft", "commandment", "retired"]
                    edited_text = st.text_area(
                        f"Rule #{rule_id}",
                        value=safe_text(rule.get("rule_text")),
                        key=f"trading_rule_text_{rule_id}",
                    )
                    edit_cols = st.columns(4)
                    edited_category = edit_cols[0].selectbox(
                        "Category",
                        category_options,
                        index=option_index(category_options, current_category),
                        key=f"trading_rule_category_{rule_id}",
                    )
                    edited_status = edit_cols[1].selectbox(
                        "Status",
                        status_options,
                        index=option_index(status_options, current_status),
                        key=f"trading_rule_status_{rule_id}",
                    )
                    edited_order = edit_cols[2].number_input(
                        "Commandment number",
                        min_value=1,
                        max_value=10,
                        value=safe_int(rule.get("commandment_order")) or 1,
                        step=1,
                        disabled=edited_status != "commandment",
                        key=f"trading_rule_order_{rule_id}",
                    )
                    delete_rule = edit_cols[3].checkbox(
                        "Remove",
                        key=f"trading_rule_delete_{rule_id}",
                    )
                    edited_notes = st.text_input(
                        "Why this rule matters",
                        value=safe_text(rule.get("notes")),
                        key=f"trading_rule_notes_{rule_id}",
                    )
                    save_rule_edit = st.form_submit_button("Save Rule Changes")
                    if save_rule_edit:
                        if delete_rule:
                            delete_trading_rule_entry(store, rule_id)
                            st.session_state["journal_flash"] = f"Rule #{rule_id} removed."
                        elif not edited_text.strip():
                            st.warning("Rule text cannot be blank.")
                        else:
                            update_trading_rule_entry(
                                store,
                                rule_id=rule_id,
                                rule_text=edited_text,
                                category=edited_category,
                                status=edited_status,
                                commandment_order=int(edited_order) if edited_status == "commandment" else None,
                                notes=edited_notes,
                            )
                            st.session_state["journal_flash"] = f"Rule #{rule_id} updated."
                        st.cache_resource.clear()
                        rerun_dashboard()

    st.divider()

    with st.form("trade_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        symbol = col1.selectbox("Ticker", settings.symbols, key="trade_symbol")
        setup_type = col2.text_input("Setup type", "manual", key="trade_setup_type")
        direction = col3.selectbox("Direction", ["LONG", "SHORT"], key="trade_direction")
        col4, col5, col6 = st.columns(3)
        entry_price = col4.number_input("Entry price", min_value=0.0, step=0.01, key="trade_entry_price")
        exit_price = col5.number_input("Exit price", min_value=0.0, step=0.01, key="trade_exit_price")
        quantity = col6.number_input("Contracts / shares", min_value=0.0, step=1.0, key="trade_quantity")
        col7, col8, col9 = st.columns(3)
        realized_pl = col7.number_input("Realized P/L", step=1.0, key="trade_realized_pl")
        confidence = col8.number_input("Alert confidence", min_value=0, max_value=100, value=0, key="trade_confidence")
        market_condition = col9.text_input("Market condition", "unknown", key="trade_market_condition")
        emotional_state = st.text_input("Emotional state", key="trade_emotional_state")
        mistake_tags = st.multiselect(
            "Mistake tags",
            MISTAKE_TAG_OPTIONS,
            key="trade_mistake_tags",
        )
        notes = st.text_area("Notes / lesson learned", key="trade_notes")
        submitted = st.form_submit_button("Add Trade")
        if submitted:
            journal.add_trade(
                symbol=symbol,
                setup_type=setup_type,
                direction=direction,
                realized_pl=realized_pl,
                entry_price=entry_price or None,
                exit_price=exit_price or None,
                quantity=quantity or None,
                confidence=confidence or None,
                market_condition=market_condition,
                notes=notes,
                emotional_state=emotional_state,
                mistake_tags=mistake_tags,
                closed_at=datetime.utcnow().replace(microsecond=0),
            )
            st.success("Trade added.")
            st.cache_resource.clear()

    trades = df("trades", 500)
    st.subheader("Journal History")
    if trades.empty:
        st.info("No trades journaled yet.")
    else:
        recent_trades = trades.sort_values("opened_at", ascending=False).head(30)
        for _, trade in recent_trades.iterrows():
            trade_id = int(trade["id"])
            pl = safe_float(trade.get("realized_pl"))
            title = (
                f"#{trade_id} {trade['symbol']} {trade['direction']} | "
                f"${pl:,.2f} | {format_datetime(trade['opened_at'])}"
            )
            with st.expander(title):
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("Setup", trade["setup_type"])
                t2.metric("P/L", f"${pl:,.2f}")
                t3.metric("Entry", display_optional_number(trade.get("entry_price")))
                t4.metric("Exit", display_optional_number(trade.get("exit_price")))
                st.write(safe_text(trade.get("notes"), "No notes."))
                emotional_label = safe_text(trade.get("emotional_state"))
                if emotional_label:
                    st.caption(f"Emotional state: {emotional_label}")
                link_action(f"Open {trade['symbol']} Chart", tradingview_url(trade["symbol"]))

                st.divider()
                st.markdown("#### Edit Entry")
                opened_local = parse_datetime(trade.get("opened_at")) or datetime.now(timezone.utc).astimezone(DISPLAY_TZ)
                closed_local = parse_datetime(trade.get("closed_at"))
                closed_default = closed_local or datetime.now(timezone.utc).astimezone(DISPLAY_TZ)
                saved_tags = [str(tag) for tag in parse_json_value(trade.get("mistake_tags_json"), [])]
                tag_options = list(dict.fromkeys(MISTAKE_TAG_OPTIONS + saved_tags))
                symbol_options = list(dict.fromkeys(settings.symbols + [safe_text(trade.get("symbol"))]))
                direction_options = list(dict.fromkeys(["LONG", "SHORT", safe_text(trade.get("direction"), "LONG")]))

                with st.form(f"edit_trade_form_{trade_id}"):
                    edit_cols = st.columns(3)
                    edit_symbol = edit_cols[0].selectbox(
                        "Ticker",
                        symbol_options,
                        index=option_index(symbol_options, safe_text(trade.get("symbol"), settings.symbols[0])),
                        key=f"edit_trade_symbol_{trade_id}",
                    )
                    edit_setup_type = edit_cols[1].text_input(
                        "Setup type",
                        value=safe_text(trade.get("setup_type"), "manual"),
                        key=f"edit_trade_setup_{trade_id}",
                    )
                    edit_direction = edit_cols[2].selectbox(
                        "Direction",
                        direction_options,
                        index=option_index(direction_options, safe_text(trade.get("direction"), "LONG")),
                        key=f"edit_trade_direction_{trade_id}",
                    )

                    time_cols = st.columns(4)
                    opened_date = time_cols[0].date_input(
                        "Opened date",
                        value=opened_local.date(),
                        key=f"edit_trade_opened_date_{trade_id}",
                    )
                    opened_time = time_cols[1].time_input(
                        "Opened time",
                        value=opened_local.time().replace(microsecond=0),
                        key=f"edit_trade_opened_time_{trade_id}",
                    )
                    is_closed = time_cols[2].checkbox(
                        "Closed",
                        value=closed_local is not None,
                        key=f"edit_trade_is_closed_{trade_id}",
                    )
                    took_trade = time_cols[3].checkbox(
                        "I took this trade",
                        value=bool(safe_int(trade.get("took_trade"))),
                        key=f"edit_trade_took_{trade_id}",
                    )

                    close_cols = st.columns(2)
                    closed_date = close_cols[0].date_input(
                        "Closed date",
                        value=closed_default.date(),
                        disabled=not is_closed,
                        key=f"edit_trade_closed_date_{trade_id}",
                    )
                    closed_time = close_cols[1].time_input(
                        "Closed time",
                        value=closed_default.time().replace(microsecond=0),
                        disabled=not is_closed,
                        key=f"edit_trade_closed_time_{trade_id}",
                    )

                    price_cols = st.columns(4)
                    edit_entry = price_cols[0].number_input(
                        "Entry price",
                        min_value=0.0,
                        step=0.01,
                        value=safe_float(trade.get("entry_price")),
                        key=f"edit_trade_entry_{trade_id}",
                    )
                    edit_exit = price_cols[1].number_input(
                        "Exit price",
                        min_value=0.0,
                        step=0.01,
                        value=safe_float(trade.get("exit_price")),
                        key=f"edit_trade_exit_{trade_id}",
                    )
                    edit_quantity = price_cols[2].number_input(
                        "Contracts / shares",
                        min_value=0.0,
                        step=1.0,
                        value=safe_float(trade.get("quantity")),
                        key=f"edit_trade_quantity_{trade_id}",
                    )
                    edit_pl = price_cols[3].number_input(
                        "Realized P/L",
                        step=1.0,
                        value=safe_float(trade.get("realized_pl")),
                        key=f"edit_trade_pl_{trade_id}",
                    )

                    context_cols = st.columns(2)
                    edit_confidence = context_cols[0].number_input(
                        "Alert confidence",
                        min_value=0,
                        max_value=100,
                        value=safe_int(trade.get("confidence")),
                        key=f"edit_trade_confidence_{trade_id}",
                    )
                    edit_market_condition = context_cols[1].text_input(
                        "Market condition",
                        value=safe_text(trade.get("market_condition"), "unknown"),
                        key=f"edit_trade_market_{trade_id}",
                    )

                    edit_emotional_state = st.text_input(
                        "Emotional state",
                        value=safe_text(trade.get("emotional_state")),
                        key=f"edit_trade_emotion_{trade_id}",
                    )
                    edit_tags = st.multiselect(
                        "Mistake tags",
                        tag_options,
                        default=saved_tags,
                        key=f"edit_trade_tags_{trade_id}",
                    )
                    edit_notes = st.text_area(
                        "Notes / lesson learned",
                        value=safe_text(trade.get("notes")),
                        key=f"edit_trade_notes_{trade_id}",
                    )

                    save_edit = st.form_submit_button("Save Changes")
                    if save_edit:
                        journal.edit_trade(
                            trade_id=trade_id,
                            symbol=edit_symbol,
                            setup_type=edit_setup_type or "manual",
                            direction=edit_direction,
                            opened_at=to_storage_datetime(opened_date, opened_time),
                            closed_at=to_storage_datetime(closed_date, closed_time) if is_closed else None,
                            took_trade=took_trade,
                            realized_pl=edit_pl,
                            entry_price=optional_float(edit_entry),
                            exit_price=optional_float(edit_exit),
                            quantity=optional_float(edit_quantity),
                            confidence=optional_confidence(edit_confidence),
                            market_condition=edit_market_condition or "unknown",
                            notes=edit_notes,
                            emotional_state=edit_emotional_state,
                            mistake_tags=edit_tags,
                        )
                        st.session_state["journal_flash"] = f"Trade #{trade_id} updated."
                        st.cache_resource.clear()
                        rerun_dashboard()

                st.markdown("#### Remove Entry")
                st.caption(
                    "This permanently removes the trade from the journal and performance analytics."
                )
                with st.form(f"remove_trade_form_{trade_id}"):
                    confirm_delete = st.checkbox(
                        f"Yes, remove trade #{trade_id}",
                        key=f"remove_trade_confirm_{trade_id}",
                    )
                    remove_submitted = st.form_submit_button("Remove Journal Entry")
                    if remove_submitted:
                        if not confirm_delete:
                            st.warning("Check the confirmation box before removing this entry.")
                        elif remove_trade_entry(store, trade_id):
                            st.session_state["journal_flash"] = f"Trade #{trade_id} removed."
                            st.cache_resource.clear()
                            rerun_dashboard()
                        else:
                            st.warning("That trade was already removed.")

if selected_view == "Performance":
    st.subheader("Performance")
    trades = df("trades", 500).to_dict("records")
    metrics = calculate_metrics(trades)
    mcols = st.columns(5)
    mcols[0].metric("Total P/L", f"${metrics['total_pl']:,.2f}")
    mcols[1].metric("Win Rate", f"{metrics['win_rate']:.1f}%")
    mcols[2].metric("Expectancy", f"${metrics['expectancy']:,.2f}")
    mcols[3].metric("Profit Factor", metrics["profit_factor"])
    mcols[4].metric("Max Drawdown", f"${metrics['max_drawdown']:,.2f}")

    equity = pd.DataFrame(metrics["equity_curve"])
    if not equity.empty:
        import plotly.express as px

        equity["opened_at_dt"] = equity["opened_at"].apply(parse_datetime)
        fig = px.line(equity, x="opened_at_dt", y="equity", title="Equity Curve")
        fig.update_layout(
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            margin=dict(l=20, r=20, t=50, b=20),
            xaxis_title=None,
            yaxis_title="Equity",
        )
        st.plotly_chart(fig, use_container_width=True)

    periods = period_pl(trades)
    for name in ["daily", "weekly", "monthly"]:
        render_period_summary_cards(name, periods[name])

if selected_view == "Breakdowns":
    st.subheader("Breakdown Analytics")
    trades = df("trades", 500).to_dict("records")
    data = breakdowns(trades)
    for name, metrics_by_group in data.items():
        st.markdown(f"#### {name.replace('_', ' ').title()}")
        table = pd.DataFrame(
            [{"group": group, **metrics} for group, metrics in metrics_by_group.items()]
        )
        breakdown_table = table.drop(columns=["equity_curve"], errors="ignore")
        if "total_pl" in breakdown_table.columns:
            breakdown_table = breakdown_table.sort_values("total_pl", ascending=False)
        render_breakdown_metric_cards(breakdown_table)

if selected_view == "Paper":
    st.subheader("Paper Trading: Current Rules")
    st.caption(
        "This view shows current-rule paper W/L by lane. "
        "Older replay/backtest rows and blocked setup families stay archived in SQLite but are not included in these headline scores."
    )
    excluded_setups = set(getattr(settings, "excluded_setup_types", []) or [])
    live_summary, live_event_rows = live_paper.current_live_100_snapshot(store, excluded_setups)
    live_events = pd.DataFrame(live_event_rows)

    st.markdown("### Core Strict Liquidity Sweep Paper Trades")
    tracking_since = "-"
    if not live_events.empty:
        tracking_since = format_datetime(live_events["event_time"].min(), include_relative=False)
    live_cols = st.columns(8)
    closed_live = live_summary.get("closed", 0)
    live_win_rate = (
        f"{live_summary.get('wins', 0) / closed_live * 100:.1f}%"
        if closed_live
        else "No Closed Trades"
    )
    live_cols[0].metric("Core Alerts", live_summary.get("alerted", 0))
    live_cols[1].metric("Wins", live_summary.get("wins", 0))
    live_cols[2].metric("Losses", live_summary.get("losses", 0))
    live_cols[3].metric("Expired", live_summary.get("expired_daytrade", 0))
    live_cols[4].metric("Still Open", live_summary.get("open", 0))
    live_cols[5].metric("Not Triggered", live_summary.get("not_triggered", 0))
    live_cols[6].metric("Win Rate", live_win_rate)
    live_cols[7].metric("Tracking Since", tracking_since)
    st.caption(
        "This section only counts 100/100 Liquidity Sweep Reversal rows on 15m/30m. "
        "Fast Momentum, premarket/previous-day breaks, VWAP, 1h liquidity, and experimental lanes are excluded from core. "
        "A win means the +1R paper target hit after entry triggered. "
        "A loss means stop hit first. Expired means a triggered day trade did not hit target or stop before the same-day cutoff. "
        "Open means entry triggered but target/stop has not resolved yet during the active session. "
        "Raw historical rows remain archived for research."
    )
    if live_events.empty:
        st.info("No current-rule core paper trades have been recorded yet.")
    else:
        readable_live = live_events.copy()
        readable_live["alert_time"] = readable_live["event_time"].apply(format_datetime)
        readable_live["entry"] = readable_live.apply(
            lambda row: f"{safe_float(row.get('entry_low')):.2f}-{safe_float(row.get('entry_high')):.2f}",
            axis=1,
        )
        readable_live["stop"] = readable_live["stop_loss"].apply(lambda value: f"{safe_float(value):.2f}")
        readable_live["target"] = readable_live.apply(paper_target_label, axis=1)
        readable_live["r"] = readable_live["r_multiple"].apply(lambda value: f"{safe_float(value):.2f}R")
        readable_live["source_label"] = readable_live.apply(paper_source_label, axis=1)
        live_columns = [
            "alert_time",
            "source_label",
            "symbol",
            "direction",
            "setup_type",
            "outcome",
            "r",
            "entry",
            "stop",
            "target",
        ]
        st.markdown("#### Core Strict Trade List")
        for _, event in readable_live.head(12).iterrows():
            with st.container(border=True):
                top_cols = st.columns([1.1, 1.1, 1.1, 2.1, 1, 1])
                top_cols[0].metric("Source", safe_text(event.get("source_label"), CORE_SOURCE_LABEL))
                top_cols[1].metric("Ticker", safe_text(event.get("symbol")))
                top_cols[2].metric("Direction", safe_text(event.get("direction")))
                top_cols[3].metric("Setup", safe_text(event.get("setup_type")))
                top_cols[4].metric("Outcome", safe_text(event.get("outcome")).upper())
                top_cols[5].metric("R", safe_text(event.get("r"), "0.00R"))
                detail_cols = st.columns([1.6, 1, 1, 1, 1])
                detail_cols[0].caption(f"Alert time: {safe_text(event.get('alert_time'))}")
                detail_cols[1].caption(f"Entry: {safe_text(event.get('entry'))}")
                detail_cols[2].caption(f"Stop: {safe_text(event.get('stop'))}")
                detail_cols[3].caption(f"Paper target (+1R): {safe_text(event.get('target'))}")
                with detail_cols[4]:
                    link_action("Open Chart", tradingview_url(safe_text(event.get("symbol"))))
    st.markdown("### Carter Squeeze Put Paper Trades")
    st.caption(
        "Counts only Carter SHORT/put-side paper alerts. Carter call-side remains blocked or watch-only until it earns separate evidence."
    )
    carter_summary, carter_event_rows = live_paper.current_carter_put_snapshot(store)
    carter_events = pd.DataFrame(carter_event_rows)
    carter_tracking_since = "-"
    if not carter_events.empty:
        carter_tracking_since = format_datetime(carter_events["event_time"].min(), include_relative=False)
    carter_cols = st.columns(7)
    carter_closed = carter_summary.get("closed", 0)
    carter_win_rate = (
        f"{carter_summary.get('wins', 0) / carter_closed * 100:.1f}%"
        if carter_closed
        else "No Closed Trades"
    )
    carter_cols[0].metric("Carter Put Alerts", carter_summary.get("alerted", 0))
    carter_cols[1].metric("Wins", carter_summary.get("wins", 0))
    carter_cols[2].metric("Losses", carter_summary.get("losses", 0))
    carter_cols[3].metric("Still Open", carter_summary.get("open", 0))
    carter_cols[4].metric("Not Triggered", carter_summary.get("not_triggered", 0))
    carter_cols[5].metric("Win Rate", carter_win_rate)
    carter_cols[6].metric("Tracking Since", carter_tracking_since)
    if carter_events.empty:
        st.info("No Carter Squeeze put-side paper trades have been recorded yet.")
    else:
        readable_carter = carter_events.copy()
        readable_carter["alert_time"] = readable_carter["event_time"].apply(format_datetime)
        readable_carter["source_label"] = readable_carter.apply(paper_source_label, axis=1)
        readable_carter["entry"] = readable_carter.apply(
            lambda row: f"{safe_float(row.get('entry_low')):.2f}-{safe_float(row.get('entry_high')):.2f}",
            axis=1,
        )
        readable_carter["stop"] = readable_carter["stop_loss"].apply(lambda value: f"{safe_float(value):.2f}")
        readable_carter["target"] = readable_carter.apply(paper_target_label, axis=1)
        readable_carter["r"] = readable_carter["r_multiple"].apply(lambda value: f"{safe_float(value):.2f}R")
        show_table(
            readable_carter[
                [
                    "alert_time",
                    "source_label",
                    "symbol",
                    "direction",
                    "setup_type",
                    "outcome",
                    "r",
                    "entry",
                    "stop",
                    "target",
                ]
            ].head(25),
            height=260,
        )
    st.markdown("### Failed Auction Trap Paper Trades")
    st.caption(
        "Dashboard-only experimental lane. These rows are paper-tracked for evidence; "
        "Telegram is unchanged until the lane graduates."
    )
    trap_summary, trap_event_rows = live_paper.current_failed_auction_trap_snapshot(store)
    trap_events = pd.DataFrame(trap_event_rows)
    trap_tracking_since = "-"
    if not trap_events.empty:
        trap_tracking_since = format_datetime(trap_events["event_time"].min(), include_relative=False)
    trap_cols = st.columns(7)
    trap_closed = trap_summary.get("closed", 0)
    trap_win_rate = (
        f"{trap_summary.get('wins', 0) / trap_closed * 100:.1f}%"
        if trap_closed
        else "No Closed Trades"
    )
    trap_cols[0].metric("Trap Signals", trap_summary.get("alerted", 0))
    trap_cols[1].metric("Wins", trap_summary.get("wins", 0))
    trap_cols[2].metric("Losses", trap_summary.get("losses", 0))
    trap_cols[3].metric("Still Open", trap_summary.get("open", 0))
    trap_cols[4].metric("Not Triggered", trap_summary.get("not_triggered", 0))
    trap_cols[5].metric("Win Rate", trap_win_rate)
    trap_cols[6].metric("Tracking Since", trap_tracking_since)
    if trap_events.empty:
        st.info("No Failed Auction Trap paper trades have been recorded yet.")
    else:
        readable_trap = trap_events.copy()
        readable_trap["alert_time"] = readable_trap["event_time"].apply(format_datetime)
        readable_trap["source_label"] = readable_trap.apply(paper_source_label, axis=1)
        readable_trap["entry"] = readable_trap.apply(
            lambda row: f"{safe_float(row.get('entry_low')):.2f}-{safe_float(row.get('entry_high')):.2f}",
            axis=1,
        )
        readable_trap["stop"] = readable_trap["stop_loss"].apply(lambda value: f"{safe_float(value):.2f}")
        readable_trap["target"] = readable_trap.apply(paper_target_label, axis=1)
        readable_trap["r"] = readable_trap["r_multiple"].apply(lambda value: f"{safe_float(value):.2f}R")
        show_table(
            readable_trap[
                [
                    "alert_time",
                    "source_label",
                    "symbol",
                    "direction",
                    "setup_type",
                    "outcome",
                    "r",
                    "entry",
                    "stop",
                    "target",
                ]
            ].head(25),
            height=260,
        )

    st.markdown("### Experiment Bench")
    st.caption(
        "Setups here are not promoted alert lanes. They are monitored separately so they can earn evidence without changing the core score."
    )
    st.text_area(
        "Promotion rules to become an alert lane",
        value=EXPERIMENT_PROMOTION_RULES,
        height=265,
        disabled=True,
        key="experiment_promotion_rules",
    )

    st.markdown("#### Experimental Lane Paper Evidence")
    st.caption(
        "These are dashboard-only lanes collecting paper evidence. "
        "They stay out of Telegram and out of the core score until they pass every gate and Eva approves promotion."
    )
    experimental_summaries = live_paper.experimental_lane_summaries(store)
    experimental_summary_table = experimental_lane_summary_rows(experimental_summaries)
    if experimental_summary_table.empty:
        st.info("No experimental lane paper evidence has been recorded yet.")
    else:
        show_table(experimental_summary_table, height=220)

    experimental_events = []
    for summary in experimental_summaries:
        experimental_events.extend(
            live_paper.list_live_experimental_lane_paper_events(
                store,
                summary["paper_source"],
            )
        )

    open_experiment_events = experimental_lane_events_table(
        experimental_events,
        closed=False,
    )
    closed_experiment_events = experimental_lane_events_table(
        experimental_events,
        closed=True,
    )
    lane_cols = st.columns(2)
    with lane_cols[0]:
        st.markdown("##### Open Experimental Signals")
        if open_experiment_events.empty:
            st.info("No open experimental signals right now.")
        else:
            show_table(open_experiment_events, height=300)
    with lane_cols[1]:
        st.markdown("##### Closed Experimental Results")
        if closed_experiment_events.empty:
            st.info("No closed experimental results yet.")
        else:
            show_table(closed_experiment_events, height=300)

    st.markdown("#### Current Non-Alert Candidates")
    experiment_setups = experiment_candidate_rows(df("setups", 300))
    if experiment_setups.empty:
        st.info("No watch-only or candidate experiment setups are active in the latest stored setup window.")
    else:
        show_table(experiment_setups, height=320)

    with st.expander("Latest Scanner Watch-Only Notes", expanded=False):
        load_watch_notes = st.checkbox(
            "Load latest watch-only scanner notes",
            key="paper_load_watch_notes",
        )
        if load_watch_notes:
            watch_notes = latest_watch_only_notes(df("scanner_heartbeats", 5))
            if not watch_notes:
                st.info("No watch-only notes in the latest scanner heartbeat.")
            else:
                for note in watch_notes:
                    st.write(note)
        else:
            st.caption("Skipped until requested so the Paper page can render faster.")
    st.divider()

    with st.expander("Archived replay/backtest data", expanded=False):
        st.caption(
            "These are older strategy-version rows kept for audit only. "
            "They are intentionally excluded from the current live paper stats above."
        )
        load_archive = st.checkbox(
            "Load archived replay/backtest rows",
            key="paper_load_archived_replay",
        )
        if load_archive:
            runs = df("paper_runs", 100)
            events = df("paper_events", 500)
            live_sources = {
                LIVE_CORE_100_PAPER_SOURCE,
                LIVE_CARTER_PAPER_SOURCE,
                LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE,
            }
            replay_runs = runs[~runs["source"].isin(live_sources)] if not runs.empty else runs
            if replay_runs.empty:
                st.info("No archived replay runs found.")
            else:
                show_table(replay_runs, height=220)
            if not events.empty and not runs.empty:
                replay_ids = set(replay_runs["id"].tolist()) if not replay_runs.empty else set()
                replay_events = events[events["run_id"].isin(replay_ids)]
                if not replay_events.empty:
                    readable_events = replay_events.copy()
                    readable_events["source_label"] = readable_events.apply(paper_source_label, axis=1)
                    show_table(readable_events.sort_values("event_time", ascending=False), height=320)
        else:
            st.caption("Skipped until requested so current-rule paper metrics stay fast.")

if selected_view == "Improve":
    st.subheader("Improvement Lab")
    st.caption("Recommendations are analysis only. They never change live rules unless you review and approve them.")
    engine = RecommendationEngine()
    recommendations = engine.generate(
        df("trades", 500).to_dict("records"),
        df("alerts", 500).to_dict("records"),
    )
    if recommendations:
        for rec in recommendations:
            with st.container(border=True):
                st.write(f"**{rec.title}**")
                st.write(rec.rationale)
                st.write(rec.proposed_change)
                st.caption(
                    f"Metric: {rec.metric} | Current: {rec.before_value} | "
                    f"Sample: {rec.sample_size} | Evidence: {rec.evidence_quality} | "
                    f"Overfitting risk: {rec.overfitting_risk}"
                )
        if st.button("Save Recommendations For Review", key="save_recommendations"):
            for rec in recommendations:
                store.insert_recommendation(rec)
            st.success("Recommendations saved as pending review.")
    else:
        st.info("No recommendations yet. More journaled outcomes will make this useful.")

    saved = df("strategy_recommendations", 100)
    if not saved.empty:
        st.subheader("Saved Recommendations")
        show_table(saved, height=360)
