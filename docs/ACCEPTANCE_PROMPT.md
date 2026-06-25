# Acceptance Prompt: Prove The Bot Is Done

Use this prompt in a validation or deployment workstream. The goal is to force a clear PASS / FAIL / BLOCKED answer instead of a vague “looks good.”

```text
You are validating the SPY/QQQ/IWM day-trading alert bot.

Your job is to prove whether the MVP is actually done. Be strict. Do not mark the project complete unless every required gate passes or the user explicitly accepts a documented exception.

Core rules:
- The bot tracks only SPY, QQQ, and IWM.
- It is alert-only and must never place trades.
- It must remain zero-cost for the MVP.
- TradingView is manual confirmation only.
- Robinhood is not integrated.
- Free market data is best-effort; stale or questionable data must produce NO TRADE behavior.
- Strategy changes suggested by analytics must require manual review and approval.

Validate these gates:

1. Repository and environment
- Confirm the repository is current.
- Confirm `.env` is ignored and no secrets are committed.
- Confirm dependencies install in a local virtual environment.
- Confirm `config/settings.yaml` uses SPY, QQQ, IWM only and an alert threshold of 80.

2. Automated tests
- Run `.venv/bin/python -m pytest`.
- PASS only if all tests pass.
- Record the exact test count and result.

3. Health checks
- Run `.venv/bin/python -m trading_bot healthcheck`.
- PASS only if database access, settings load, logging, Telegram configuration state, and scanner status are clearly reported.
- Telegram may be BLOCKED if credentials are not configured, but that must be called out.

4. Market data and scanner
- Run `.venv/bin/python -m trading_bot backfill --days 5`.
- Run `.venv/bin/python -m trading_bot scan --once`.
- PASS only if SPY/QQQ/IWM are processed without unhandled exceptions.
- Stale data, chop, weak volume, or no setup may correctly return NO TRADE.
- Confirm no automated trade execution exists.

5. Alert behavior
- Confirm sub-80 setups do not send Telegram alerts.
- Confirm 80+ setups are the only setups eligible for Telegram alerts.
- Confirm duplicate alerts are suppressed.
- Confirm suggested sell/partial alerts are alert-only management guidance, do not place orders, and do not count against entry-alert caps.
- Confirm every alert includes ticker, setup type, direction, entry zone, stop, targets, invalidation, confidence, risk/reward, plain-English reasoning, avoid-if warning, and alert-only footer.
- If Telegram credentials are configured, run `.venv/bin/python -m trading_bot telegram_test` and verify delivery.

6. Dashboard
- Start `.venv/bin/streamlit run dashboard/app.py`.
- Open the local dashboard.
- PASS only if Health, Market Monitor, Alerts, Paper Trading, Journal, Performance, Breakdowns, and Improvement Lab render without app errors.

7. Journal and P/L analytics
- Add or simulate a manual trade.
- Confirm total P/L, daily/weekly/monthly P/L, win rate, average win/loss, expectancy, profit factor, drawdown, largest winner/loser, equity curve, setup breakdowns, market condition breakdowns, time-of-day breakdowns, confidence buckets, notes, emotional state, and mistake tags update.

8. Replay and improvement loop
- Run a replay using stored candles or CSV data.
- Run `.venv/bin/python -m trading_bot paper_summary`.
- Confirm paper events are stored.
- Confirm replay evaluates only on completed alert timeframe closes and does not use partial 15m/30m/1h bars for setup detection.
- Confirm replay does not use full future daily candles for current-day intraday decisions.
- Confirm recommendations are pending review only and do not mutate live scoring rules automatically.

9. Local deployment
- If deploying locally, verify scanner and dashboard launch commands.
- If using launchd, copy the example plists, load them, confirm processes restart, and confirm scanner heartbeat updates.
- Confirm logs are written to `logs/trading_bot.log`.

10. Final proof report
Return a concise report with:
- Overall status: PASS, FAIL, or BLOCKED.
- Exact commit hash validated.
- Exact commands run.
- Test result.
- Dashboard result.
- Telegram result.
- Data/scanner result.
- Journal/analytics result.
- Replay result.
- Deployment result.
- Current validation phase: Phase 1 technical, Phase 2 replay, Phase 3 live paper, Phase 4 statistical, or Phase 5 small-size live.
- Any remaining blockers.
- A final sentence: “This system is alert-only and does not place trades.”

Do not call the MVP done if any required gate is untested, failing, or blocked without explicit user acceptance.
Do not call the system ready for real-money decisions unless the phased framework in docs/TESTING_VALIDATION_FRAMEWORK.md is complete through Phase 4 and the user explicitly approves Phase 5.
```

## Done Definition

The software MVP is done only when:

- Continuous scanning works for SPY, QQQ, and IWM.
- Only 80-100 confidence setups are eligible for Telegram alerts.
- Telegram delivery is verified when credentials are configured.
- Low-quality conditions produce NO TRADE instead of forced alerts.
- SPY VWAP reclaim long alerts remain blocked pending review unless explicitly approved later.
- Liquidity sweep alerts include +1R tactical management guidance and suggested sell/partial alerts remain alert-only.
- Trade journaling and manual realized P/L tracking work.
- Performance analytics and equity curve work.
- Replay evaluates on completed candle closes, avoids current-day daily lookahead, and recommendations work without automatically changing live rules.
- Streamlit dashboard renders without app errors.
- Local deployment or local run commands are documented and verified.
- README setup, strategy, testing, and deployment instructions are accurate.

## Real-Money Readiness

Software completion is not the same as trading readiness. The bot should move through the phased framework in [TESTING_VALIDATION_FRAMEWORK.md](TESTING_VALIDATION_FRAMEWORK.md):

- Phase 1: technical validation
- Phase 2: historical replay testing
- Phase 3: live paper trading
- Phase 4: statistical validation
- Phase 5: small-size live testing

Do not rely on the bot for real-money decisions until Phase 4 has enough evidence and Phase 5 is explicitly approved.
