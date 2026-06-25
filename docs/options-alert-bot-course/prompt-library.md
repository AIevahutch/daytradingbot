# Prompt Library

## Label Rules

Every prompt in this file uses one of these labels:

- Exact prompt found in repo
- Reconstructed prompt - not found verbatim in repo
- Recommended future prompt

Exact prompts cite the repo location where they were found. Reconstructed prompts are designed for teaching the same current bot but were not found verbatim.

## Session 1 Thread A Current Student Build Prompt

Label: Reconstructed current teaching prompt - updated from repo facts and recent bot changes

Use this as the main Session 1 Thread A prompt. Students should create a blank folder on their own computer, start a new Codex thread, choose Project Plan mode, and paste this full prompt as one prompt.

Teaching note:

- This prompt reflects the current course bot contract, including the `80` threshold, `15m`/`30m`/`1h` alert timeframes, configured `60` second scan cadence, market-data window pause, manual-review-only workflow, source-labeled Carter Squeeze lane, `morning` research phase, research risk gates, source-aware alert caps, and live 100-confidence paper tracking.
- It is designed to produce the same architecture boundaries and DOD as the instructor bot, not identical code or guaranteed trading results.
- The original recovered master prompt is preserved in the next section as history, but this current prompt is the one to paste during Session 1.

