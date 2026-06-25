# SPY/QQQ/IWM Day-Trading Alert Bot

Local, zero-cost, alert-only trading assistant for SPY, QQQ, and IWM. It scans free best-effort market data, detects disciplined price-action setups, sends Telegram alerts only when confidence is 80-100 and no hard no-trade blocker is present, and tracks manual and paper-trading performance in a Streamlit dashboard.

It never places trades, never connects to Robinhood, and never changes live strategy rules without review.

## What It Does

- Scans SPY, QQQ, and IWM only.
- Uses 1m data only as a raw feed to derive 15m, 30m, and hourly alert context.
- Computes VWAP, previous day high/low/close, premarket high/low, weekly levels, and gap-fill levels.
- Detects VWAP reclaim/reject, level break/hold, liquidity sweep reversals, failed breakouts/breakdowns, momentum continuation, and Strat-style continuation.
- Scores setups with aggressive penalties for chop, weak volume, stale data, poor risk/reward, overextension, and mixed market confirmation.
- Sends Telegram alerts only when confidence is at least 80 and no hard blocker is active.
- Blocks SPY VWAP reclaim long alerts pending review because replay evidence shows weak full-target performance.
- Adds suggested +1R sell/partial management alerts for liquidity sweep reversals.
- Retries Telegram delivery, records failed sends, and supports retrying undelivered alerts.
- Records lower-confidence setups in the dashboard as watch-only context.
- Provides historical replay, manual trade journaling, P/L analytics, setup breakdowns, and review-only strategy recommendations.

## Setup

