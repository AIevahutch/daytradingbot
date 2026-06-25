# Session 3 Slides: Replay, Journal, Dashboard, Validation

## 0:00-0:10 - Slide 1: Why Validation Matters

Bullets:

- Passing code is not proof of profit.
- Replay is historical.
- Paper trading is practice.
- Live risk is outside this course.

Speaker notes:

- Draw a hard line between software validation and trading readiness.

## 0:10-0:20 - Slide 2: Validation Ladder

Bullets:

- Phase 1: technical validation.
- Phase 2: historical replay.
- Phase 3: live paper trading.
- Phase 4: statistical validation.
- Phase 5: small-size live testing later.

Speaker notes:

- This course focuses on construction, review, and validation language.

## 0:20-0:35 - Slide 3: Replay Mechanics

Bullets:

- Offline.
- No Telegram alerts.
- Chronological candles.
- Completed alert-frame closes.
- No current-day daily lookahead.

Speaker notes:

- Explain lookahead as "accidentally using future information."

## 0:35-0:50 - Slide 4: Paper Event Types

Bullets:

- `alerted`.
- `blocked`.
- `suppressed`.
- `ignored`.
- `missed`.

Speaker notes:

- Each event tells a different review story.

Activity notes:

- Students match example scenarios to event types.

## 0:50-1:05 - Slide 5: Metrics Without Overtrust

Bullets:

- Closed-alert win rate.
- Total R.
- MFE and MAE.
- Move-start rate.
- Tactical +1R outcomes.

Speaker notes:

- Metrics describe what happened in a sample. They do not guarantee future performance.

## 1:05-1:20 - Slide 6: Journal

Bullets:

- Entry.
- Exit.
- Partials.
- P/L.
- Notes.
- Emotional state.
- Mistake tags.
- Taken, ignored, late, or avoided.

Speaker notes:

- Human journal is the source of truth for actions.

## 1:20-1:35 - Slide 7: Dashboard QA

Bullets:

- Health tab.
- Research state.
- Alerts table.
- Paper Trading tab.
- Journal tab.
- Performance and Breakdowns.
- Improvement Lab.

Speaker notes:

- Dashboard failures are software issues, not trading signals.

## 1:35-1:48 - Slide 8: Troubleshooting With Codex

Bullets:

- Include command run.
- Include traceback.
- Include relevant config.
- Include expected behavior.
- Do not paste secrets.
- Ask for read-only diagnosis first.

Speaker notes:

- Good debugging prompts are specific and safe.

## 1:48-1:57 - Slide 9: Final Project

Bullets:

- Architecture diagram.
- Alert lifecycle proof.
- Manual-review checklist.
- Replay validation plan.
- Dashboard QA checklist.
- Pending-review improvement.

Speaker notes:

- The final project proves understanding, not profitability.

## 1:57-2:00 - Slide 10: Course Close

Bullets:

- Alert-only.
- Manual review.
- No profit promises.
- No live auto-trading.
- Keep learning with evidence.

Speaker notes:

- End with: this system is alert-only and does not place trades.
