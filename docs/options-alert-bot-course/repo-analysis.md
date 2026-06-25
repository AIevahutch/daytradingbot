# Repo Analysis

## Summary

Verified from the repository: this is a Python 3.9+ local alert-only day-trading assistant for `SPY`, `QQQ`, and `IWM`.

The current bot is a software decision-support tool. It scans market data, detects and scores setups, applies risk gates, sends alerts, and records manual review data. It does not place trades.

## Detected Language And Framework

Verified from `pyproject.toml` and `requirements.txt`:

- Language: Python
- Supported Python version: 3.9+
- App framework: Streamlit
- Test framework: pytest
- Data tools: pandas, numpy, yfinance
- Charting/UI support: plotly
- HTTP/API support: requests
- Config/env support: python-dotenv, pydantic
- Scheduling support: apscheduler
- Persistence: local SQLite through Python's `sqlite3`

## Main Dependencies

Declared dependencies:

- `streamlit`
- `pandas`
- `numpy`
- `plotly`
- `yfinance`
- `requests`
- `pydantic`
- `python-dotenv`
- `sqlalchemy`
- `apscheduler`
- `pytest`

Observed implementation note: the storage layer uses Python `sqlite3` directly even though SQLAlchemy is also declared.

## Main Folders

- `trading_bot/`: core Python package.
- `dashboard/`: Streamlit dashboard.
- `config/`: non-secret settings.
- `tests/`: pytest test suite.
- `docs/`: existing validation prompts and testing framework.
- `deploy/`: macOS launchd examples.
- `scripts/`: local helper scripts.
- `data/`: local runtime data such as SQLite database and scanner PID files.

## Main Files

- `README.md`: current product contract, setup, commands, strategy summary, testing, deployment notes.
- `pyproject.toml`: package metadata, Python version, dependencies, pytest configuration.
- `requirements.txt`: install dependency list.
- `config/settings.yaml`: symbols, alert threshold, alert timeframes, cadence, research gates, scoring weights, risk settings.
- `trading_bot/cli.py`: command-line entry points for scan, backfill, healthcheck, replay, Telegram test, research, and paper summary.
- `trading_bot/scanner.py`: live scan orchestration and alert eligibility flow.
- `trading_bot/data/market_data.py`: yfinance data adapter, candle normalization, resampling, and completed-candle handling.
- `trading_bot/levels/levels.py`: VWAP, previous-day, premarket, weekly, and gap levels.
- `trading_bot/strategy/engine.py`: setup detection.
- `trading_bot/scoring/scoring.py`: confidence scoring and hard blockers.
- `trading_bot/psychology/no_trade.py`: no-trade and quality filters.
- `trading_bot/research/`: research evidence, risk scoring, and scanner gating.
- `trading_bot/summaries.py`: optional OpenAI summary generation with deterministic fallback.
- `trading_bot/alerts/telegram.py`: Telegram alert formatting and delivery.
- `trading_bot/storage.py`: SQLite schema and repository operations.
- `trading_bot/replay.py`: historical replay and paper-event creation.
- `trading_bot/journal/trade_journal.py`: manual trade journal support.
- `trading_bot/analytics/`: performance metrics and review-only recommendations.
- `trading_bot/health.py`: healthcheck reporting.
- `trading_bot/runtime/scanner_process.py`: dashboard-managed scanner process control.
- `dashboard/app.py`: Streamlit dashboard tabs and controls.

## Current Configuration Facts

Verified from `config/settings.yaml`:

- Symbols: `SPY`, `QQQ`, `IWM`
- Alert threshold: `80`
- Alert timeframes: `15m`, `30m`, `1h`
- Scan cadence: `900` seconds
- Database path: `data/trading_bot.sqlite`
- Manual rule approval: enabled
- Research gating: enabled
- Summary generation: API-backed OpenAI summaries are configured but disabled by default; the course can use the local/deterministic fallback without asking students for an OpenAI Platform account or API key.
- Email: configured in settings, with addresses supplied by environment/config

## Install Commands

Verified from `README.md`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Students should use placeholder values in teaching examples:

```bash
TELEGRAM_BOT_TOKEN=YOUR_TOKEN_HERE
TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE
GMAIL_SMTP_USERNAME=YOUR_EMAIL_HERE
GMAIL_SMTP_PASSWORD=YOUR_APP_PASSWORD_HERE
RESEARCH_EMAIL_TO=YOUR_EMAIL_HERE
ALPHA_VANTAGE_API_KEY=YOUR_API_KEY_HERE
```

## Run Commands

Verified from `README.md` and `trading_bot/cli.py`:

```bash
.venv/bin/python -m trading_bot backfill --days 5
.venv/bin/python -m trading_bot scan --once
.venv/bin/python -m trading_bot scan
.venv/bin/python -m trading_bot telegram_test
.venv/bin/python -m trading_bot healthcheck
.venv/bin/python -m trading_bot replay --from YYYY-MM-DD --to YYYY-MM-DD
.venv/bin/python -m trading_bot replay --from YYYY-MM-DD --to YYYY-MM-DD --csv-dir path/to/csvs
.venv/bin/python -m trading_bot retry_failed_alerts
.venv/bin/python -m trading_bot paper_summary
.venv/bin/python -m trading_bot research --phase premarket --email
.venv/bin/streamlit run dashboard/app.py
```

## Test Commands

Verified from `pyproject.toml` and `README.md`:

```bash
.venv/bin/python -m pytest
```

This documentation task did not run pytest because tests can create caches, temporary runtime files, logs, or database state. That skip is documented in `no-code-change-confirmation.md`.

## External Services And Integrations

Verified or inferred from code and docs:

- yfinance/Yahoo: free best-effort market data.
- Telegram Bot API: alert delivery only.
- Alpha Vantage: optional live news sentiment and earnings calendar research.
- OpenAI Responses API: optional research summary formatting.
- Gmail SMTP: optional research email delivery.
- TradingView: manual chart confirmation only.
- macOS launchd: optional local scanner/dashboard restart support.

No broker execution integration was found in the command surface described by the repo.

## Alert Destinations

The active alert destination is Telegram. Alerts are decision-support messages and include manual-confirmation language.

Research summaries can optionally be emailed through Gmail SMTP. Email summaries are not trade execution.

## Missing Or Unclear Setup Details

Unknown / needs owner answer:

- Whether the current untracked `.env.save` should be deleted, ignored, or retained privately.
- Whether any credentials have been rotated after being saved locally.
- Why a GitHub issue template reportedly still refers to an older alert threshold of `85` while current config and README use `80`.
- Whether all current uncommitted research/runtime features are intended to be part of the official student-facing bot.
- Whether students should use live API credentials during class or only placeholders and dry walkthroughs.

## No Source Code Changed

This file documents the repo. It does not change source code, config, dependencies, tests, trading logic, signal logic, alert logic, or runtime behavior.