```text
GOAL

Build an educational, alert-only options bot for SPY, QQQ, and IWM that helps a human review potential day-trading setups. The bot must scan market conditions only during the configured market-data window, score alerts, show a Streamlit dashboard, support manual review, support paper/replay validation, support a separate Carter Squeeze signal lane, support conservative research risk gates, and keep every workflow manual-review-only.

This is not financial advice, not a profit promise, and not an auto-trading system.

Use Codex in Project Plan mode. Use GPT-5 or the highest available Codex reasoning model with high thinking/reasoning and standard speed. Use the following skills if available: principal-ml-engineer, quant-researcher, and ui-ux-designer.

CONTEXT

I want to build the current version of my SPY/QQQ/IWM alert bot as an educational software engineering project.

The bot should be a Python 3.9+ project with:

- Streamlit dashboard
- SQLite storage
- yfinance market data
- pytest tests
- Telegram alert support
- optional local AI/research-summary support
- Gmail/email delivery support for research summaries if configured
- replay and paper validation for educational evidence only
- no broker execution
- no Robinhood integration
- no automatic live rule changes
- no automatic trading

The bot must only support these symbols:

- SPY
- QQQ
- IWM

Current core alert settings:

- Alert threshold: 80
- Alert timeframes: 15m, 30m, 1h
- Active scan cadence from config: 60 seconds
- Code default may remain 900 seconds if no config override is loaded, but the configured bot should use 60 seconds
- Bot market timezone: America/New_York
- Dashboard/display timezone: America/Los_Angeles
- Market-data window: premarket start 04:00 ET through after-hours end 20:00 ET
- Scanner should pause outside the configured market-data window and on non-trading days before fetching market data
- Stale data threshold: 7 minutes
- Duplicate cooldown: 90 minutes
- Symbol cooldown: 30 minutes
- Core max alerts per symbol per day: 3
- Manual review required before any trade decision
- Alerts are decision-support only

The bot should include a main alert workflow plus a separate parallel Carter Squeeze signal source.

Core signal expectations:

- Score alerts from market conditions
- Require explainable reasons for each alert
- Include confidence/score output
- Include risk flags
- Include symbol, direction, timeframe, setup type, entry context, stop/risk context, and target/risk-reward context when available
- Require 80+ confidence/score before alerting
- Hard blockers can still prevent an alert even if the score reaches 80
- Use no-trade, watch-only, and alert-ready statuses
- Rank alertable setup records and send only the highest-priority eligible setup per source/symbol scan cycle
- Suppress lower-priority alertable setup records as watch-only/no-trade notes instead of blasting every candidate
- Preserve source labels so alerts, paper results, replay results, and dashboard stats can separate the core bot from Carter Squeeze
- Use `core_model` / `Core Model` labels for the main signal lane
- Capture 100-confidence core alerts into the live paper run/source named `live_100_alerts`

Carter Squeeze expectations:

- Keep Carter Squeeze as a separate signal source, not mixed into the core bot
- Support SPY and QQQ for Carter Squeeze
- Use `carter_squeeze` / `Carter Squeeze` labels
- Use confirmation timeframes 30m and 1h
- Require all-index alignment using SPY, QQQ, and IWM
- Require tactical 1R path
- Use tactical exit multiple of 1.0R
- Require minimum risk/reward of 2.0
- Use Carter Squeeze max alerts per symbol per day: 2
- Use Carter Squeeze duplicate cooldown: 90 minutes
- Use Carter Squeeze symbol cooldown: 30 minutes
- Preserve the 80+ alert threshold
- Make it removable and clearly labeled
- Capture Carter Squeeze paper tracking separately when implemented, using a separate live/paper source such as `live_carter_squeeze`

Current strategy and scoring expectations:

- Keep excluded setup types out of the main alert stream:
  - VWAP reclaim + retest
  - VWAP rejection + retest
- Block weak SPY VWAP reclaim longs
- Use strict index alignment for core alerts with SPY and QQQ
- For standalone level breaks, require a trending market condition and alignment across SPY, QQQ, and IWM
- Use VWAP quality checks for VWAP-related candidates
- Use opening-noise protection around weak VWAP setups
- Penalize weak volume, chop, overextension, stale data, conflicting timeframes, poor risk/reward, weak VWAP quality, VWAP whipsaw, momentum continuation risk, and standalone level-break risk
- Allow fast-momentum and all-index trend-continuation overrides only when the configured confirmation requirements are met
- Allow the midday momentum exception only when volume expansion, range expansion, recent move, market confirmation, and timeframe alignment meet the configured thresholds
- Alert-ready means eligible for human review only; it does not mean trade entry

Research/risk expectations:

- Research can be enabled
- Research may be required for alerts
- If research is required, alerts should respect the research risk gate
- Hard-block risk score: 65
- Caution risk score: 40
- Caution penalty: -8
- Hard-block penalty: -30
- Bias-conflict penalty: -6
- Research phases: premarket, morning, midday, eod
- Research phase times:
  - premarket: 08:15
  - morning: 10:00
  - midday: 12:00
  - eod: 16:10
- Use shared research phase constants instead of hard-coded phase lists
- If same-day research is required but missing, the scanner should block alerts and explain the missing research brief
- Research can block or penalize alerts, but research must not create alerts without a valid chart/setup candidate
- AI summaries and confidence scores are explanation/decision-support only
- Do not present AI output as trading authority
- Keep OpenAI/API summaries disabled by default unless the owner explicitly enables that path
- Do not require an OpenAI Platform account, OpenAI API key, or OpenAI API call for Session 1 or for the default local build
- Use deterministic/local fallback summary behavior when AI/API summaries are unavailable or disabled
- Do not invent external API requirements that are not needed by the current build

Optional services expectations:

- Telegram alerts are optional/configured only
- Telegram send attempts should be bounded by config, with max attempts 3 and retry delay 1 second
- Gmail/email delivery for research summaries is optional/configured only
- Alpha Vantage and other data-provider credentials are optional placeholders only unless the owner explicitly enables that path
- Do not send Telegram messages or emails during setup unless explicitly approved

Paper/replay expectations:

- Paper validation is educational evidence only
- Replay validation is educational evidence only
- Do not claim proof of profitability
- Support source-aware paper tracking where possible
- Support source-aware replay summaries where possible
- Keep live/paper tracking source-aware so core 100-confidence alerts and Carter Squeeze can be evaluated separately
- Store enough alert/setup detail for later review without implying trade execution
- Keep manual review in the workflow

Dashboard expectations:

- Build a Streamlit dashboard that lets a user review alerts manually
- Show alert details clearly
- Show signal source labels
- Show confidence/score
- Show reasons and risk notes
- Show no-trade/watch-only/alert-ready state clearly
- Show research decision, risk score, phase, and source status when available
- Show market-data freshness and scanner heartbeat/paused state when available
- Show paper/replay summaries where available
- Keep the UI clean, readable, and beginner-friendly
- Do not make the dashboard look like a broker execution platform

Safety expectations:

- Never place real trades
- Never connect to a broker
- Never auto-execute anything
- Never promise profits
- Never tell the user what to buy or sell
- Always frame the system as educational alert software and decision support
- Do not expose secrets
- Do not print .env values
- Do not commit credentials
- Include owner-facing warnings for .env files, saved credentials, deploy keys, Telegram tokens, Gmail credentials, and anything else that should be rotated before sharing

CONSTRAINTS

Build this conservatively.

Do not add broker execution.

Do not add Robinhood.

Do not add automatic trading.

Do not add automatic live rule changes.

Do not make claims of profitability.

Do not make the bot trade options automatically.

Do not use real secrets in code or documentation.

Do not read or print .env secret values.

Do not call external services during setup unless explicitly approved.

Do not run commands that send Telegram messages, emails, market scans, backfills, replay jobs, or live dashboards unless explicitly approved.

Do not overwrite unrelated existing files.

Keep changes scoped to the project.

Use clear file organization.

Use tests for risky logic.

Prefer simple Python modules over over-engineering.

Preserve the alert-only workflow.

Separate verified facts from assumptions in documentation.

Use source labels for parallel signal sources.

Keep Carter Squeeze separate from the core bot.

Use SQLite for local persistence.

Use Streamlit for the dashboard.

Use yfinance for market data.

Use pytest for tests.

DONE WHEN

The project has a working educational alert-only bot structure with:

- Python package layout
- Config file for symbols, thresholds, timeframes, cadence, research gates, and signal-source settings
- SPY/QQQ/IWM-only universe
- Alert threshold set to 80
- Timeframes set to 15m, 30m, and 1h
- Active configured scan cadence set to 60 seconds
- Manual-review-only alert workflow
- No broker execution
- No Robinhood
- No automatic trading
- Scanner pauses outside the configured market-data window and on non-trading days
- Core alert scoring module
- Separate Carter Squeeze signal-source module
- Source-aware alert storage
- Core max alert cap of 3 per symbol per day
- Carter Squeeze max alert cap of 2 per symbol per day
- Duplicate cooldown of 90 minutes
- Symbol cooldown of 30 minutes
- Ranked alert selection so only the highest-priority eligible setup is sent per source/symbol scan cycle
- Live paper capture for 100-confidence core alerts under `live_100_alerts`
- Source-aware paper/replay reporting where practical
- SQLite persistence
- Streamlit dashboard
- Telegram alert support as optional/configured only
- Research/risk gate support with premarket, morning, midday, and eod phases
- Research phase times set to 08:15, 10:00, 12:00, and 16:10
- Same-day research-required blocking behavior when enabled
- OpenAI/API summaries disabled by default unless explicitly enabled
- Local/deterministic research-summary fallback behavior where practical
- Gmail/email research-summary support only if configured
- Safety disclaimers in docs
- Secrets warnings in docs
- Tests for scoring, source labeling, Carter Squeeze behavior, research phase mapping, scanner market-window pause behavior, and key safety constraints
- README explaining setup, manual workflow, and safety boundaries
- Troubleshooting notes
- Clear statement that replay and paper validation are educational evidence, not proof of profitability

Before finishing, provide a final verification checklist. Each item must be marked either YES - VERIFIED or NO - NOT VERIFIED. If anything is not verified, explain why.

Final verification checklist:

- YES - VERIFIED: The bot remains alert-only
- YES - VERIFIED: No broker execution code was added
- YES - VERIFIED: No real secrets were printed or copied
- YES - VERIFIED: SPY, QQQ, and IWM are the only supported symbols
- YES - VERIFIED: Alert threshold is 80
- YES - VERIFIED: Alert timeframes are 15m, 30m, and 1h
- YES - VERIFIED: Configured scanner cadence is 60 seconds
- YES - VERIFIED: Scanner pauses outside the configured market-data window before fetching market data
- YES - VERIFIED: Core alert cap is 3 per symbol per day
- YES - VERIFIED: Carter Squeeze alert cap is 2 per symbol per day
- YES - VERIFIED: Carter Squeeze is separate and source-labeled
- YES - VERIFIED: Research gates include premarket, morning, midday, and eod phases
- YES - VERIFIED: OpenAI/API summaries are not required for the default local build
- YES - VERIFIED: Live 100-confidence core paper capture is source-labeled
- YES - VERIFIED: Dashboard shows manual-review information clearly
- YES - VERIFIED: Tests pass or skipped tests are clearly explained
- YES - VERIFIED: External-service commands were skipped unless explicitly approved
```

