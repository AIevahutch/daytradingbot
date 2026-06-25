# Session 2 Instructor Script

## Session Goal

Students should understand how market data becomes setup candidates, how filters and scoring decide alert eligibility, and why research/AI must stay conservative.

## 0:00-0:10 - Recap

What to say:

"Last session, we mapped the repo. Today we follow a possible alert through the logic. Most candidates should not become alerts. That is a feature, not a bug."

What to demo:

- Reopen `architecture-map.md`.

What students should do:

- One student explains the flow from candles to dashboard.

Safety reminder:

- Alert logic is decision support only.

## 0:10-0:30 - Market Data And Completed Candles

What to say:

"The bot uses free best-effort data. Raw 1-minute candles are useful, but alert decisions should use completed alert-timeframe context."

"Current alert timeframes are 15 minutes, 30 minutes, and 1 hour."

What to demo:

- Point to `trading_bot/data/market_data.py`.
- Point to `config/settings.yaml` alert timeframes.

What students should do:

- Explain why an unfinished candle can be misleading.

Where beginners may get confused:

- They may think faster scanning always means better alerts. Explain that noisy data can create bad decisions.

Safety reminder:

- Stale or questionable data should block or warn, not encourage action.

## 0:30-0:50 - Levels

What to say:

"Levels help the bot know where price is reacting. The current project uses VWAP, previous day levels, premarket levels, weekly levels, and gap-fill context."

What to demo:

- Point to `trading_bot/levels/levels.py`.

What students should do:

- List two levels and explain why they are context rather than instructions.

Where beginners may get confused:

- A level is not a trade. It is a place to inspect behavior.

Safety reminder:

- Always confirm levels manually on a chart before acting in the real world.

## 0:50-1:10 - Setup Detection

What to say:

"A setup detector finds candidates. The candidate still needs filters, scoring, and manual review."

Setup examples:

- VWAP reclaim/reject.
- Level break/hold.
- Liquidity sweep reversal.
- Failed breakout/breakdown.
- Momentum continuation.
- Strat-style continuation.

What to demo:

- Point to `trading_bot/strategy/engine.py`.

What students should do:

- Classify a sample as "candidate only."

Where beginners may get confused:

- They may assume a setup function should send alerts directly. Explain separation of responsibilities.

Safety reminder:

- Candidates are untrusted until they pass gates.

## 1:10-1:30 - No-Trade Filters And Scoring

What to say:

"The bot should be comfortable staying quiet. Filters and scoring protect against low-quality conditions."

Blocker examples:

- Stale data.
- Chop.
- Weak volume.
- Bad risk/reward.
- Conflicting timeframes.
- Mixed SPY/QQQ/IWM confirmation.
- Overextension.
- Risky time of day.

What to demo:

- Point to `trading_bot/psychology/no_trade.py`.
- Point to `trading_bot/scoring/scoring.py`.

What students should do:

- Explain why `79` is not the same as `80`.
- Explain why `80+` still might be blocked.

Where beginners may get confused:

- The score is not a win probability. It is an internal quality score.

Safety reminder:

- No profit promises. No guaranteed win rate.

## 1:30-1:45 - Research Gates And AI Summaries

What to say:

"Research can reduce risk by blocking or penalizing alerts. It should never create a trade by itself."

"The OpenAI summary layer is for formatting and explanation. The rule-based decision remains the source of truth."

What to demo:

- Point to `trading_bot/research/`.
- Point to `trading_bot/summaries.py`.

What students should do:

- Identify which part is rule-based and which part is AI-generated text.

Where beginners may get confused:

- AI wording can sound confident. Teach students to distrust confident wording when risk gates disagree.

Safety reminder:

- Do not treat AI text, confidence scores, or research bias as permission to trade.

## 1:45-1:55 - Telegram Alert Anatomy

What to say:

"Telegram is the notification channel. It should describe the setup and remind the human to review manually."

Alert components:

- Ticker.
- Setup type.
- Direction.
- Entry zone.
- Stop/invalidation.
- Targets.
- Confidence.
- Risk/reward.
- Reasoning.
- Avoid-if warning.
- Alert-only footer.

What to demo:

- Point to `trading_bot/alerts/telegram.py`.
- Do not send a real Telegram test in this documentation-only course build.

What students should do:

- Rewrite an aggressive alert phrase into manual-review language.

Where beginners may get confused:

- "Suggested sell/partial" can sound like order placement. Explain it is management guidance only.

Safety reminder:

- Telegram does not place orders.

## 1:55-2:00 - Checkpoint And Homework

Checkpoint questions:

- What is a setup candidate?
- Name two hard blockers.
- Can research create trades?
- Can AI override the rule-based gate?

Homework:

- Draft four test scenarios.
- Read `prompt-library.md`.

Close:

"A quiet scan is not failure. The bot is designed to reject low-quality conditions."
