# Build Sequence

## Purpose

This file teaches students how to rebuild a similar training version of the current SPY/QQQ/IWM alert-only bot from scratch.

Important: do not apply these rebuild steps to the current repo unless you intentionally start a separate implementation exercise. This course package only documents the current repo.

## Step 1: Define The Alert-Only Contract

Objective: define what the bot is and is not.

Beginner explanation: before code exists, students need a safety boundary. This bot can scan and alert, but it cannot trade.

Files students would create or change in their own rebuild:

- `README.md`
- `docs/safety.md`

Codex prompt:

```text
Create the project contract for a local SPY/QQQ/IWM options alert bot. It must be alert-only, manual-review only, no broker execution, no Robinhood integration, no automatic rule changes, and no profit promises. Write beginner-friendly README language and a safety notice.
```

Expected output: clear project scope and safety language.

How to test the step: ask a classmate to answer, "Can this bot place trades?" The answer must be no.

Common errors: writing language that sounds like trade instructions.

Troubleshooting: search the docs for words like "guarantee," "automatic trade," or "buy now" and rewrite them.

Safety/risk note: alerts are educational decision-support outputs only.

## Step 2: Create The Python Project Skeleton

Objective: set up the package, dependencies, tests folder, config folder, and dashboard folder.

Beginner explanation: the skeleton gives the project predictable places for code, settings, docs, and tests.

Files students would create or change:

- `pyproject.toml`
- `requirements.txt`
- `trading_bot/__init__.py`
- `trading_bot/__main__.py`
- `tests/`
- `dashboard/app.py`
- `config/settings.yaml`

Codex prompt:

```text
Scaffold a Python 3.9+ project named spy-qqq-iwm-alert-bot. Add requirements for streamlit, pandas, numpy, plotly, yfinance, requests, pydantic, python-dotenv, sqlalchemy, apscheduler, and pytest. Add a trading_bot package, tests folder, dashboard folder, and config/settings.yaml. Do not implement trading logic yet.
```

Expected output: project structure imports cleanly.

How to test the step:

```bash
python -m pytest
```

Common errors: missing `__init__.py`, package not on `pythonpath`, or running commands outside the repo.

Safety/risk note: no market data or alerts exist yet.

## Step 3: Add Safe Configuration And Environment Placeholders

Objective: separate non-secret settings from secret credentials.

Beginner explanation: settings like symbols and thresholds belong in config; secrets belong in `.env` and should never be committed.

Files students would create or change:

- `config/settings.yaml`
- `.env.example`
- `.gitignore`

Codex prompt:

```text
Create config/settings.yaml for an alert-only SPY/QQQ/IWM bot. Use symbols SPY, QQQ, IWM; alert_threshold 80; alert_timeframes 15m, 30m, 1h; scan_cadence_seconds 900; database_path data/trading_bot.sqlite; and manual_approval_required_for_rule_changes true. Create .env.example with placeholder values only for Telegram, OpenAI, Gmail, research email, and Alpha Vantage. Do not include real secrets.
```

Expected output: config loads and `.env.example` contains only placeholders.

How to test the step: inspect files and confirm no real tokens, passwords, or keys are present.

Common errors: copying real credentials into examples.

Troubleshooting: rotate any secret that was accidentally shared.

Safety/risk note: credentials are operational risk, not course content.

## Step 4: Build The Storage Layer

Objective: create local SQLite tables for bot state.

Beginner explanation: the dashboard needs history. SQLite gives students a local database without a server.

Files students would create or change:

- `trading_bot/storage.py`
- `data/` runtime folder

Codex prompt:

```text
Build a local SQLite storage layer for the alert-only bot. Store candles, alerts, failed alert attempts, research briefs, replay paper events, journal entries, performance summaries, and pending recommendations. Keep the schema local-first and avoid external databases.
```

Expected output: database can initialize locally.

How to test the step: run a small storage unit test that initializes an empty database in a temp path.

Common errors: hardcoding absolute paths or writing tests to the production DB.

