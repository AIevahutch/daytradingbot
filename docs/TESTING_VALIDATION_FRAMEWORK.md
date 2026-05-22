# Testing And Validation Framework

The bot must move through these phases before it is trusted for real trading decisions. Do not skip phases because a backtest looks good or because one live day feels convincing.

## Phase 1: Technical Validation

Goal: prove the system functions technically before evaluating profitability.

Verify:

- Market data loads for SPY, QQQ, and IWM.
- Candle normalization and resampling are correct.
- Previous day, premarket, weekly, gap, and session levels calculate correctly.
- VWAP calculations are accurate.
- Telegram alert delivery works when credentials are configured.
- Dashboard tabs update from SQLite without app errors.
- Trade journal entries and partial exits persist.
- Scanner runs repeatedly without unhandled exceptions.
- Logging writes to `logs/trading_bot.log`.
- Health checks report database, settings, Telegram, scanner, logs, and data status.
- Crash recovery is verified if launchd is used.

Exit criteria:

- Tests pass.
- Healthcheck is understandable.
- One backfill and one scan cycle complete.
- Dashboard renders.
- Any Telegram blocker is explicitly documented.

## Phase 2: Historical Replay Testing

Goal: identify weak strategy behavior before live testing.

Replay SPY, QQQ, and IWM across:

- Trend days
- Chop days
- Volatile days
- Low-volume days
- Gap days
- CPI, FOMC, and other major news-event days

Validate:

- Alert quality
- Confidence score accuracy
- No-trade filtering
- False positive rate
- Risk/reward quality
- Overtrading prevention
- Missed A+ setups
- Avoided bad setups

Exit criteria:

- Replay runs are stored.
- Paper events are reviewable in the dashboard.
- Weak setup types and weak market conditions are documented.
- No live scoring rule is changed automatically.

## Phase 3: Live Paper Trading

Goal: validate real-time performance without risking capital.

Run the bot live in paper-trading mode only.

Requirements:

- Manually review every alert on TradingView.
- Manually log whether the alert was taken, ignored, won, failed, or was late.
- Manually record entry, exit, partials, realized or simulated P/L, and notes.
- Manually track emotional decisions.
- Compare alerted trades against trades actually taken.

Track:

- Alert precision
- Timing quality
- Emotional reactions
- Missed trades
- Ignored trades
- False positives
- Expectancy
- Consistency
- No-trade day quality

Exit criteria:

- Real-time alerts are journaled consistently.
- The dashboard shows enough paper outcomes to evaluate behavior.
- Emotional mistake tags are being used honestly.
- No real capital is risked in this phase.

## Phase 4: Statistical Validation

Goal: prove the edge is meaningful enough to test with very small real-money size.

Before real-money testing:

- Collect at least 50-100 trade samples.
- Include multiple market conditions.
- Avoid changing rules after tiny samples.

Validate:

- Win rate
- Expectancy
- Profit factor
- Max drawdown
- Setup consistency
- Confidence score reliability
- Best setup types
- Worst setup types
- Best market conditions
- Weak filters
- Over-alerting patterns

Exit criteria:

- Sample size is documented.
- Performance is broken down by setup, confidence bucket, market condition, and time of day.
- Recommendations are reviewed for overfitting risk.
- Any proposed rule change has before/after simulation evidence and manual approval.

## Phase 5: Small-Size Live Testing

Goal: validate human execution behavior under real-money conditions.

Only begin after successful paper-trading and statistical validation.

Requirements:

- Use extremely small position sizes.
- Continue manually confirming on TradingView.
- Continue journaling every trade and emotional state.
- Continue reinforcement-learning-ready data collection.
- Treat psychology and discipline as the main test.

Focus:

- Execution discipline
- Emotional control
- Consistency
- Avoiding revenge trading
- Avoiding FOMO
- Respecting stops
- Preserving capital

Exit criteria:

- Live behavior matches the paper-trading process.
- Position sizing remains intentionally small.
- Emotional mistakes are documented instead of hidden.
- The system still prioritizes quality over quantity.

## Constraints Across All Phases

Do not:

- Optimize solely for historical backtests.
- Overfit the strategy.
- Continuously change rules after small sample sizes.
- Prioritize alert quantity over quality.
- Treat confidence scores as permission to chase.
- Let the bot place trades automatically.

Always prioritize:

- Long-term consistency
- Discipline
- Statistical validity
- Repeatability
- Capital preservation
- No-trade selectivity

## Final Rule

The bot is not “done” for real-money trust until all five phases have a documented result. Passing Phase 1 means the software works. It does not mean the strategy is profitable.