Python 3.9+ is supported.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
OPENAI_API_KEY=your_openai_key
GMAIL_SMTP_USERNAME=your_gmail_address
GMAIL_SMTP_PASSWORD=your_gmail_app_password
RESEARCH_EMAIL_TO=your_gmail_address
ALPHA_VANTAGE_API_KEY=required_for_live_news_and_earnings
```

`ALPHA_VANTAGE_API_KEY` powers the Research tab's live market news sentiment
and earnings calendar context. Without it, research marks those sources as
missing and adds risk to the brief.

Edit non-secret rules in `config/settings.yaml`.

## Commands

Backfill recent context:

```bash
python -m trading_bot backfill --days 5
```

Run one scan cycle:

```bash
python -m trading_bot scan --once
```

Run continuous scanner:

```bash
python -m trading_bot scan
```

Run scanner watchdog:

```bash
python -m trading_bot watchdog
```

The watchdog checks the scanner heartbeat and restarts the scanner if it stops
or goes stale. The Desktop launcher starts this automatically.

Test Telegram:

```bash
python -m trading_bot telegram_test
```

Run health checks:

```bash
python -m trading_bot healthcheck
```

Replay stored 1m candles for paper-trading QA:

```bash
python -m trading_bot replay --from 2026-05-13 --to 2026-05-19
```

Replay CSV candles from `SPY.csv`, `QQQ.csv`, and `IWM.csv`:

```bash
python -m trading_bot replay --from 2026-05-13 --to 2026-05-19 --csv-dir path/to/csvs
```

Retry failed Telegram alerts:

```bash
python -m trading_bot retry_failed_alerts
```

Summarize paper-trading replay results:

```bash
python -m trading_bot paper_summary
```

Open dashboard:

```bash
streamlit run dashboard/app.py
```

The dashboard Health tab can start, stop, and run the scanner. It manages the
background scanner through `data/scanner.pid` and writes process output to
`logs/scanner_process.log`. Scanner watchdog state is tracked through
`data/scanner_watchdog.pid` and `logs/scanner_watchdog.log`.

## Architecture

- `trading_bot/data`: yfinance adapter, candle normalization, resampling, stale-data checks
- `trading_bot/levels`: VWAP, previous day, premarket, weekly, and gap levels
- `trading_bot/strategy`: rule-based setup detection
- `trading_bot/scoring`: confidence score and 80+ alert gating
- `trading_bot/psychology`: no-trade conditions and chase/fakeout filters
- `trading_bot/alerts`: Telegram formatting and delivery
- `trading_bot/replay`: historical paper-trading replay without lookahead
- `trading_bot/runtime`: local scanner process controls for dashboard-managed runs
- `trading_bot/health`: local runtime checks for Telegram, DB, data freshness, logs, and scanner status
- `trading_bot/journal`: manual trade entry, partial exits, notes, tags
- `trading_bot/analytics`: P/L metrics, breakdowns, and review-only recommendations
- `dashboard`: Streamlit health, monitor, alerts, replay, journal, analytics, and improvement lab
- `data/trading_bot.sqlite`: local SQLite database

## Strategy Logic

The scanner builds candidates, then scoring decides whether they deserve attention.

Positive score factors:

- clean setup type
- timeframe continuity
- level confluence
- VWAP confirmation
- relative volume confirmation
- SPY/QQQ/IWM peer confirmation
- risk/reward at or above the configured minimum

Penalties:

- chop
- weak volume
- stale or missing data
- conflicting timeframes
- overextension from VWAP
- poor risk/reward
- duplicate or excessive alerts
- generic momentum or Strat continuation until paper/journal evidence improves

Hard blockers:

- stale or missing market data
- compressed chop
- weak relative volume
- overextension from VWAP
- poor risk/reward
- conflicting timeframes
- mixed SPY/QQQ/IWM confirmation
- opening-range noise, midday participation lulls, and late closing-window entries

Current A+ precision defaults in `config/settings.yaml` use a 2R target, 1.8R minimum risk/reward, same-symbol cooldown, daily alert caps, and session-quality blocks. These settings are designed to reduce alert volume and improve paper-trading precision, not to maximize activity.

The bot should be comfortable producing no Telegram alert. A quiet day is acceptable when conditions are low quality.

## Alert Format

Every alert includes ticker, setup type, direction, entry zone, stop, targets, invalidation, confidence, risk/reward, plain-English reasoning, avoid-if warning, and an alert-only footer reminding you to confirm manually on TradingView.

## Journal And Analytics

Manual realized P/L is the source of truth. Entry, exit, contracts/shares, partial exits, notes, emotional state, and mistake tags are stored as context.

Tracked analytics include total/daily/weekly/monthly P/L, win rate, average win/loss, expectancy, profit factor, drawdown, largest winner/loser, equity curve, setup performance, market-condition performance, time-of-day performance, confidence buckets, false-positive review support, alert reviews, replay outcomes, and no-trade notes.

## Paper Trading Replay

Replay is offline and never sends Telegram alerts. It walks historical 1m candles chronologically, rebuilds 15m/30m/hourly context without lookahead, detects/scored setups, and stores paper events:

- `alerted`: would have cleared the live alert gate
- `blocked`: blocked by no-trade, quality, research, or risk filters
- `suppressed`: alert-ready but held back by duplicate, cooldown, cap, or priority controls
- `ignored`: watch-only setup that did not qualify
- `missed`: watch-only setup that later reached target 1

Use the dashboard Paper Trading tab to inspect replay runs, event types, closed-alert win rate, total R, and missed/blocked/suppressed patterns. Open alerted setups are tracked separately and are not counted in win rate until closed by the replay outcome model. Replay also stores MFE/MAE in R so you can distinguish alerts that caught the start of a move from alerts that reached the full paper target before stop.

Liquidity sweep reversals are tracked with tactical +1R management in addition to the full target model. Telegram entry alerts include a suggested sell/partial level, and the scanner can send a separate suggested sell/partial alert if an already-alerted liquidity sweep reaches that +1R level. These are decision-support alerts only; the bot still never places trades.

### Replay Timing Done When

- Replay evaluates only after the shortest enabled alert timeframe has closed. With the default 15m/30m/1h model, replay evaluates on 15m closes such as `09:44`, `09:59`, `10:14`, and `10:29` for minute-start candles.
- Replay and live scanning both use `completed_candles_for_timeframe` before no-trade evaluation, trend bias, and strategy detection.
- Replay does not use a full future daily candle for current-day intraday decisions; it derives the current daily candle only from 1m candles available at that replay timestamp.
- Replay paper events store `replay_evaluated_on_completed_close`, `replay_latest_1m_at`, MFE, and MAE metadata for audit.
- `test_replay_evaluates_on_completed_candle_closes`, `test_replay_daily_context_uses_partial_current_day_without_lookahead`, and the full pytest suite pass.

## Reinforcement-Learning-Ready Feedback Loop

The MVP does not train or apply live RL rules. It stores outcomes and generates recommendations such as:

- reduce score weight for setups with negative expectancy
- add filters for market conditions producing losses
- strengthen warnings around recurring mistake tags
- recalibrate confidence buckets when 90+ alerts underperform

Recommendations include sample size, evidence quality, and overfitting risk. They stay `pending_review` until manually approved. The code intentionally separates recommendation generation from rule application.

## Data Notes

The MVP uses free best-effort yfinance data for personal/research use and local scanning. Treat it as near-real-time context, not exchange-grade execution data. Use TradingView manually to confirm every setup before acting.

## Testing

```bash
.venv/bin/python -m pytest
```

The tests cover candle resampling, stale-data detection, level generation, VWAP, setup detection, 79/80 alert gating, hard blockers, alert formatting, Telegram retry persistence, replay storage, no-trade filters, P/L metrics, breakdowns, and recommendation generation.

## Acceptance Check

Use [docs/ACCEPTANCE_PROMPT.md](docs/ACCEPTANCE_PROMPT.md) as the validation prompt before calling the MVP done. It defines the required PASS / FAIL / BLOCKED gates for tests, health checks, scanner behavior, Telegram, dashboard, journal analytics, replay, deployment, and the alert-only safety rule.

Use [docs/A_PLUS_PRECISION_PROMPT.md](docs/A_PLUS_PRECISION_PROMPT.md) when tuning for higher win rate. It requires broad replay samples and explicitly blocks one-day overfitting.

Use [docs/TESTING_VALIDATION_FRAMEWORK.md](docs/TESTING_VALIDATION_FRAMEWORK.md) before relying on live trading decisions. Passing technical validation means the software runs; it does not prove the strategy is profitable. The bot must progress through technical validation, historical replay, live paper trading, statistical validation, and only then small-size live testing.

## Local Deployment

1. Install dependencies and fill in `.env`.
2. Run `.venv/bin/python -m trading_bot healthcheck`.
3. Run `.venv/bin/python -m trading_bot telegram_test`.
4. Backfill context with `.venv/bin/python -m trading_bot backfill --days 5`.
5. Start scanner with `.venv/bin/python -m trading_bot scan`.
6. Start dashboard with `.venv/bin/streamlit run dashboard/app.py`.
7. Watch `logs/trading_bot.log`, the dashboard Health tab, and failed Telegram delivery attempts.

For crash recovery on macOS, copy the example launchd plists from `deploy/` to `~/Library/LaunchAgents/`, then load them:

```bash
cp deploy/com.eva.trading-bot.scanner.plist.example ~/Library/LaunchAgents/com.eva.trading-bot.scanner.plist
cp deploy/com.eva.trading-bot.dashboard.plist.example ~/Library/LaunchAgents/com.eva.trading-bot.dashboard.plist
launchctl load ~/Library/LaunchAgents/com.eva.trading-bot.scanner.plist
launchctl load ~/Library/LaunchAgents/com.eva.trading-bot.dashboard.plist
```

The launchd jobs run local alert-only processes. They do not connect broker APIs or place trades.

## Future Upgrades

- Optional paid/exchange-grade data adapter
- Screenshot upload support for journal entries
- Better historical alert outcome labeling
- More detailed before/after rule simulations
- Broker read-only import for reconciliation
- Optional hosted dashboard after local reliability is proven