Troubleshooting: use temporary database paths in tests.

Safety/risk note: storage records alerts and manual review. It does not authorize trades.

## Step 5: Build The Market Data Layer

Objective: fetch and normalize SPY/QQQ/IWM data.

Beginner explanation: the bot needs candle data before it can calculate levels or setups.

Files students would create or change:

- `trading_bot/data/market_data.py`
- `tests/test_data_engine.py`

Codex prompt:

```text
Build a yfinance market-data adapter for SPY, QQQ, and IWM. Normalize candle columns, handle empty or stale data, store local candles, and resample raw 1m data into completed 15m, 30m, and 1h candles. Stale data should produce a visible no-trade reason.
```

Expected output: candle data can be fetched, normalized, and resampled.

How to test the step: test resampling, stale-data detection, and empty data handling with mocked candles.

Common errors: using partial candles for alert decisions.

Troubleshooting: print the latest raw candle timestamp and latest completed alert timeframe timestamp.

Safety/risk note: free market data is best-effort and must be manually confirmed.

## Step 6: Add Levels

Objective: calculate technical levels used by setup detection.

Beginner explanation: levels are reference points where the bot checks whether price is reacting.

Files students would create or change:

- `trading_bot/levels/levels.py`
- `tests/test_levels.py`

Codex prompt:

```text
Create a levels module that calculates VWAP, previous day high/low/close, premarket high/low, weekly levels, and gap-fill levels from normalized candles. Add tests with small fixture data.
```

Expected output: levels are deterministic and testable.

How to test the step: compare known fixture candles against expected levels.

Common errors: mixing timezones or using future daily data.

Troubleshooting: show the source candles used for each level.

Safety/risk note: a level is context, not a trade signal by itself.

## Step 7: Add Setup Detection

Objective: identify candidate setups before scoring.

Beginner explanation: a candidate is something to inspect, not something to trade.

Files students would create or change:

- `trading_bot/strategy/engine.py`
- `trading_bot/models.py`
- `tests/test_strategy_scoring_alerts.py`

Codex prompt:

```text
Build setup detection for SPY/QQQ/IWM alert candidates. Include VWAP reclaim/reject, level break/hold, liquidity sweep reversal, failed breakout/breakdown, momentum continuation, and Strat-style continuation. Return structured SetupSignal objects with direction, entry zone, stop, targets, invalidation, reasoning, and context.
```

Expected output: fixture candles can produce setup candidates.

How to test the step: create fixture scenarios for each setup type.

Common errors: sending alerts directly from setup detection.

Troubleshooting: keep setup detection separate from scoring and alert delivery.

Safety/risk note: a setup candidate can still be blocked.

## Step 8: Add No-Trade Filters

Objective: block low-quality conditions.

Beginner explanation: good bots spend a lot of time saying no.

Files students would create or change:

- `trading_bot/psychology/no_trade.py`
- `tests/test_no_trade_and_analytics.py`

Codex prompt:

```text
Build no-trade filters for stale data, compressed chop, weak volume, overextension, poor risk/reward, conflicting timeframes, mixed SPY/QQQ/IWM confirmation, opening noise, midday lull, and late close-window entries. Return explicit reasons so the dashboard can explain why no alert was sent.
```

Expected output: bad conditions return clear blockers.

How to test the step: fixture scenarios for each blocker.

Common errors: hiding no-trade reasons from the user.

Troubleshooting: record all blockers and warnings on the setup object.

Safety/risk note: no-trade is a correct outcome.

## Step 9: Add Scoring And Alert Eligibility

Objective: convert candidates into watch-only, blocked, or alert-ready records.

Beginner explanation: scoring ranks setup quality and prevents marginal alerts.

Files students would create or change:

- `trading_bot/scoring/scoring.py`
- `trading_bot/scoring/selection.py`
- `tests/test_strategy_scoring_alerts.py`

Codex prompt:

```text
Create a confidence scoring layer for setup candidates. Add positive weights for clean setup, timeframe continuity, level confluence, VWAP confirmation, volume confirmation, market confirmation, and risk/reward. Add penalties for weak volume, chop, conflicting timeframes, overextension, stale data, weak setup categories, and research conflict. Only 80+ setups with no hard blocker can be alert-eligible.
```

Expected output: `79` remains below alert eligibility; `80+` is only eligible if no hard block exists.

How to test the step: test sub-80 suppression, 80+ eligibility, hard blockers, and cooldowns.

Common errors: treating confidence as permission to trade.

Troubleshooting: show score components and hard blockers separately.

Safety/risk note: confidence is a filter, not a guarantee.

## Step 10: Add Research Risk Gate

Objective: use research as a conservative blocker or penalty.

Beginner explanation: news, macro, Fed, CPI/jobs, VIX, and missing sources can make conditions riskier.

Files students would create or change:

- `trading_bot/research/`
- `trading_bot/summaries.py`
- `trading_bot/email/`
- `tests/test_research_agent.py`

Codex prompt:

```text
Build a research module for premarket, midday, and EOD briefs. Collect or represent macro calendar, Fed events, CPI/jobs risk, news sentiment, earnings/options context, VIX/volatility, fear/greed proxy, and SPY/QQQ/IWM tape. Produce risk_score, bias, trade_today, decision, drivers, hard_blocks, source_status, and evidence. Missing same-day research should block alerts when configured. OpenAI may summarize only; rules remain the source of truth.
```

Expected output: research can block, penalize, or allow alerts.

How to test the step: mock source failures, high-risk briefs, medium-risk briefs, and bias conflicts.

Common errors: letting AI create trades.

Troubleshooting: inspect `source_status` and `hard_blocks`.

Safety/risk note: AI summaries must not override rule-based risk gates.

## Step 11: Add Telegram Alerts

Objective: format and send manual review alerts.

Beginner explanation: the alert explains what the human should inspect.

Files students would create or change:

- `trading_bot/alerts/telegram.py`
- `tests/test_strategy_scoring_alerts.py`

Codex prompt:

```text
Build Telegram alert formatting and delivery for alert-eligible setups only. Include ticker, setup type, direction, entry zone, stop/invalidation, targets, confidence, risk/reward, reasoning, avoid-if warning, and an alert-only manual-confirmation footer. Add retry persistence for failed sends. Never place orders.
```

Expected output: alert text is clear and manual-review focused.

How to test the step: test alert formatting without calling the real Telegram API.

Common errors: writing "BUY NOW" language.

Troubleshooting: use a mocked Telegram sender in tests.

Safety/risk note: Telegram is a notification channel, not execution.

## Step 12: Add Scanner CLI

Objective: connect settings, data, levels, setup detection, scoring, research, alerts, and storage.

Beginner explanation: the scanner is the main loop.

Files students would create or change:

- `trading_bot/scanner.py`
- `trading_bot/cli.py`
- `trading_bot/__main__.py`

Codex prompt:

```text
Create CLI commands for backfill, scan --once, continuous scan, telegram_test, healthcheck, replay, retry_failed_alerts, paper_summary, and research. The scanner should process only SPY/QQQ/IWM, evaluate completed alert candles, apply no-trade and research gates, score candidates, suppress duplicates/cooldowns/daily caps, send only eligible Telegram alerts, and store all records.
```

Expected output: `python -m trading_bot scan --once` can run the scan path.

How to test the step: unit-test scanner behavior with mocked data and mocked Telegram.

Common errors: calling external APIs in unit tests.

Troubleshooting: split scanner dependencies so they can be mocked.

Safety/risk note: scan commands still do not trade.

## Step 13: Add Replay And Paper Events

Objective: validate behavior offline.

Beginner explanation: replay lets students inspect how rules behaved historically without risking money.

Files students would create or change:

- `trading_bot/replay.py`
- `tests/test_qa_replay_deploy.py`

Codex prompt:

