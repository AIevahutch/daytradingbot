from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.analytics.performance import breakdowns, calculate_metrics, period_pl
from trading_bot.analytics.recommendations import RecommendationEngine
from trading_bot.health import run_healthcheck
from trading_bot.journal.trade_journal import TradeJournal
from trading_bot.settings import load_settings
from trading_bot.storage import SQLiteStore


st.set_page_config(page_title="SPY/QQQ/IWM Alert Bot", layout="wide")


@st.cache_resource
def get_store():
    settings = load_settings()
    return settings, SQLiteStore(settings.database_file)


settings, store = get_store()
journal = TradeJournal(store)


def rows(table: str, limit: int = 500):
    return store.list_rows(table, limit=limit)


def df(table: str, limit: int = 500):
    data = rows(table, limit)
    return pd.DataFrame(data) if data else pd.DataFrame()


st.title("SPY / QQQ / IWM Alert Bot")
st.caption("Alert-only. Manual TradingView confirmation. No automated execution.")

tabs = st.tabs(
    [
        "Health",
        "Market Monitor",
        "Alerts",
        "Journal",
        "Performance",
        "Breakdowns",
        "Paper Trading",
        "Improvement Lab",
    ]
)

with tabs[0]:
    st.subheader("Runtime Health")
    health = run_healthcheck(settings, store)
    st.metric("Status", health["status"].upper())
    st.dataframe(pd.DataFrame(health["checks"]), width="stretch", hide_index=True)

    st.subheader("Scanner Heartbeats")
    heartbeats = df("scanner_heartbeats", 20)
    if heartbeats.empty:
        st.info("No scanner heartbeat recorded yet.")
    else:
        st.dataframe(heartbeats, width="stretch", hide_index=True)

with tabs[1]:
    st.subheader("Market Monitor")
    latest_setups = df("setups", 100)
    latest_levels = df("levels", 200)
    latest_reviews = df("daily_market_reviews", 30)

    cols = st.columns(3)
    for idx, symbol in enumerate(settings.symbols):
        symbol_setups = latest_setups[latest_setups["symbol"] == symbol] if not latest_setups.empty else pd.DataFrame()
        symbol_levels = latest_levels[latest_levels["symbol"] == symbol] if not latest_levels.empty else pd.DataFrame()
        with cols[idx]:
            st.metric(symbol, "Watching")
            if not symbol_setups.empty:
                top = symbol_setups.sort_values("created_at", ascending=False).iloc[0]
                st.write(f"Bias setup: {top['direction']} {top['setup_type']}")
                st.write(f"Confidence: {top['confidence']}/100")
                st.write(f"Condition: {top['market_condition']}")
            else:
                st.write("No setup candidates recorded yet.")
            if not symbol_levels.empty:
                compact = symbol_levels[["name", "price", "timeframe"]].head(8)
                st.dataframe(compact, width="stretch", hide_index=True)

    st.subheader("No-Trade / Daily Review")
    if latest_reviews.empty:
        st.info("No daily market reviews recorded yet.")
    else:
        st.dataframe(latest_reviews, width="stretch", hide_index=True)