## Session 1 Thread A Original Master Build Prompt

Label: Exact prompt recovered from saved Codex build thread - not found verbatim in repo docs

Preserve this as the historical prompt Eva used to start the original SPY/QQQ/IWM alert bot build. Do not use this as the main Session 1 student prompt unless you intentionally want to teach the original seed prompt before teaching the current bot contract.

Teaching note:

- This is the original seed prompt Eva used to start the SPY/QQQ/IWM alert bot build.
- The original seed prompt says alerts should be `85-100`. The current course prompt above uses threshold `80`, timeframes `15m`, `30m`, `1h`, configured scanner cadence `60` seconds, manual review only, and a separate source-labeled Carter Squeeze lane.
- The prompt should produce the same architecture boundaries and safety posture, not identical code or guaranteed trading results.

```text
# THREAD 1 — MASTER BUILD

GOAL

Build a zero-cost advanced day-trading alert bot for personal use focused ONLY on SPY, QQQ, and IWM.

The bot will:
- analyze market structure, levels, psychology, and momentum
- detect high-probability day-trading setups
- send real-time Telegram alerts
- explain setups in plain English
- help reduce emotional/FOMO trading
- prioritize quality over quantity
- NEVER place trades automatically

The system should feel like a disciplined professional trading assistant using clean price action and market psychology rather than gambling or indicator overload.

---

CONTEXT

This project is inspired by:
- The Strat methodology
- level-based trading
- liquidity and market psychology
- professional discretionary day traders
- clean chart analysis styles similar to traders like itsjsla
- intraday index ETF trading behavior

The bot should ONLY track:
- SPY
- QQQ
- IWM

The bot should focus on:
- 5-minute
- 15-minute
- hourly
- daily context

Primary concepts:
- The Strat setups
- full timeframe continuity
- VWAP interactions
- previous day high/low
- premarket high/low
- weekly levels
- gap fills
- liquidity sweeps
- failed breakouts
- failed breakdowns
- reversal setups
- momentum continuation
- trend alignment
- chop detection
- emotional exhaustion/fakeouts

The bot should think like a disciplined trader:
- avoid overtrading
- avoid emotional chasing
- avoid low-volume chop
- avoid low-quality setups
- respect risk management
- prefer “NO TRADE” over forcing trades

---

CONSTRAINTS

- ZERO-COST MVP
- personal use only
- no domain needed
- no paid APIs initially
- no automated trade execution
- no Robinhood API integration
- Robinhood will ONLY be used manually for execution

Infrastructure:
- TradingView for charting
- Telegram Bot API for alerts
- Python backend
- Streamlit dashboard
- free market data initially
- local computer or free hosting only

DO NOT:
- build auto-trading
- build machine learning initially
- overcomplicate indicators
- optimize for entertainment
- build enterprise infrastructure

Focus on:
- consistency
- discipline
- repeatability
- psychological edge
- risk management
- clean execution

---

HIGH-CONFIDENCE ALERT FILTER

The bot should ONLY send trade alerts when the confidence score is between 85–100.

Aggressively filter out:
- chop
- emotional fakeouts
- weak volume
- unclear direction
- poor risk/reward
- overextended price action
- conflicting timeframe signals
- weak market confirmation

The goal is NOT constant activity.
The goal is disciplined, high-probability opportunities only.

The system should be comfortable sending:
- “NO TRADE”
- “Market conditions are low quality today”
- “No A+ setups detected”

---

ALERT REQUIREMENTS

Every alert must include:
- ticker
- setup type
- direction
- entry zone
- stop loss
- target 1
- target 2
- invalidation level
- confidence score
- risk/reward
- plain-English reasoning
- “avoid this trade if…” warning

Example:

SPY LONG SETUP
Setup: VWAP reclaim + prior day high retest
Entry: 542.20–542.50
Stop: 541.60
Target 1: 543.40
Target 2: 544.80
Confidence: 89/100

Reason:
SPY reclaimed VWAP, held retest, and QQQ confirmed strength.

Avoid if:
SPY loses VWAP or rejects below prior day high.

This is an alert only. Never place trades automatically.

---

TRADE PERFORMANCE TRACKING + P/L SYSTEM

The bot must include a complete trade-performance tracking system.

I will manually input:
- whether I took the trade
- entry price
- exit price
- contracts/shares
- realized P/L
- partial exits
- notes
- emotional state if applicable

The system should track:
- total P/L
- daily P/L
- weekly P/L
- monthly P/L
- win rate
- average win
- average loss
- expectancy
- profit factor
- max drawdown
- largest winner
- largest loser
- average hold time
- best setup type
- worst setup type
- best trading hours
- worst trading hours
- setup accuracy
- confidence score accuracy
- false positive rate
- no-trade day performance

The dashboard should display:
- cumulative P/L
- rolling performance
- equity curve
- performance by setup type
- performance by timeframe
- performance by market condition

The journal should support:
- manual notes
- emotional reflections
- lessons learned
- screenshots later
- mistake tagging:
  - FOMO
  - revenge trade
  - oversized position
  - poor entry
  - ignored stop
  - emotional trade

---

REINFORCEMENT LEARNING / CONTINUOUS IMPROVEMENT

The bot should include a reinforcement-learning-ready feedback loop so it can improve over time based on real trade outcomes.

The system should learn from:
- alerts that won
- alerts that lost
- alerts I ignored
- alerts I took
- trades I manually entered
- trades I manually exited
- realized P/L
- setup type performance
- confidence score accuracy
- market condition performance
- emotional mistake tags
- time-of-day performance

The bot should analyze patterns such as:
- which setups perform best
- which setups fail most
- which confidence scores are actually reliable
- which market conditions produce losses
- which timeframes are most accurate
- which alerts should have been filtered out
- which setup combinations produce the best risk/reward

IMPORTANT CONSTRAINT:
The bot must NOT automatically change live trading rules without review and approval.

Instead, it should:
- collect feedback
- analyze results
- suggest improvements
- recommend scoring adjustments
- recommend filters to add/remove
- show before/after performance simulations
- require manual approval before strategy updates are applied

Future reinforcement learning module:
- use historical alerts and manually entered P/L as training data
- create a reward system where profitable disciplined trades receive positive reward
- penalize low-quality trades, overtrading, chop trades, emotional entries, and poor risk/reward
- reward strong confirmations, clean risk management, and disciplined execution

---

TECHNICAL REQUIREMENTS

Build using:
- Python
- Telegram Bot API
- Streamlit
- TradingView for manual chart confirmation
- free market data APIs initially
- local machine or free hosting

Recommended architecture:
- modular services
- reusable strategy engine
- reusable data engine
- centralized logging
- clean configuration management
- scalable folder structure

---

BUILD REQUIREMENTS

Build:
1. architecture + folder structure
2. market data engine
3. strategy engine
4. confidence scoring system
5. psychology/risk engine
6. Telegram alert system
7. Streamlit dashboard
8. trade journal
9. P/L analytics
10. logging system
11. reinforcement-learning-ready analytics layer
12. README documentation

The dashboard should show:
- SPY/QQQ/IWM bias
- active setups
- key levels
- recent alerts
- trend direction
- confidence scores
- no-trade conditions
- performance metrics
- equity curve
- journal history
- setup performance analytics
- reinforcement-learning recommendations

---

DONE WHEN

The project is complete when:
1. The bot continuously scans SPY, QQQ, and IWM
2. The bot only alerts 85–100 confidence setups
3. Telegram alerts work successfully
4. Alerts clearly explain:
   - why the setup matters
   - where to enter
   - where to exit
   - when the setup fails
5. The bot filters low-quality conditions
6. The bot supports NO TRADE logic
7. Trade journaling works
8. Manual P/L tracking works
9. Performance analytics work
10. Dashboard works
11. Risk-management safeguards work
12. Reinforcement-learning-ready analytics work
13. The system remains zero-cost for MVP
14. README documentation explains:
   - setup
   - architecture
   - strategy logic
   - deployment
   - future upgrades

```

