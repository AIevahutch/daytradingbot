# Session 1 Prep Email

## Purpose

Send this email 3-7 days before Session 1 so students can arrive with the right software, accounts, and permissions.

This prep list is for building and understanding the exact current SPY/QQQ/IWM alert-only bot using Codex. It does not ask students to set up a traditional local Python developer environment before class, open a broker account, fund an account, or connect live trading.

Codex installation is essential before class. Students should also have ChatGPT Plus or higher before class; Plus is the minimum plan for this course workflow.

## Copy/Paste Email

Subject: Before Session 1: Setup Checklist For The SPY/QQQ/IWM Alert Bot Course

Hi [Student Name],

I am excited for Session 1 of our SPY/QQQ/IWM alert bot course.

Before class, please complete as much of the checklist below as you can. Codex installation is essential before Session 1, and you will need ChatGPT Plus or higher.

If you have trouble setting anything up, I can help you in class. Please still try before class so we can keep the session smoother and spend more time building instead of troubleshooting installs.

Important safety note: this course is about software construction and manual review. It is not financial advice, not live auto-trading, and not a promise of profit. You do not need a broker account, Robinhood account, funded trading account, or real options trades for this class.

## 1. Computer Permissions You Will Need

Please use a laptop where you are allowed to:

- Install software.
- Create folders and files.
- Download and install Codex before class.
- Sign in to ChatGPT/Codex with Plus or higher.
- Open course files or a course repo link.
- Allow Codex to access the course project folder if your computer asks.
- Use the internet for Codex, course files, and optional API setup.

If you are on a school or work computer, please confirm you are allowed to install Codex. If your computer blocks installs, bring that up before class.

## 2. Download To Install Before Class

Required:

- Codex desktop app: https://chatgpt.com/download/
- A modern browser such as Chrome, Safari, Edge, or Firefox.

Optional only if you personally want a traditional local coding setup:

- Python 3.9 or newer.
- Git.
- Visual Studio Code.
- GitHub Desktop.

Notes:

- You do not need to install Python before Session 1 if we are working through Codex.
- You do not need to install Visual Studio Code before Session 1 if we are working through Codex.
- You do not need Git or GitHub Desktop before Session 1 unless I specifically send a GitHub-based workflow.
- If your computer asks whether Codex can access a project folder, allow it for the course folder.

## 3. Accounts To Create Before Class

Required for the course workflow:

- ChatGPT account with access to Codex.
- ChatGPT Plus or higher. Plus is the minimum plan for this class workflow. It is the $20/month plan in the U.S. at the time of writing; confirm the current price on the official pricing page before signing up: https://chatgpt.com/pricing/

Strongly recommended for manual chart review:

- TradingView free account: https://www.tradingview.com/

Recommended if I send the project through GitHub:

- GitHub account: https://github.com/signup

Needed only if you want the exact live alert/research integrations working on your own machine:

- Telegram account and Telegram bot token from BotFather: https://core.telegram.org/bots/tutorial
- Alpha Vantage free API key for live news and earnings research context: https://www.alphavantage.co/support/#api-key
- Gmail account with 2-Step Verification and an app password if you want Gmail SMTP research emails: https://support.google.com/accounts/answer/185833

Important:

- Your ChatGPT Plus/Codex login is enough for the Codex-first class workflow.
- You do not need an OpenAI Platform account or OpenAI API key for Session 1.
- We are not using an OpenAI API call for Session 1.
- The course can use the bot's local/deterministic summary path instead of API-backed AI summaries.
- Gmail app passwords require 2-Step Verification and may not be available on all work/school accounts.
- Telegram, Alpha Vantage, and Gmail credentials are optional for Session 1. We can use placeholders while learning the repo.

## 4. What You Do Not Need

Please do not sign up for or connect:

- Robinhood.
- A brokerage account.
- A funded trading account.
- Broker API access.
- Paid market data.
- Live order routing.
- Python.
- Visual Studio Code.
- Git.
- GitHub Desktop.
- OpenAI Platform account.
- OpenAI API key.
- OpenAI API call.

The bot we are studying is alert-only. It does not place trades.

## 5. Permissions For API Keys And Tokens

If you choose to create optional service keys, keep them private.

Never paste real values into:

- Class chat.
- Screenshots.
- Shared docs.
- GitHub.
- Codex prompts.
- `.env.example`.

Use placeholders in class:

```text
TELEGRAM_BOT_TOKEN=YOUR_TOKEN_HERE
TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE
GMAIL_SMTP_USERNAME=YOUR_EMAIL_HERE
GMAIL_SMTP_PASSWORD=YOUR_APP_PASSWORD_HERE
RESEARCH_EMAIL_TO=YOUR_EMAIL_HERE
ALPHA_VANTAGE_API_KEY=YOUR_API_KEY_HERE
```

## 6. Quick Readiness Check

Before class:

- Install Codex.
- Sign in with the ChatGPT account that has Plus or higher.
- Open Codex and confirm you can start a new task or thread.
- Keep your ChatGPT login available.

If Codex will not install or you cannot access it, do not panic. Send me a screenshot of the error before class, or bring it to Session 1 and we will troubleshoot. The important thing is that you try before class, because Codex setup is the one essential setup item.

## 7. Project Folder For Class

During Session 1, each student will create their own blank project folder on their own computer.

Example folder name:

```text
SPY-QQQ-IWM-Alert-Bot-Student
```

Please do not open, edit, or work inside anyone else's bot folder. We will build in your own student folder so your work stays separate and safe.

## 8. Bring To Class

Please bring:

- Your laptop.
- Charger.
- Access to your email.
- Access to your phone for two-factor login codes.
- Your ChatGPT/Codex login with Plus or higher.
- Your GitHub login if I send the class repo through GitHub.
- Optional service keys saved privately if you created them.

Again, no broker account and no live trades are needed.

See you in Session 1,

[Your Name]

## Instructor Notes

### Minimum Ready State

A student can fully participate in Session 1 with only:

- Laptop.
- Internet.
- Codex desktop app installed.
- ChatGPT/Codex login.
- ChatGPT Plus or higher.
- Browser.
- Course link or project folder access.

Codex installed plus ChatGPT Plus or higher is the essential pre-class setup. If a student struggles, help them in class, but ask them to try before class so setup does not take over the session.

In Session 1, have each student create a fresh blank project folder on their own computer, such as `SPY-QQQ-IWM-Alert-Bot-Student`, and open that folder in Codex. Do not give students access to the instructor's live bot repo.

### Optional Integration Ready State

A student can turn on more of the exact bot later if they also have:

- Telegram bot token and chat ID.
- Alpha Vantage API key.
- Gmail SMTP username and app password.
- TradingView account for manual confirmation.
- GitHub account if the project is distributed through GitHub.

### Do Not Require For Session 1

Do not require:

- Python.
- Visual Studio Code.
- Git.
- GitHub Desktop.
- OpenAI Platform account.
- OpenAI API key.
- OpenAI API call.
- Broker account.
- Robinhood account.
- Real-money account.
- Paid data feed.
- Live API calls.
- Telegram test alert.
- Gmail email test.
- Alpha Vantage call.

### Suggested Instructor Framing

Say this out loud at the start of Session 1:

```text
If you only have placeholders today, that is fine. We are learning the repo, architecture, and safety workflow first. Live service credentials are optional and private. This system is alert-only and does not place trades.
```
