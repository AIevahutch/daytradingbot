# SPY/QQQ/IWM Options Alert Bot Course Package

## What This Package Is

This folder is a documentation and teaching package for the current SPY/QQQ/IWM day-trading options alert bot in this repository.

It is designed for a 3-session beginner course:

- Session 1: 2 hours
- Session 2: 2 hours
- Session 3: 2 hours
- Total: 6 hours

The course teaches students how the current bot is structured and how they would rebuild the same kind of local alert-only system in their own training repo.

## Who This Is For

This package is for total beginners who want to learn:

- How a local Python trading-alert project is organized.
- How Codex can help inspect, build, test, and document a software project.
- How market data, setup detection, scoring, alerts, replay, and journaling fit together.
- How to think about risk, manual review, and validation before trusting any alert.

Students do not need to be professional developers, but they should be comfortable opening a terminal, reading files, and copying commands carefully.

For the Codex-first version of this course, students do not need to install Python, Visual Studio Code, Git, or GitHub Desktop before Session 1. They need Codex installed, a ChatGPT/Codex login, and ChatGPT Plus or higher.

## What The Bot Does

Verified from the repository:

- Scans only `SPY`, `QQQ`, and `IWM`.
- Uses Python 3.9+.
- Uses a Streamlit dashboard.
- Stores local state in SQLite.
- Uses free best-effort yfinance market data.
- Builds alert context from completed `15m`, `30m`, and `1h` candles.
- Uses a default scanner cadence of `900` seconds.
- Evaluates price-action setups, no-trade conditions, research risk gates, and confidence scoring.
- Sends Telegram alerts only when a setup is eligible.
- Tracks replay, paper events, manual journal entries, analytics, and review-only recommendations.

## What The Bot Does Not Do

Verified from the repository:

- It does not place trades automatically.
- It does not connect to Robinhood.
- It does not connect to a broker for order execution.
- It does not authorize trades.
- It does not guarantee a win rate.
- It does not prove profitability.
- It does not automatically change live strategy rules.
- It does not remove the need for manual TradingView review.

## Educational And Risk Notice

This material and bot are for educational and research purposes only. They are not financial, investment, tax, or trading advice.

The bot is alert-only. It does not place trades, connect to a broker, or authorize trades. Any decision to trade is manual and solely the user's responsibility.

Options and day trading involve substantial risk, including loss of the full premium or more depending on strategy. Past replay, paper-trading, win-rate, or profit-factor results do not guarantee future performance.

AI summaries are only a formatting and explanation layer. Rule-based risk gates, manual review, and no-trade conditions remain the source of truth. Do not treat AI text, confidence scores, or research bias as permission to enter a trade.

## How To Use This Folder

Recommended reading order:

1. `README.md` for the package overview.
2. `session-1-prep-email.md` for the email to send before the first session.
3. `repo-analysis.md` for the current repo setup.
4. `architecture-map.md` for the plain-English system diagram.
5. `build-history.md` for verified and inferred build history.
6. `build-sequence.md` for the student rebuild sequence.
7. `prompt-library.md` for Codex prompts organized by build stage.
8. `course-3-session.md` for the full class plan.
9. `slides/` for markdown slide outlines.
10. `scripts/` for instructor scripts.
11. `student-checklist.md`, `troubleshooting.md`, and `safety-and-risk.md` for class support.

## Course Structure

Session 1 builds Thread A: the main alert-bot architecture plan. Students create the safety contract, module map, safe settings contract, alert lifecycle diagram, and three-thread build map.

Session 2 builds Thread B: the QA + paper-trading bot. Students turn the architecture into validation gates, replay behavior, paper events, `paper_summary`, and acceptance checks.

Session 3 builds Thread C: the market research agent. Students add the conservative research workflow, risk gates, source status, optional summaries, and email-delivery architecture.

## No-Code-Change Boundary

This course package documents the current bot. It does not change how the bot works.

Students may use `build-sequence.md` to rebuild a similar training project in their own repo. They should not apply those rebuild steps to this current repo unless they are intentionally starting a separate implementation exercise.
