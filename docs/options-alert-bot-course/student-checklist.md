# Student Checklist

## Setup Checklist

- I know this is a local Python project.
- I know the course teaches software setup and validation, not financial advice.
- I have the Codex desktop app installed before Session 1.
- I have ChatGPT/Codex access for prompt-driven coding.
- I have ChatGPT Plus or higher as the minimum plan for this class.
- I have a modern browser.
- I can open the course link or project folder.
- I know not to share real credentials.
- I know this bot is alert-only and does not place trades.

## Pre-Session Permission Checklist

- I can install software on my laptop.
- I can create folders and files.
- I can install Codex.
- I can sign in to ChatGPT/Codex.
- I can verify I am using ChatGPT Plus or higher.
- I can allow Codex to access the course project folder if my computer asks.
- I can open a local dashboard in my browser if Codex starts one during class.
- I can access my email and phone for two-factor codes.
- If setup gives me trouble, I will try before class and bring the issue to class for help.

## Download Checklist

Required:

- Codex desktop app before Session 1.
- A modern browser.

Optional only if I want a traditional local coding setup:

- Python 3.9 or newer.
- Git.
- VS Code or another code editor.
- GitHub Desktop if I prefer a visual Git app.

## Signup Checklist

Required for the course workflow:

- ChatGPT/Codex access.
- ChatGPT Plus or higher as the minimum plan.

Strongly recommended:

- TradingView free account for manual chart review.

Recommended if the project is distributed through GitHub:

- GitHub.

Optional live integrations:

- Telegram account, bot token, and chat ID.
- Alpha Vantage API key.
- Gmail account with 2-Step Verification and app password.

Not needed:

- Python before Session 1.
- Visual Studio Code before Session 1.
- Git before Session 1.
- GitHub Desktop before Session 1.
- OpenAI Platform account before Session 1.
- OpenAI API key before Session 1.
- OpenAI API call before Session 1.
- API-backed AI summaries before Session 1.
- Robinhood.
- Brokerage account.
- Funded trading account.
- Broker API access.
- Paid market data.

## Environment Variable Checklist

Use placeholders in class materials:

- `TELEGRAM_BOT_TOKEN=YOUR_TOKEN_HERE`
- `TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE`
- `GMAIL_SMTP_USERNAME=YOUR_EMAIL_HERE`
- `GMAIL_SMTP_PASSWORD=YOUR_APP_PASSWORD_HERE`
- `RESEARCH_EMAIL_TO=YOUR_EMAIL_HERE`
- `ALPHA_VANTAGE_API_KEY=YOUR_API_KEY_HERE`

Before sharing any repo copy:

- Real `.env` is not included.
- Backup env files are not included.
- Tokens, passwords, account IDs, and webhook URLs are not included.
- Deploy keys or private key folders are not included.

## Run Checklist

Commands students should recognize:

```bash
.venv/bin/python -m trading_bot backfill --days 5
.venv/bin/python -m trading_bot scan --once
.venv/bin/python -m trading_bot scan
.venv/bin/python -m trading_bot healthcheck
.venv/bin/python -m trading_bot replay --from YYYY-MM-DD --to YYYY-MM-DD
.venv/bin/python -m trading_bot paper_summary
.venv/bin/streamlit run dashboard/app.py
```

Classroom rule:

- Do not call real Telegram, Gmail, OpenAI, Alpha Vantage, or market-data services unless the instructor explicitly prepared safe credentials and a safe demo environment.

## Testing Checklist

- I can explain what pytest is.
- I know `.venv/bin/python -m pytest` is the main test command.
- I know tests passing means software behavior passed checks.
- I know tests passing does not prove a profitable strategy.
- I know tests should not expose secrets or call live services.

## SPY/QQQ/IWM Configuration Checklist

- `SPY` is present.
- `QQQ` is present.
- `IWM` is present.
- No other symbols are added for this course.
- Alert threshold is `80`.
- Alert timeframes are `15m`, `30m`, and `1h`.
- Scanner cadence is `900` seconds.

## Alert Review Checklist

Before trusting any alert as worth manual review:

- Confirm the symbol is `SPY`, `QQQ`, or `IWM`.
- Confirm the alert is not stale.
- Confirm the setup type.
- Confirm the direction.
- Confirm entry zone, invalidation, and targets.
- Confirm confidence score and score reasons.
- Confirm no hard blockers are present.
- Confirm duplicate, cooldown, and daily cap rules did not suppress or distort context.
- Confirm the chart manually on TradingView.

## Risk-Management Checklist

- Stale data blocks or warns.
- Weak volume blocks or penalizes.
- Chop blocks or penalizes.
- Poor risk/reward blocks or penalizes.
- Overextension blocks or penalizes.
- Conflicting timeframes block or penalize.
- Research risk blocks or penalizes.
- Missing same-day research is visible.
- AI summary text does not override rules.
- No-trade is accepted as a correct outcome.

## Debugging Checklist

When asking Codex for help:

- Include the exact command.
- Include the exact error or traceback.
- Include what you expected.
- Include relevant file names.
- Include whether credentials are placeholders.
- Do not paste `.env`.
- Do not paste tokens or passwords.
- Ask Codex to inspect read-only before proposing edits.
- Ask Codex not to change trading behavior unless that is the explicit task.

## Final Project Checklist

Your final report includes:

- Architecture diagram.
- One alert lifecycle trace.
- Manual review checklist.
- Replay validation plan.
- Dashboard QA checklist.
- One pending-review improvement idea.
- One paragraph on why this is educational software, not financial advice.
- Final sentence: "This system is alert-only and does not place trades."

## Manual Review Checklist Before Acting On Any Alert

Educational warning: this course does not recommend acting on alerts. If a user outside class chooses to manually evaluate an alert, they are responsible for every decision.

Minimum manual review:

- Confirm chart on TradingView.
- Confirm the relevant timeframe.
- Confirm price level, volume, VWAP, and invalidation.
- Confirm data is not stale.
- Confirm no high-risk research block exists.
- Confirm options spread, liquidity, and affordability manually.
- Define maximum loss before any decision.
- Do not chase outside the planned zone.
- Journal the result and emotional state.