## Session 1 Thread A Architecture Prompt Set

Label: Reconstructed follow-up prompt set - not found verbatim in repo

Use these after the current student prompt if students need smaller follow-up prompts for Thread A: Build Alert Bot Architecture. These prompts should not replace the full current student prompt above.

Teaching note:

- These Session 1 prompts are reconstructed from the way the current bot was built and taught. They were not found verbatim in the repo history.
- Use the full `Goal / Context / Constraints / Done When` structure below for the most consistent student results.
- These prompts should produce the same architecture boundaries, safety contract, thread map, and DOD as the instructor bot. They should not be described as a guarantee of identical code or identical trading results.

Recommended Codex settings for the class workflow:

- Model: `GPT-5` or the highest available Codex reasoning model
- Thinking/reasoning: `High` for class build work; `Extra High` only for long instructor validation if available.
- Speed: `Standard` for teaching and validation; Fast mode only for short edits when credits are not a concern.
- Plan: ChatGPT Plus or higher.

Skill/thread map:

- Thread A: Build Alert Bot Architecture. Use base Codex, plus `principal-ml-engineer` as an architecture/approval-gate review lens and `ui-ux-designer` for dashboard/workflow clarity.
- Thread B: QA + Paper Trading Bot. Use base Codex plus validation prompts, `principal-ml-engineer` for evaluation/approval-gate thinking, and `ui-ux-designer` for dashboard QA.
- Thread C: Build Market Research Agent. Use `quant-researcher`, with `principal-ml-engineer` for conservative AI-summary guardrails and `ui-ux-designer` for research dashboard clarity.
- Skill note: `principal-ml-engineer` is a reusable ML/LLM architecture lens in this course, not a trading-strategy skill.

