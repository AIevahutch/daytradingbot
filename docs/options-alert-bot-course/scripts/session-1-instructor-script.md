# Session 1 Instructor Script

## Session Goal

Students leave Session 1 with Thread A complete: a reviewed Project Plan for the main SPY/QQQ/IWM alert-bot architecture.

Thread A is not the full bot implementation. It is the architecture and safety blueprint that later threads build from.

## Deck Rule

The visible slides are student-facing only.

Instructor notes, private reminders, setup nuance, and copy/paste text belong in speaker notes. The full current Thread A student prompt is in the speaker notes for slide 8, `Start With The Project Plan`.

## Before Students Paste Anything

What to say:

"Today we are building the plan first. In Codex, this first thread should be created in Project Plan mode."

"Do not open my live bot folder. Do not use my repo. Create your own blank folder on your computer, for example `SPY-QQQ-IWM-Alert-Bot-Student`."

"The key sentence is: this system is alert-only and does not place trades."

Safety reminder:

- Do not share `.env`, `.env.save`, deploy keys, logs, databases, or credentials.
- Do not add broker execution, Robinhood automation, or automatic live rule changes.
- Do not promise profits.

## 0:00-0:15 - Course Frame And Setup

Use slides 1-3.

What to say:

"This course is three threads. Thread A is the main alert-bot architecture. Thread B is the QA and paper-trading validation bot. Thread C is the market research agent."

"The dashboard screenshot is the product direction. It is not a file handoff. Students should build in their own blank folder."

## 0:15-0:30 - Codex Settings And Current Contract

Use slides 4-6.

Recommended class settings:

- Model: `GPT-5` or the highest available Codex reasoning model
- Thinking/reasoning: `High`
- Speed: `Standard`
- Plan: ChatGPT Plus or higher

Skills to call out:

- `principal-ml-engineer`: architecture, evaluation, approval gates, and guardrails.
- `ui-ux-designer`: dashboard clarity and manual-review workflow polish.
- `quant-researcher`: Session 3 market research briefs and conservative risk gates.

Important note:

"The original seed prompt is preserved in the prompt library as build history. For class, we are using the updated student prompt that matches the current bot contract: threshold `80`, alert timeframes `15m`, `30m`, `1h`, configured scanner cadence `60` seconds, market-data window pause, manual review only, premarket/morning/midday/eod research risk gates, source-aware alert caps, live 100-confidence paper capture, and a separate source-labeled Carter Squeeze lane."

## 0:30-0:45 - Thread A Build Step

Use slide 8.

Instructor action:

1. Open PowerPoint speaker notes for slide 8.
2. Copy everything between `COPY/PASTE START` and `COPY/PASTE END`.
3. Paste it into the student's Thread A Codex chat.
4. Confirm Thread A is in Project Plan mode before submitting.

What to say:

"This is the full current Thread A prompt. I am pasting it into chat for you. Do not paste it piece by piece. Paste it as one prompt."

"This prompt works because it gives Codex the four pieces beginners usually forget: goal, context, constraints, and done when."

## 0:45-1:20 - Student Build Time

Student actions:

1. Create or open their blank student folder.
2. Start a new Codex thread named `Thread A - Build SPY/QQQ/IWM Alert Bot Project Plan`.
3. Choose Project Plan mode.
4. Receive or paste the full current Thread A student prompt.
5. Ask Codex to return the Project Plan first.
6. Review the output before allowing any build.

What students should verify:

- It says alert-only.
- It uses only SPY, QQQ, and IWM.
- It has no broker execution.
- It has no real secrets.
- It has no profit promise.
- It separates Thread A from QA/paper validation and market research.
- It keeps Carter Squeeze separate and source-labeled.
- It uses configured scanner cadence `60` seconds.
- It pauses scanning outside the configured market-data window before fetching data.
- It keeps the core alert cap at `3` per symbol per day and Carter Squeeze at `2`.
- It includes the `morning` research phase between premarket and midday.
- It does not require an OpenAI Platform account or OpenAI API key for the default local build.

## 1:20-1:40 - Lifecycle, Output, And Review Gate

Use slides 8-10.

What to say:

"The alert lifecycle is the bot asking: is this idea even allowed to become an alert?"

"A setup candidate is not an alert. An alert is not a trade. A trade is always manual."

"Do not let Codex build until the plan passes the review gate."

Session 1 DOD:

- Thread A Project Plan exists.
- Architecture blueprint exists.
- Folder/module map exists.
- Safe settings contract exists.
- Plain-English alert lifecycle exists.
- Three-thread map exists.
- No real secrets and no live trading permissions.

## 1:40-1:55 - Fix The Plan If Needed

Use the optional DOD review prompt from slide 10 speaker notes if the plan feels incomplete.

Common fixes:

- Ask Codex to remove broker execution.
- Ask Codex to add no-secrets handling.
- Ask Codex to clarify SPY/QQQ/IWM only.
- Ask Codex to separate Thread A from QA/paper and research.
- Ask Codex to add a clear Done Definition.

## 1:55-2:00 - Close

Use slides 11-12.

What to say:

"Session 2 is where we prove behavior with QA, replay, and paper validation. Session 3 is where market research becomes a conservative risk gate."

"For today, success means the Project Plan is reviewed and safe."

Final sentence:

"This system is alert-only and does not place trades."
