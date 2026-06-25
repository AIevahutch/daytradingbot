# Architecture Map

## Plain-English Overview

The bot is a local alert-only system. It collects market data for `SPY`, `QQQ`, and `IWM`, builds technical context, detects possible setups, filters out low-quality conditions, applies research and risk gates, scores the remaining setups, sends Telegram alerts only when rules allow, and stores everything in local SQLite for dashboard review.

It is not a broker. It is not an auto-trader. It is not a contract picker. It is a manual decision-support tool.

## Data Flow Diagram

```text
Settings + Environment
   |
   v
SPY/QQQ/IWM Symbol List
   |
   v
yfinance 1m Market Data
   |
   v
Candle Normalization + Completed 15m/30m/1h Context
   |
   v
Levels: VWAP, Previous Day, Premarket, Weekly, Gap Fill
   |
   v
No-Trade Filters + Research Risk Gate
   |
   v
Setup Detection
   |
   v
Confidence Scoring + Hard Blockers
   |
   v
Duplicate/Cooldown/Daily Cap Controls
   |
   v
Telegram Alert or Watch-Only/Blocked/No-Trade Record
   |
   v
SQLite History
   |
   v
Streamlit Dashboard + Manual Journal + Replay + Analytics
```

## Component Guide

### Settings And Environment

`config/settings.yaml` defines the non-secret operating rules:

- `SPY`, `QQQ`, and `IWM` only.
- Alert threshold `80`.
- Alert timeframes `15m`, `30m`, and `1h`.
- Scan cadence `900` seconds.
- Research risk thresholds.
- Scoring weights.
- Strategy filters.

`.env` supplies secrets and service credentials. Student docs must use placeholders and must not expose real values.

### Market Data

The data layer uses yfinance as a free best-effort source. Raw `1m` candles can feed VWAP, levels, and resampling, but alert decisions are based on completed alert-timeframe context.

Teaching note: students should understand that free data can be stale or imperfect. Stale or missing data should make the bot more cautious, not more aggressive.

### SPY/QQQ/IWM Filter

The current universe is fixed to:

- `SPY`
- `QQQ`
- `IWM`

The course should not broaden this into crypto, individual stocks, futures, or live options execution.

### Levels

The levels layer calculates context such as:

- VWAP
- Previous day high, low, and close
- Premarket high and low
- Weekly levels
- Gap-fill levels

These levels help the strategy engine decide whether price is reacting near meaningful areas.

### Setup Detection

The strategy layer detects candidate setups before final alert eligibility. Current docs mention setups such as:

- VWAP reclaim
- VWAP reject
- Level break/hold
- Liquidity sweep reversal
- Failed breakout/breakdown
- Momentum continuation
- Strat-style continuation

Teaching note: a setup candidate is not automatically an alert.

### No-Trade And Research Gates

The no-trade layer blocks or penalizes low-quality conditions such as stale data, chop, weak volume, overextension, poor risk/reward, mixed confirmation, opening noise, midday lull, and late-session emotion.

Research gating is conservative:

- Missing same-day research can block alerts.
- High research risk can hard-block alerts.
- Medium risk can penalize confidence.
- Contra-bias setups can lose confidence.

Research should never create a trade by itself.

### Confidence Scoring

The scoring layer combines positive factors and penalties.

Positive factors include:

- Clean setup type
- Timeframe continuity
- Level confluence
- VWAP confirmation
- Relative volume confirmation
- Peer confirmation across SPY/QQQ/IWM
- Clean risk/reward

Penalties include:

- Weak volume
- Chop
- Conflicting timeframes
- Overextension
- Stale data
- Poor risk/reward
- Low-quality setup categories
- Research conflict

Current alert threshold: `80`.

Teaching shorthand:

- Below `80`: watch-only, blocked, ignored, or no-trade depending on context.
- `80+`: alert-eligible only if no hard blocker, cooldown, duplicate, daily cap, or research block applies.

### Alert Formatter

Telegram alerts are decision-support messages. They include setup context, entry zone, invalidation, confidence, reasoning, and manual confirmation language.

Important: the alert text must be taught as "review this setup manually," not "place this trade."

### Storage

SQLite stores local state such as:

- Candles
- Alerts
- Failed alert delivery attempts
- Research briefs and evidence
- Paper replay events
- Journal entries
- Analytics/recommendations
- Scanner heartbeat/process state

The dashboard reads from this local state.

### Dashboard

The Streamlit dashboard is the operating surface for:

- Health
- Research
- Market Monitor
- Alerts
- Paper Trading
- Journal
- Performance
- Breakdowns
- Improvement Lab

Students should learn to use the dashboard as a review surface, not as proof that a trade should be taken.

### Replay

Replay is offline and paper-only. It walks historical candles chronologically, records paper events, and avoids lookahead assumptions.

Replay event types include:

- `alerted`
- `blocked`
- `suppressed`
- `ignored`
- `missed`

Replay can teach how the software behaved. It does not guarantee future performance.

### Analytics And Recommendations

Analytics can summarize P/L, setup performance, confidence buckets, time-of-day performance, and other review data.

Recommendations remain pending manual review. They do not automatically mutate live strategy rules.

## What Is Not Automated

The bot does not automate:

- Broker login
- Contract selection
- Order placement
- Stop placement
- Profit-taking orders
- Rule changes
- Real-money approval
- TradingView confirmation
- Human judgment

Every alert requires manual review.