### Thread A Prompt 1 - Main Architecture Plan

```text
GOAL
Create the main project plan for a local SPY/QQQ/IWM alert-only options bot built with Codex. This is Thread A: Build Alert Bot Architecture.

CONTEXT
This is Session 1 of a beginner course. Students are using Codex in their own blank folder, not inside the instructor's live bot repo. The final project should be modeled after the current instructor bot: Python 3.9+, Streamlit dashboard, SQLite history, yfinance market data, optional Telegram alerts later, optional Gmail/email delivery for research summaries if configured, SPY/QQQ/IWM only, alert threshold 80, alert timeframes 15m/30m/1h, configured scanner cadence 60 seconds, market-data window pause, manual review only, premarket/morning/midday/eod research gates, source-aware caps, live 100-confidence paper capture, and a separate source-labeled Carter Squeeze lane.

CONSTRAINTS
Do not write trading code yet. Do not create broker execution. Do not add Robinhood. Do not add automatic trades. Do not add automatic live rule changes. Do not require an OpenAI Platform account, OpenAI API key, or OpenAI API call for Session 1. Do not create or request real secrets. Do not promise profits. This is educational software engineering, not financial advice.

DONE WHEN
Return a beginner-friendly architecture blueprint with project goal, safety contract, major modules, data flow, build phases, and a clear Done Definition. The blueprint must clearly say: This system is alert-only and does not place trades.
```

