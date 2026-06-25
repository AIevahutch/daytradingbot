# Safety And Risk

## Required Disclaimer

This material and bot are for educational and research purposes only. They are not financial, investment, tax, or trading advice.

The bot is alert-only: it does not place trades, connect to a broker, or authorize trades. Any decision to trade is manual and solely the user's responsibility.

Options and day trading involve substantial risk, including loss of the full premium or more depending on strategy. Past replay, paper-trading, win-rate, or profit-factor results do not guarantee future performance.

## Manual Alerts Vs Automated Trading

Manual alert workflow:

- Bot scans.
- Bot evaluates conditions.
- Bot may send an alert.
- Human reviews chart, risk, data, and context.
- Human decides what to do outside the bot.
- Human journals the result.

Automated trading workflow:

- Software places orders.
- Software changes positions.
- Software may manage stops or exits.

The current bot is the first workflow only. It is not the second workflow.

## What The Bot Should Never Claim

The bot and course should never claim:

- Guaranteed profit.
- Guaranteed win rate.
- Guaranteed signal quality.
- "Safe" options trades.
- "Risk-free" alerts.
- Permission to trade.
- Broker execution.
- Automatic order placement.
- AI certainty.
- Real-money readiness after technical tests only.

## Why Risk Management Matters

Risk management matters because:

- Free data can be stale.
- Candles can change before they close.
- News and macro events can change context quickly.
- Options can move fast.
- Spread and liquidity matter.
- Human emotions affect decisions.
- Backtests and replays can overfit.
- AI-generated language can sound more certain than it is.

## AI Overtrust Warning

AI summaries are only a formatting and explanation layer. The rule-based risk gates, manual review, and no-trade conditions remain the source of truth.

Do not treat:

- AI text,
- confidence scores,
- research bias,
- replay win rate,
- paper-trading profit factor,
- or dashboard metrics

as permission to enter a trade.

## Manual Review Checklist

Before any alert is discussed as tradable outside class:

- Confirm this is paper/demo mode unless later phases have explicit owner approval.
- Confirm the symbol is `SPY`, `QQQ`, or `IWM`.
- Confirm the TradingView chart manually.
- Confirm timeframe, price level, volume, VWAP, and invalidation.
- Confirm data is not stale.
- Confirm no high-risk macro, Fed, CPI/jobs, VIX, or research block exists.
- Confirm entry is not being chased outside the planned zone.
- Confirm stop/invalidation and maximum loss.
- Confirm options spread, liquidity, and whole-contract affordability manually.
- Journal outcome, emotional state, mistakes, and whether the alert was ignored, taken, late, or avoided.
- Treat no-trade as a correct outcome.

## Safe Paper-Review Workflow

Recommended educational workflow:

1. Run technical checks in a safe local environment.
2. Review historical replay.
3. Record paper events.
4. Inspect dashboard metrics.
5. Journal manual decisions.
6. Collect enough samples across different market conditions.
7. Review proposed rule changes manually.
8. Keep all live rule changes behind owner approval.

## Live Trading Is Not Part Of This Course

This course does not teach live auto-trading.

This course does not teach students to connect a broker.

This course does not teach students to place orders from the bot.

This course does not approve real-money trading.

## Student-Facing Safety Language

Use this wording at the start of each session:

```text
This is an educational software course. The bot is alert-only and does not place trades. Alerts, AI summaries, replay results, and dashboard metrics are decision-support context only. They are not financial advice, not a guarantee, and not permission to trade.
```
