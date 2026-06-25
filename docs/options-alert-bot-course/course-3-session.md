# 3-Session Course Plan

## Course Title

Build And Understand A SPY/QQQ/IWM Alert-Only Options Bot With Codex

## Target Student

This course is for total beginners who want to learn how a local AI-assisted trading-alert software project is structured.

Students are learning software construction, documentation, validation, and safe manual review. They are not learning live auto-trading or financial advice.

## Prerequisites

Recommended:

- Basic computer comfort.
- Ability to copy/paste commands.
- Codex desktop app installed before Session 1.
- ChatGPT/Codex login.
- ChatGPT Plus or higher as the minimum plan.
- A modern browser.
- Curiosity and patience.

Not required:

- Professional Python experience.
- Python installed locally before Session 1.
- Prior Streamlit experience.
- VS Code installed locally before Session 1.
- Git installed locally before Session 1.
- Broker API experience.
- Live options trading.
- Robinhood account.
- Funded trading account.
- Paid market data.

## Pre-Session 1 Prep Email

Send `session-1-prep-email.md` before the first class.

Minimum ready state:

- Laptop with permission to install Codex.
- Internet access.
- Codex desktop app installed before Session 1.
- ChatGPT/Codex login.
- ChatGPT Plus or higher as the minimum plan.
- Browser.

Optional integration setup:

- TradingView free account for manual chart review.
- GitHub account if the project is distributed through GitHub.
- Telegram bot token and chat ID for alert delivery.
- Local/deterministic summary fallback for class; no OpenAI Platform account, OpenAI API key, or OpenAI API call required.
- Alpha Vantage API key for live news and earnings research.
- Gmail app password for optional research email delivery.

Do not ask students to install Python, VS Code, Git, or GitHub Desktop before Session 1 unless you intentionally switch from a Codex-first workflow to a traditional local-dev workflow. Do not ask students to create a broker account or connect live trading.

## Learning Outcomes

By the end, students can:

- Explain what the current bot does and does not do.
- Identify the major repo folders and files.
- Trace data from yfinance candles through levels, filters, scoring, alerts, storage, and dashboard review.
- Explain why the bot is limited to `SPY`, `QQQ`, and `IWM`.
- Explain why alert eligibility starts at `80` confidence but still requires no hard blockers.
- Explain how research risk can block or penalize alerts.
- Explain replay, paper events, and no-lookahead validation.
- Use Codex prompts to inspect, rebuild, test, debug, and document a similar training project.
- Write a final proof report that separates "software works" from "strategy is profitable."

## Session 1: Thread A - Build Alert Bot Architecture

Time: 2 hours

Focus:

- Create the main project plan for the alert-only bot.
- Define the safety contract.
- Map the repo/folder architecture.
- Lock the safe settings contract.
- Draw the alert lifecycle.
- Split the remaining work into Thread B and Thread C.
- Teach Codex model, thinking, speed, and skill choices.
- Use dashboard screenshots as the visual target for the architecture plan.

Timed lesson plan:

- `0:00-0:10`: Explain the three Codex threads: Alert Bot Architecture, QA + Paper Trading Bot, Market Research Agent.
- `0:10-0:20`: Show the dashboard reference visuals and explain what students are planning toward.
- `0:20-0:30`: Call out skills: `principal-ml-engineer` for architecture/approval gates, `ui-ux-designer` for dashboard/workflow clarity, and `quant-researcher` for Thread C research.
- `0:30-0:38`: Set Codex defaults: GPT-5 or the highest available Codex reasoning model, High reasoning for class build work, Standard speed, Plus minimum.
- `0:38-0:58`: Create the Thread A safety contract and architecture backlog.
- `0:58-1:15`: Create the folder/module architecture plan.
- `1:15-1:31`: Create the safe settings contract: `SPY/QQQ/IWM`, threshold `80`, `15m/30m/1h`, configured cadence `60`, Carter Squeeze separate and source-labeled.
- `1:31-1:47`: Create the alert lifecycle diagram.
- `1:47-1:55`: Create the Thread B/Thread C handoff and skill map.
- `1:55-2:00`: Run the Session 1 DOD review prompt.

Exercises:

- Create a one-page architecture blueprint.
- Label each folder as code, dashboard, config, tests, docs, runtime data, or future integration.
- Write one sentence explaining why this bot cannot place trades.
- Write the three-thread build map, identify which thread owns QA/paper trading, identify which thread owns market research, and explain where `principal-ml-engineer`, `ui-ux-designer`, and `quant-researcher` belong.

Checkpoint:

- Student can explain the Thread A architecture and can say what is intentionally deferred to Thread B and Thread C.
- Student can explain that `principal-ml-engineer` is a reusable architecture/approval-gate lens, not trading logic.

Homework:

- Read `architecture-map.md`, `build-sequence.md`, and `prompt-library.md`.
- Prepare one question about the architecture.
- Bring the Thread A blueprint to Session 2.

## Session 2: Thread B - QA + Paper Trading Bot

Time: 2 hours

Focus:

- Acceptance validation.
- Replay mechanics.
- Paper-event storage.
- No-lookahead validation.
- `paper_summary` interpretation.
- A+ precision checks.
- Dashboard QA for paper/replay views.

Timed lesson plan:

- `0:00-0:10`: Recap Thread A architecture and DOD.
- `0:10-0:25`: Explain validation layers: technical, replay, live paper, statistical, small-size live later only with owner approval.
- `0:25-0:45`: Use `docs/ACCEPTANCE_PROMPT.md` as the strict PASS / FAIL / BLOCKED gate.
- `0:45-1:05`: Build replay/paper-event requirements.
- `1:05-1:25`: Check completed `15m/30m/1h` candle timing and no-lookahead rules.
- `1:25-1:40`: Interpret `paper_summary`, MFE/MAE, strict outcomes, and tactical +1R outcomes.
- `1:40-1:55`: Use `docs/A_PLUS_PRECISION_PROMPT.md` for anti-overfitting review.
- `1:55-2:00`: Checkpoint and homework.

Exercises:

- Draft tests for sub-80 suppression, 80+ eligibility, duplicate suppression, research hard block, and replay completed-candle timing.
- Create a PASS / FAIL / BLOCKED validation matrix.
- Explain why replay/paper evidence is not proof of profitability.

Checkpoint:

- Student can explain how Thread B validates behavior without creating live-trading permission.

Homework:

- Prepare the validation report outline for the final project.
- Bring one paper/replay question to Session 3.

## Session 3: Thread C - Build Market Research Agent

Time: 2 hours

Focus:

- Use the `quant-researcher` skill.
- Build conservative premarket, midday, and EOD research briefs.
- Add research risk gates.
- Keep AI summaries as explanation only.
- Add optional Alpha Vantage, Gmail, and summary pathways.
- Connect research status back to scanner and dashboard review.

Timed lesson plan:

- `0:00-0:10`: Recap Thread A architecture and Thread B validation.
- `0:10-0:25`: Introduce `quant-researcher` and its alert-only operating contract.
- `0:25-0:45`: Build research evidence inputs: macro calendar, Fed, CPI/jobs, news, earnings/options, VIX, fear/greed, SPY/QQQ/IWM tape.
- `0:45-1:05`: Build risk scoring, `trade_today`, `decision`, `drivers`, `hard_blocks`, and `source_status`.
- `1:05-1:25`: Connect research as blocker/penalty only; never as an alert creator.
- `1:25-1:40`: Add optional summaries and Gmail delivery with placeholders and deterministic fallback.
- `1:40-1:55`: Dashboard review: Trade Today, Risk Score, Bias, Phase, source chips, evidence expander.
- `1:55-2:00`: Final project briefing and safety close.

Exercises:

- Classify research scenarios as allow, penalize, hard-block, or source-failure block.
- Write one prompt that invokes `quant-researcher` for a premarket brief.
- Explain why research can block or penalize but cannot create a trade.

Checkpoint:

- Student can explain how the market research agent supports manual review without becoming a trading system.

Homework:

- Complete the final project proof report.

## Final Project

Title: Alert Lifecycle Proof Report

Deliverables:

- One plain-English architecture diagram.
- One traced lifecycle for a no-trade, watch-only, blocked, or alert-ready event.
- One manual-review checklist.
- One replay validation plan.
- One dashboard QA checklist.
- One pending-review improvement proposal.
- One paragraph explaining why the bot does not place trades.

Required final sentence:

```text
This system is alert-only and does not place trades.
```

## Common Beginner Mistakes

- Thinking a setup candidate is the same as an alert.
- Thinking an alert is the same as a trade.
- Trusting AI text more than rule-based risk gates.
- Forgetting that free market data can be stale.
- Treating replay win rate as a future guarantee.
- Putting real secrets in `.env.example`.
- Running live service tests during a classroom walkthrough.
- Changing strategy rules before collecting enough evidence.

## Safety Reminders

- No financial advice.
- No profit promises.
- No guaranteed win rate.
- No live auto-trading.
- No broker execution.
- No blindly trusting AI-generated summaries.
- Every alert requires manual review.
- No-trade is a valid outcome.