### Thread A Prompt 2 - Folder And Module Map

```text
GOAL
Create the folder and module architecture for Thread A.

CONTEXT
The student is building a fresh local project plan for the SPY/QQQ/IWM alert-only bot. The project should eventually have bot logic, dashboard views, safe config, tests, docs, and local runtime data. Session 1 is still planning only.

CONSTRAINTS
Include `trading_bot`, `dashboard`, `config`, `tests`, `docs`, and `data`. For each folder, explain what belongs there, what does not belong there, and what files we will probably create later. Keep secrets out. Do not add a real `.env`, API keys, broker credentials, account IDs, private instructor files, or runtime database files. Do not add broker execution or live trading folders.

DONE WHEN
Return a folder/module map that a beginner can understand. Each folder must have a plain-English purpose, example future files, and a safety note for what should not go there.
```

### Thread A Prompt 3 - Safe Settings Contract

```text
GOAL
Create the safe settings contract for the architecture plan.

CONTEXT
The current instructor bot is intentionally narrow and quiet. It watches only SPY, QQQ, and IWM. Alert eligibility starts at confidence 80, but hard blockers still prevent alerts. Alert review is based on 15m, 30m, and 1h completed candles. Configured scanner cadence is 60 seconds. Carter Squeeze is a separate, removable, source-labeled lane.

CONSTRAINTS
Use symbols `SPY`, `QQQ`, and `IWM` only. Use `alert_threshold: 80`. Use `alert_timeframes: [15m, 30m, 1h]`. Use `scan_cadence_seconds: 60` in the active config. Include `timezone: America/New_York`, `display_timezone: America/Los_Angeles`, `stale_data_minutes: 7`, premarket start `04:00`, regular start `09:30`, regular end `16:00`, after-hours end `20:00`, duplicate cooldown `90`, symbol cooldown `30`, core max alerts per symbol per day `3`, and Carter Squeeze max alerts per symbol per day `2`. Include `manual_approval_required_for_rule_changes: true`. Include research phase times for premarket `08:15`, morning `10:00`, midday `12:00`, and eod `16:10`. Include a `carter_squeeze` settings block that is enabled, separate from the core model, source-labeled, and removable. Add placeholder-only notes for Telegram, Alpha Vantage, Gmail, and optional summaries. Do not require an OpenAI Platform account, OpenAI API key, or OpenAI API call for Session 1. Do not include real secrets.

DONE WHEN
Return a settings contract table with setting name, value, purpose, and safety reason. Include the core bot and Carter Squeeze settings separately. End with a short note explaining that settings changes require manual review.
```

### Thread A Prompt 4 - Alert Lifecycle Diagram

```text
GOAL
Create a beginner-friendly alert lifecycle diagram and explanation.

CONTEXT
The alert lifecycle is the bot's review path, not a trade path. The bot should not jump from market data to a trade. It should move through checkpoints: market-data window check, completed 15m/30m/1h candles, levels, possible setup candidate, research gate, no-trade filters, score, ranked selection, output, SQLite history, optional source-aware paper capture, dashboard review, and journal.

CONSTRAINTS
Use plain English. Explain that a setup candidate is only a possibility. Explain that blockers can stop the idea even if the score is high. Explain that confidence 80 means alert-eligible only if no hard blockers apply. Explain that the scanner pauses before fetching data outside the configured market-data window. Explain that only the highest-priority eligible setup should be alerted per source/symbol scan cycle. Include the three possible outputs: no-trade, watch-only, or alert-ready. Make clear that alert-ready still means human review, not automatic trading.

DONE WHEN
Return one simple diagram, a one-paragraph explanation, and a five-sentence beginner version. The beginner version must include: "candidate first, alert later, and alert never means automatic trade."
```

### Thread A Prompt 5 - Thread And Skill Map

```text
GOAL
Split the course build into three Codex threads and map the right skills to each thread.

CONTEXT
Thread A is Build Alert Bot Architecture. Thread B is QA + Paper Trading Bot. Thread C is Build Market Research Agent. Students should not try to build the entire bot in one thread.

CONSTRAINTS
For each thread, list the goal, recommended model, thinking/reasoning setting, speed setting, skills to use, inputs, outputs, and handoff artifact. Include `principal-ml-engineer` as the architecture and approval-gate review lens, `ui-ux-designer` for dashboard/workflow clarity, `quant-researcher` for Thread C market research, and base Codex for normal repo/docs work. If a skill is a reusable lens rather than a dedicated trading skill, say that clearly.

DONE WHEN
Return a three-row thread map. The map must show what Thread A builds now, what Thread B builds later, what Thread C builds later, and what artifact passes from one thread to the next.
```

