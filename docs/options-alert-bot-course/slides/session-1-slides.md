# Session 1 Slides: Thread A - Build Alert Bot Architecture

PowerPoint file:

- `docs/options-alert-bot-course/slides/session-1-bot-map-and-setup.pptx`

Desktop copy:

- `/Users/eva/Desktop/Session-1-Alert-Bot-Architecture.pptx`

Dashboard visual assets used:

- `docs/options-alert-bot-course/slides/assets/dashboard-health-overview.png`
- `docs/options-alert-bot-course/slides/assets/dashboard-research-tab.png`
- `docs/options-alert-bot-course/slides/assets/dashboard-market-tab.png`
- `docs/options-alert-bot-course/slides/assets/dashboard-performance-tab.png`

Deck status:

- Verified current deck has 13 visible student-facing slides.
- Instructor/private guidance is in speaker notes, not on visible slides.
- Slide 8, `Start With The Project Plan`, contains the full current Thread A student prompt in speaker notes with copy/paste markers.
- The visible slides do not contain the long prompt text.
- Session 1 is Thread A: Build Alert Bot Architecture.
- Thread A starts in Project Plan mode.
- Session 2 is Thread B: QA + Paper Trading Bot.
- Session 3 is Thread C: Build Market Research Agent.
- The deck calls out `principal-ml-engineer`, `ui-ux-designer`, and `quant-researcher`.
- The deck recommends GPT-5 or the highest available Codex reasoning model, High thinking/reasoning, Standard speed, and ChatGPT Plus or higher.

Important teaching note:

- The original seed prompt used `85-100` confidence and is preserved in `prompt-library.md` as history.
- The current Session 1 prompt uses threshold `80`, alert timeframes `15m`, `30m`, `1h`, configured scanner cadence `60` seconds, market-data window pause, manual review only, premarket/morning/midday/eod research risk gates, source-aware alert caps, live 100-confidence paper capture, and a separate source-labeled Carter Squeeze lane.
- Teach this as: current student prompt first, original seed prompt only if you want to explain the build history.

## Slide Outline

1. Session 1 / Build The Alert Bot Project Plan
   - Student sees the purpose of the class: build the blueprint first.
   - Speaker notes remind the instructor to frame this as educational software, not financial advice.

2. Outcome / What Students Build Today
   - Student sees the artifacts they should leave with.
   - Speaker notes clarify that Session 1 is the plan and boundaries, not full code completion.

3. Setup / Use A Blank Student Folder
   - Student sees the blank-folder workflow, Codex setup, Thread A name, and Project Plan mode.
   - Speaker notes remind the instructor not to share live bot files or secrets.

4. Thread Map / Three Threads Keep The Build Clean
   - Student sees the three-thread course structure.
   - Speaker notes remind the instructor to keep Session 1 limited to Thread A.

5. Settings / Use Careful Build Settings
   - Student sees model, thinking, speed, and skills.
   - Speaker notes explain the skill roles.

6. Reference / The Dashboard Is The Product Target
   - Student sees the dashboard target and what to notice.
   - Speaker notes clarify that the screenshot is a visual target only.

7. Bot Contract / Boundaries That Must Not Drift
   - Student sees SPY/QQQ/IWM only, threshold `80`, `15m/30m/1h`, `60` seconds, market-window pause, Carter Squeeze separate, no broker, no auto-trading.
   - Speaker notes explain the current bot contract and that the original seed prompt is historical.

8. Thread A / Start With The Project Plan
   - Student sees the Thread A workflow without the full prompt text.
   - Speaker notes contain the full current Thread A student prompt for instructor copy/paste.

9. Lifecycle / Candidate First, Alert Later
   - Student sees the plain-English alert checkpoint path.
   - Speaker notes reinforce that a candidate is not an alert and an alert is not a trade.

10. Output / The Plan Must Produce These Artifacts
   - Student sees the required Project Plan artifacts.
   - Speaker notes tell the instructor to stop and revise if Codex skips any item.

11. Review Gate / Do Not Build Until The Plan Passes
   - Student sees the strict review checklist.
   - Speaker notes include the optional DOD review prompt.

12. Next / What Comes After The Plan
   - Student sees Thread B and Thread C previews.
   - Speaker notes remind the instructor that Session 1 stops at the Project Plan.

13. Close / Leave With A Reviewed Project Plan
   - Student sees the final completion checklist and safety sentence.
   - Speaker notes remind the instructor to have students save the Project Plan output.

## Instructor Timing

- 0:00-0:15: Slides 1-4, course frame, setup, and thread map.
- 0:15-0:30: Slides 5-7, Codex settings, dashboard target, and current bot contract.
- 0:30-0:45: Slide 8, instructor pastes the full prompt from speaker notes.
- 0:45-1:20: Students run Thread A in Project Plan mode and review the response.
- 1:20-1:40: Slides 9-11, lifecycle, required outputs, and review gate.
- 1:40-1:55: Fix any Project Plan issues.
- 1:55-2:00: Slides 12-13, preview Sessions 2 and 3 and close the safety loop.