```text
Build historical replay for stored or CSV 1m candles. Replay must walk candles chronologically, evaluate only completed 15m/30m/1h alert timeframe closes, avoid current-day daily lookahead, send no Telegram alerts, and store paper events as alerted, blocked, suppressed, ignored, or missed. Track MFE, MAE, strict outcomes, and tactical +1R outcomes where relevant.
```

Expected output: replay stores paper events without sending alerts.

How to test the step: use fixture candles and assert completed-candle timing.

Common errors: lookahead bias.

Troubleshooting: log replay timestamp, latest 1m candle, and latest completed alert candle.

Safety/risk note: replay is not proof of future profit.

## Step 14: Add Journal And Analytics

Objective: record manual review and outcomes.

Beginner explanation: the human journal is the source of truth for what was actually taken, ignored, won, lost, or mishandled.

Files students would create or change:

- `trading_bot/journal/trade_journal.py`
- `trading_bot/analytics/`
- `tests/test_trade_journal.py`
- `tests/test_no_trade_and_analytics.py`

Codex prompt:

```text
Build a manual trade journal and analytics layer. Track entries, exits, partial exits, contracts/shares, P/L, alert taken or ignored, notes, emotional state, mistake tags, setup performance, market condition, time of day, confidence bucket, expectancy, profit factor, drawdown, and review-only recommendations. Recommendations must stay pending review.
```

Expected output: manual entries and analytics can be reviewed locally.

How to test the step: create journal fixture trades and verify metrics.

Common errors: treating recommendations as automatic rule changes.

Troubleshooting: separate recommendation generation from rule application.

Safety/risk note: analytics can guide review but do not authorize future trades.

## Step 15: Add Dashboard

Objective: create the user-facing review surface.

Beginner explanation: the dashboard helps users see health, alerts, research, replay, journal, and performance.

Files students would create or change:

- `dashboard/app.py`
- `trading_bot/runtime/scanner_process.py`
- `trading_bot/health.py`

Codex prompt:

```text
Build a Streamlit dashboard for the alert-only bot. Include Health, Research, Market Monitor, Alerts, Paper Trading, Journal, Performance, Breakdowns, and Improvement Lab tabs. Add scanner start/stop/run-now controls, health status, Telegram test support, research phase actions, and clear paper/replay safety language.
```

Expected output: dashboard renders locally.

How to test the step: run Streamlit in a local training repo and inspect each tab.

Common errors: dashboard crashes when optional tables are missing.

Troubleshooting: show empty states for optional tables.

Safety/risk note: dashboard metrics are review data, not future guarantees.

## Step 16: Add Validation Docs

Objective: force strict completion checks.

Beginner explanation: a project is not done because it "looks good." It is done when checks pass or blockers are documented.

Files students would create or change:

- `docs/ACCEPTANCE_PROMPT.md`
- `docs/A_PLUS_PRECISION_PROMPT.md`
- `docs/TESTING_VALIDATION_FRAMEWORK.md`

Codex prompt:

```text
Create validation documentation for the SPY/QQQ/IWM alert-only bot. Include a strict PASS / FAIL / BLOCKED acceptance prompt, an A+ precision prompt that prevents one-day overfitting, and a phased validation framework that separates technical validation, replay, live paper trading, statistical validation, and any later small-size live testing.
```

Expected output: validation docs are clear enough for another agent or student to run.

How to test the step: have a student explain why Phase 1 technical validation is not proof of profitability.

Common errors: declaring real-money readiness too early.

Troubleshooting: require sample size, varied market regimes, and owner approval for later phases.

Safety/risk note: no course session teaches live auto-trading.

## Final Rebuild Checklist

Students should be able to explain:

- What command starts a one-cycle scan.
- Where non-secret settings live.
- Why `.env` values are not shared.
- How raw `1m` data becomes completed `15m/30m/1h` alert context.
- Why `SPY`, `QQQ`, and `IWM` are the only symbols.
- Why a setup candidate is not automatically an alert.
- Why research can block or penalize but not create trades.
- Why replay is useful but not predictive proof.
- Why the bot is alert-only and does not place trades.