### Thread A Prompt 6 - DOD Review

```text
GOAL
Review the student's Session 1 Thread A output against the Done Definition.

CONTEXT
The student should have created only the architecture plan and safety blueprint. They should not have built the full QA/paper-trading bot or the full market research agent yet.

CONSTRAINTS
Be strict. Check for an alert-only safety contract, architecture plan, folder/module map, safe settings contract, plain-English alert lifecycle diagram, three-thread course map, Codex model/thinking/speed table, correct skill map, source-aware alert lane plan, market-data window pause, research phase plan with premarket/morning/midday/eod, core alert cap 3, Carter alert cap 2, live 100-confidence paper capture plan, and no-secrets confirmation. Do not approve anything that adds broker execution, Robinhood, automatic trades, automatic live rule changes, real secrets, OpenAI/API requirements for the default local build, or profit promises.

DONE WHEN
Return `PASS`, `FIX`, or `BLOCKED`. If the result is `FIX` or `BLOCKED`, give the smallest next step. End with: This system is alert-only and does not place trades.
```

## Project Discovery

Label: Reconstructed prompt - not found verbatim in repo

```text
Inspect this repository and explain what the current SPY/QQQ/IWM alert-only bot does. Identify the language, framework, dependencies, main folders, commands, external services, data flow, and safety boundaries. Do not change any files. Clearly separate verified facts from inferences.
```

## Repo Setup

Label: Reconstructed prompt - not found verbatim in repo

```text
Create a local Python 3.9+ project for an alert-only SPY/QQQ/IWM day-trading assistant. Use a virtual environment, requirements.txt, pyproject.toml, a config/settings.yaml file for non-secret settings, and a .env.example file with placeholder secrets only. Do not add broker execution or automatic trading.
```

## Environment Variables

Label: Reconstructed prompt - not found verbatim in repo

```text
Create a safe .env.example for this alert-only bot. Include placeholders for Telegram, OpenAI, Gmail SMTP, research email delivery, and Alpha Vantage. Do not include real credentials. Add comments that students must never commit real secrets.
```

## Market Data

Label: Reconstructed prompt - not found verbatim in repo

```text
Build a market-data layer that fetches free best-effort SPY, QQQ, and IWM candles with yfinance. Normalize candle columns, store local history, detect stale data, and resample raw 1m data into completed 15m, 30m, and 1h candles. Stale or missing data should produce cautious no-trade behavior.
```

## SPY/QQQ/IWM Filtering

Label: Reconstructed prompt - not found verbatim in repo

```text
Restrict the bot universe to SPY, QQQ, and IWM only. Add tests or checks that prevent accidental expansion beyond those symbols. Do not add crypto, futures, individual stocks, or broker-specific symbols.
```

## Options Chain Handling

Label: Reconstructed prompt - not found verbatim in repo

```text
Document that the current bot is an options alert workflow around the underlying ETFs, not a live options-chain selector. If options examples are included, keep them educational, use placeholders, require manual review, and never recommend a specific contract, strike, broker action, or guaranteed outcome.
```

## AI Signal Generation

Label: Reconstructed prompt - not found verbatim in repo

```text
Add an AI explanation layer for research summaries only. Keep rule-based scoring and risk gates as the source of truth. AI may summarize, format, and explain the research brief, but it must not create trades, override hard blockers, recommend contracts, or promise outcomes.
```

## Signal Explanation

Label: Exact prompt found in repo

Source: `trading_bot/summaries.py`

```text
You write concise trading research emails for an alert-only SPY/QQQ/IWM options dashboard. Do not recommend specific contracts, strikes, broker actions, or guaranteed outcomes. Use the provided rule-based decision as the source of truth.
```

## Day-Trading Rules

Label: Reconstructed prompt - not found verbatim in repo

```text
Implement setup detection for SPY, QQQ, and IWM day-trading alerts. Detect price-action candidates such as VWAP reclaim/reject, level break/hold, liquidity sweep reversal, failed breakout/breakdown, momentum continuation, and Strat-style continuation. Treat every candidate as untrusted until it passes no-trade filters, risk/reward checks, and scoring.
```

## Risk Management

Label: Reconstructed prompt - not found verbatim in repo

```text
Build a conservative risk-management layer for an alert-only bot. Penalize or block stale data, weak volume, chop, overextension, poor risk/reward, conflicting timeframes, mixed SPY/QQQ/IWM confirmation, risky session windows, missing same-day research, and high-risk macro conditions. Prefer no alert over a marginal alert.
```

## Alert Formatting

Label: Reconstructed prompt - not found verbatim in repo

```text
Format Telegram alerts as manual review messages. Include ticker, setup type, direction, entry zone, stop/invalidation, targets, confidence, risk/reward, plain-English reasoning, avoid-if warning, and a footer that says the bot is alert-only and the user must confirm manually before acting.
```

