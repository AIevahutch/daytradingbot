# Session 3 Instructor Script

## Session Goal

Students should understand replay, dashboard review, manual journaling, troubleshooting, and final validation without confusing software checks for trading proof.

## 0:00-0:15 - Validation Ladder

What to say:

"Today is about proof. Passing a test proves a software behavior, not a trading edge. A good validation report separates what was tested, what passed, what failed, and what is blocked."

Phases:

1. Technical validation.
2. Historical replay.
3. Live paper trading.
4. Statistical validation.
5. Small-size live testing later, outside this course.

What to demo:

- Show `docs/TESTING_VALIDATION_FRAMEWORK.md`.

What students should do:

- Write one sentence explaining why Phase 1 does not prove profitability.

Where beginners may get confused:

- They may think "tests pass" means "the bot makes money." Correct this immediately.

Safety reminder:

- Real-money readiness is outside the beginner course.

## 0:15-0:40 - Replay Mechanics

What to say:

"Replay walks historical candles in order. It should not peek into the future. It should evaluate on completed alert candles and store paper events."

Key points:

- Offline.
- No Telegram sends.
- Chronological candles.
- Completed `15m/30m/1h` closes.
- No current-day daily lookahead.

What to demo:

- Point to `trading_bot/replay.py`.
- Show the replay command shape from `README.md`.

What students should do:

- Define lookahead bias in plain English.

Where beginners may get confused:

- They may assume replay results predict tomorrow. Explain sample limits.

Safety reminder:

- Replay is evidence to review, not a future guarantee.

## 0:40-1:00 - Paper Events

What to say:

"Paper events tell the story of what the bot would have done."

Event types:

- `alerted`: would have cleared the live alert gate.
- `blocked`: stopped by quality, no-trade, research, or risk filters.
- `suppressed`: alert-ready but held back by duplicate, cooldown, cap, or priority controls.
- `ignored`: watch-only setup.
- `missed`: watch-only setup that later reached target 1.

What to demo:

- Show `README.md` replay section.

What students should do:

- Match sample rows to event types.

Where beginners may get confused:

- A missed event does not always mean the bot should be loosened. It may mean the risk filter did its job.

Safety reminder:

- Do not overfit one replay day.

## 1:00-1:20 - Dashboard Read Model

What to say:

"The dashboard lets us inspect the bot. It is a review surface, not an order screen."

Tabs:

- Health.
- Research.
- Market Monitor.
- Alerts.
- Paper Trading.
- Journal.
- Performance.
- Breakdowns.
- Improvement Lab.

What to demo:

- Point to `dashboard/app.py`.
- If using a prepared class environment, show the dashboard. In this documentation task, do not launch it.

What students should do:

- Choose one tab and say what question it answers.

Where beginners may get confused:

- Performance metrics can feel predictive. Remind them metrics are historical samples.

Safety reminder:

- Dashboard metrics do not guarantee future results.

## 1:20-1:40 - Journal And Analytics

What to say:

"The journal records what the human actually did. That is different from what the bot alerted."

Journal fields:

- Entry.
- Exit.
- Contracts or shares.
- Partial exits.
- Notes.
- Emotional state.
- Mistake tags.
- Alert taken, ignored, late, or avoided.

What to demo:

- Point to `trading_bot/journal/trade_journal.py`.
- Point to `trading_bot/analytics/`.

What students should do:

- Draft a sample journal note for an ignored alert.

Where beginners may get confused:

- Recommendations may sound like automatic improvements. Explain they stay pending review.

Safety reminder:

- No automatic live rule changes.

## 1:40-1:50 - Troubleshooting With Codex

What to say:

"Good debugging prompts are specific. They include command, error, expected behavior, and relevant files. They never include real secrets."

Prompt template:

```text
I ran COMMAND and got ERROR. I expected EXPECTED_BEHAVIOR. Please inspect the relevant files read-only first, explain the likely cause, and propose the smallest safe fix. Do not expose secrets or change trading behavior.
```

What to demo:

- Show `troubleshooting.md`.

What students should do:

- Write a debugging prompt for a failed dashboard tab.

Where beginners may get confused:

- They may paste `.env`. Tell them not to paste secrets.

Safety reminder:

- Debugging should not loosen risk gates just to make alerts appear.

## 1:50-2:00 - Final Project And Close

What to say:

"Your final project is an Alert Lifecycle Proof Report. It proves you understand the system. It does not prove a trading edge."

Final project checklist:

- Architecture diagram.
- Alert lifecycle trace.
- Manual review checklist.
- Replay validation plan.
- Dashboard QA checklist.
- Pending-review improvement proposal.
- Final alert-only sentence.

What students should do:

- Start the report outline.

Close:

"This material is educational only. This system is alert-only and does not place trades."