with tabs[2]:
    st.subheader("Recent Alerts")
    alerts = df("alerts", 200)
    setups = df("setups", 300)
    if alerts.empty:
        st.info("No Telegram alerts have been recorded yet.")
    else:
        st.dataframe(alerts.sort_values("created_at", ascending=False), width="stretch", hide_index=True)
    st.subheader("Watch-Only Setups")
    if setups.empty:
        st.info("No setup candidates yet.")
    else:
        watch = setups.sort_values("created_at", ascending=False)
        st.dataframe(
            watch[
                [
                    "created_at",
                    "symbol",
                    "setup_type",
                    "direction",
                    "confidence",
                    "risk_reward",
                    "status",
                    "market_condition",
                    "reasoning",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

    st.subheader("Telegram Delivery Attempts")
    attempts = df("telegram_delivery_attempts", 200)
    if attempts.empty:
        st.info("No Telegram delivery attempts recorded yet.")
    else:
        st.dataframe(
            attempts.sort_values("attempted_at", ascending=False),
            width="stretch",
            hide_index=True,
        )

    st.subheader("Alert Review")
    if alerts.empty:
        st.info("No alert to review yet.")
    else:
        alert_ids = alerts.sort_values("created_at", ascending=False)["id"].tolist()
        with st.form("alert_review_form", clear_on_submit=True):
            alert_id = st.selectbox("Alert", alert_ids)
            col1, col2, col3 = st.columns(3)
            review_status = col1.selectbox("Status", ["needs_review", "taken", "ignored", "avoided"])
            outcome = col2.selectbox("Outcome", ["pending", "win", "loss", "breakeven", "not_triggered"])
            r_multiple = col3.number_input("R multiple", step=0.25)
            emotional_state = st.text_input("Review emotional state")
            mistake_tags = st.multiselect(
                "Review mistake tags",
                [
                    "FOMO",
                    "revenge trade",
                    "oversized position",
                    "poor entry",
                    "ignored stop",
                    "emotional trade",
                ],
            )
            notes = st.text_area("Alert review notes")
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
        st.dataframe(reviews, width="stretch", hide_index=True)

with tabs[3]:
    st.subheader("Manual Trade Journal")
    with st.form("trade_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        symbol = col1.selectbox("Ticker", settings.symbols)
        setup_type = col2.text_input("Setup type", "manual")
        direction = col3.selectbox("Direction", ["LONG", "SHORT"])
        col4, col5, col6 = st.columns(3)
        entry_price = col4.number_input("Entry price", min_value=0.0, step=0.01)
        exit_price = col5.number_input("Exit price", min_value=0.0, step=0.01)
        quantity = col6.number_input("Contracts / shares", min_value=0.0, step=1.0)
        col7, col8, col9 = st.columns(3)
        realized_pl = col7.number_input("Realized P/L", step=1.0)
        confidence = col8.number_input("Alert confidence", min_value=0, max_value=100, value=0)
        market_condition = col9.text_input("Market condition", "unknown")
        emotional_state = st.text_input("Emotional state")
        mistake_tags = st.multiselect(
            "Mistake tags",
            [
                "FOMO",
                "revenge trade",
                "oversized position",
                "poor entry",
                "ignored stop",
                "emotional trade",
            ],
        )
        notes = st.text_area("Notes / lesson learned")
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
        st.dataframe(trades.sort_values("opened_at", ascending=False), width="stretch", hide_index=True)

with tabs[4]:
    st.subheader("Performance")
    trades = store.list_trades()
    metrics = calculate_metrics(trades)
    mcols = st.columns(5)
    mcols[0].metric("Total P/L", f"${metrics['total_pl']:.2f}")
    mcols[1].metric("Win Rate", f"{metrics['win_rate']:.1f}%")
    mcols[2].metric("Expectancy", f"${metrics['expectancy']:.2f}")
    mcols[3].metric("Profit Factor", metrics["profit_factor"])
    mcols[4].metric("Max Drawdown", f"${metrics['max_drawdown']:.2f}")

    equity = pd.DataFrame(metrics["equity_curve"])
    if not equity.empty:
        st.plotly_chart(px.line(equity, x="opened_at", y="equity", title="Equity Curve"), width="stretch")
    periods = period_pl(trades)
    pcols = st.columns(3)
    for col, name in zip(pcols, ["daily", "weekly", "monthly"]):
        values = pd.DataFrame(
            [{"period": key, "pl": value} for key, value in periods[name].items()]
        )
        with col:
            st.write(name.title())
            if values.empty:
                st.info("No data")
            else:
                st.dataframe(values.sort_values("period", ascending=False), hide_index=True)

with tabs[5]:
    st.subheader("Breakdown Analytics")
    trades = store.list_trades()
    data = breakdowns(trades)
    for name, metrics_by_group in data.items():
        st.write(name.replace("_", " ").title())
        table = pd.DataFrame(
            [{"group": group, **metrics} for group, metrics in metrics_by_group.items()]
        )
        if table.empty:
            st.info("No data")
        else:
            st.dataframe(table.drop(columns=["equity_curve"], errors="ignore"), width="stretch", hide_index=True)

with tabs[6]:
    st.subheader("Paper Trading Replay")
    runs = df("paper_runs", 100)
    latest_run_id = None
    if not runs.empty:
        latest_run_id = int(runs.sort_values("id", ascending=False).iloc[0]["id"])
    paper_summary = store.paper_summary(latest_run_id)
    if latest_run_id is not None:
        st.caption(f"Showing latest replay run #{latest_run_id}. Historical runs remain below for comparison.")
    cols = st.columns(5)
    cols[0].metric("Replay Alerts", paper_summary["alerted_count"])
    cols[1].metric("Avoided", paper_summary["avoided_count"])
    cols[2].metric("Missed", paper_summary["missed_count"])
    cols[3].metric("Win Rate", f"{paper_summary['win_rate']:.1f}%")
    cols[4].metric("Total R", f"{paper_summary['total_r']:.2f}")

    events = df("paper_events", 500)
    if runs.empty:
        st.info("No replay runs yet. Run `python -m trading_bot replay --from YYYY-MM-DD --to YYYY-MM-DD`.")
    else:
        st.dataframe(runs, width="stretch", hide_index=True)
    if not events.empty:
        st.subheader("Replay Events")
        st.dataframe(
            events.sort_values("event_time", ascending=False),
            width="stretch",
            hide_index=True,
        )

with tabs[7]:
    st.subheader("Reinforcement-Learning-Ready Improvement Lab")
    st.caption("Recommendations are analysis only. They never change live rules unless you review and approve them.")
    engine = RecommendationEngine()
    recommendations = engine.generate(store.list_trades(), store.list_alerts())
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
        if st.button("Save Recommendations For Review"):
            for rec in recommendations:
                store.insert_recommendation(rec)
            st.success("Recommendations saved as pending review.")
    else:
        st.info("No recommendations yet. More journaled outcomes will make this useful.")

    saved = df("strategy_recommendations", 100)
    if not saved.empty:
        st.subheader("Saved Recommendations")
        st.dataframe(saved, width="stretch", hide_index=True)