## Manual Review Workflow

Label: Reconstructed prompt - not found verbatim in repo

```text
Create a manual review workflow for every alert. Require the user to confirm the chart on TradingView, check research risk, confirm data freshness, verify liquidity and affordability for any options example, define maximum loss, avoid chasing outside the entry zone, and journal the result.
```

## Logging And History

Label: Reconstructed prompt - not found verbatim in repo

```text
Store local bot history in SQLite. Record alerts, failed delivery attempts, candles, research briefs, replay paper events, journal entries, performance metrics, and pending recommendations. Recommendations must stay pending review and must not change live rules automatically.
```

## Testing

Label: Exact prompt found in repo

Source: `docs/ACCEPTANCE_PROMPT.md`

Use the exact fenced prompt in that file to validate the bot with strict PASS / FAIL / BLOCKED gates. The prompt verifies repository setup, tests, health checks, scanner behavior, alerts, dashboard, journal, replay, deployment, validation phase, and the final alert-only safety statement.

Copy/paste teaching excerpt:

```text
You are validating the SPY/QQQ/IWM day-trading alert bot.

Your job is to prove whether the MVP is actually done. Be strict. Do not mark the project complete unless every required gate passes or the user explicitly accepts a documented exception.

Core rules:
- The bot tracks only SPY, QQQ, and IWM.
- It is alert-only and must never place trades.
- TradingView is manual confirmation only.
- Robinhood is not integrated.
- Free market data is best-effort; stale or questionable data must produce NO TRADE behavior.
- Strategy changes suggested by analytics must require manual review and approval.
```

## Debugging

Label: Reconstructed prompt - not found verbatim in repo

```text
Debug this bot without changing trading logic. First inspect the failing command, traceback, config, environment placeholders, recent logs, and relevant tests. Separate environment/setup problems from code problems. Do not expose secrets. Return the likely cause, safest verification step, and any proposed fix for owner review.
```

## A+ Precision Validation

Label: Exact prompt found in repo

Source: `docs/A_PLUS_PRECISION_PROMPT.md`

Use the exact fenced prompt in that file when tuning for higher precision. The prompt requires broad replay samples, before/after comparison, sample-size discipline, and explicit anti-overfitting language.

Copy/paste teaching excerpt:

```text
You are validating the A+ precision mode for the SPY/QQQ/IWM alert bot.

Primary objective:
- Maximize disciplined alert precision while preserving positive expectancy.
- Prefer fewer high-quality alerts over more marginal alerts.
- Never optimize solely to make one historical replay look good.

Required constraints:
- The bot remains alert-only and never places trades.
- Only SPY, QQQ, and IWM are allowed.
- Telegram alerts must still be a subset of 80-100 confidence setups.
- Strategy changes are recommendations until manually reviewed and approved.
- Free data quality limitations must be called out.
```

## Replay Validation

Label: Reconstructed prompt - not found verbatim in repo

```text
Validate replay and paper-trading behavior for SPY/QQQ/IWM. Confirm replay walks historical 1m candles chronologically, evaluates only completed 15m/30m/1h alert timeframe closes, avoids current-day daily lookahead, stores alerted/blocked/suppressed/ignored/missed events, and reports closed-alert win rate separately from open alerts, MFE/MAE, and tactical +1R outcomes.
```

## Documentation

Label: Recommended future prompt

```text
Create student-facing documentation for this exact SPY/QQQ/IWM alert-only bot. Include repo analysis, architecture, build history, rebuild sequence, prompts, safety language, troubleshooting, and a no-code-change confirmation. Do not change source code, config, tests, dependencies, or runtime behavior.
```

## Slide Creation

Label: Recommended future prompt

```text
Create markdown slide outlines for a 3-session beginner course. Each session is 2 hours. Teach the current bot only. Include slide titles, bullets, speaker notes, demo notes, activity notes, time markers, and repeated safety reminders.
```

## Instructor Scripts

Label: Recommended future prompt

```text
Create full instructor scripts for the 3-session course. Include what to say, what to demo, what students should do, where beginners may get confused, time checkpoints, and safety reminders. Keep the course focused on software construction and manual review, not financial advice.
```

## Prompt Consistency Audit

Label: Recommended future prompt

```text
Audit prompt and validation artifacts for consistency. Compare README, docs/ACCEPTANCE_PROMPT.md, docs/A_PLUS_PRECISION_PROMPT.md, docs/TESTING_VALIDATION_FRAMEWORK.md, issue templates, and config/settings.yaml. Flag stale thresholds, timeframe mismatches, missing alert-only language, broker-execution risk, and any prompt that implies real-money readiness before statistical validation and explicit owner approval.
```
