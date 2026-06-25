# Session 2 Slides: Signal, Risk Gate, Score, Alert

## 0:00-0:10 - Slide 1: Recap

Bullets:

- Local Python bot.
- SPY/QQQ/IWM only.
- Alert-only.
- Manual review.
- Dashboard records the story.

Speaker notes:

- Ask one student to explain the data flow.

## 0:10-0:25 - Slide 2: Market Data

Bullets:

- yfinance is free best-effort data.
- Raw `1m` data feeds context.
- Alerts use completed `15m/30m/1h` candles.
- Stale data should block or warn.

Speaker notes:

- Explain why incomplete candles can mislead.

Demo notes:

- Point to `trading_bot/data/market_data.py`.

## 0:25-0:40 - Slide 3: Levels

Bullets:

- VWAP.
- Previous day high/low/close.
- Premarket high/low.
- Weekly levels.
- Gap-fill levels.

Speaker notes:

- Levels are context, not instructions.

## 0:40-0:55 - Slide 4: Setup Candidates

Bullets:

- VWAP reclaim/reject.
- Level break/hold.
- Liquidity sweep reversal.
- Failed breakout/breakdown.
- Momentum continuation.
- Strat-style continuation.

Speaker notes:

- Candidate means "something to inspect."

Activity notes:

- Students label each example as "candidate, not alert yet."

## 0:55-1:10 - Slide 5: No-Trade Filters

Bullets:

- Stale data.
- Chop.
- Weak volume.
- Overextension.
- Poor risk/reward.
- Conflicting timeframes.
- Risky session windows.

Speaker notes:

- Good systems are allowed to stay quiet.

## 1:10-1:25 - Slide 6: Scoring

Bullets:

- Positive factors add confidence.
- Penalties reduce confidence.
- Hard blockers stop alerts.
- `80+` is the current alert threshold.
- `80+` still needs no hard blocker.

Speaker notes:

- Confidence is a filter, not a promise.

## 1:25-1:40 - Slide 7: Research Gate

Bullets:

- Premarket, midday, EOD context.
- Risk score.
- Bias.
- Hard blocks.
- Source status.
- Missing sources are visible risk.

Speaker notes:

- Research can block or penalize. It should not create trades.

## 1:40-1:50 - Slide 8: AI Explanation Layer

Bullets:

- Optional OpenAI summary.
- Formats research email.
- Rule-based decision remains source of truth.
- No contracts, strikes, broker actions, or guarantees.

Speaker notes:

- AI writes explanation text; it does not become the trader.

## 1:50-1:57 - Slide 9: Telegram Alert Anatomy

Bullets:

- Ticker.
- Setup.
- Direction.
- Entry zone.
- Stop/invalidation.
- Targets.
- Confidence.
- Reasoning.
- Avoid-if warning.
- Alert-only footer.

Speaker notes:

- Alert text is for manual review.

## 1:57-2:00 - Slide 10: Session 2 Checkpoint

Bullets:

- Explain one blocker.
- Explain one score factor.
- Explain why AI cannot override risk gates.

Speaker notes:

- End with no-trade as a valid result.
