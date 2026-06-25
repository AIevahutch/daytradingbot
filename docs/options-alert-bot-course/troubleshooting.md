# Troubleshooting

## General Rule

Troubleshoot software without weakening safety rules. Do not loosen filters just to make alerts appear.

## Install Issues

Symptoms:

- `python` not found.
- Virtual environment does not activate.
- `pip install -r requirements.txt` fails.
- Streamlit command not found.

What to check:

- Python 3.9+ is installed.
- The terminal is inside the repo.
- `.venv` is activated or commands use `.venv/bin/python`.
- Dependencies were installed in the correct environment.

Safe Codex prompt:

```text
I am setting up the SPY/QQQ/IWM alert-only bot. I ran COMMAND and got ERROR. Please diagnose the setup issue without changing trading logic or reading secrets. Tell me the likely cause and the safest next command.
```

## Missing Dependency Issues

Symptoms:

- `ModuleNotFoundError`.
- `ImportError`.
- Streamlit cannot import project modules.

What to check:

- `requirements.txt` was installed.
- `pyproject.toml` pytest `pythonpath` includes the repo root.
- The command is run from the project root.

Safe Codex prompt:

```text
Diagnose this Python import error for the alert-only bot. Here is the command and traceback. Inspect dependency files and imports first. Do not change bot behavior.
```

## Environment Variable Issues

Symptoms:

- Telegram not configured.
- OpenAI summary disabled or unavailable.
- Gmail email fails.
- Alpha Vantage sources are missing.

What to check:

- `.env` exists locally.
- Values are placeholders or real private values depending on environment.
- `.env.example` has no real secrets.
- Optional services may be intentionally missing.

Never paste:

- API keys.
- Tokens.
- Passwords.
- Account IDs.
- Webhook URLs.
- Private URLs.

Safe Codex prompt:

```text
The bot reports a missing environment variable for SERVICE. I will not paste secrets. Please inspect the config and .env.example shape and explain which placeholder names are expected.
```

## Market Data Issues

Symptoms:

- No candles.
- Stale data.
- Empty yfinance result.
- Unexpected no-trade.

What to check:

- Market hours.
- Symbol list is `SPY`, `QQQ`, `IWM`.
- Network/API availability.
- Data timestamp.
- Completed alert timeframe timestamp.

Safe Codex prompt:

```text
The scanner reports stale or missing market data. Please inspect the data layer and explain how stale data is detected. Do not call external APIs and do not change filters.
```

## AI/API Issues

Symptoms:

- OpenAI summary unavailable.
- Deterministic fallback used.
- JSON parsing error.

What to check:

- `openai_summary.enabled`.
- Whether the class is intentionally using the local/deterministic fallback.
- Whether the owner later chose to enable API-backed summaries privately.
- Fallback path.
- Structured output expectations.

Safety note:

- Summary text is optional explanation text. It does not create trades or override risk gates. Students do not need an OpenAI Platform account, OpenAI API key, or OpenAI API call for Session 1.

## Alert Delivery Issues

Symptoms:

- Telegram test fails.
- Alert delivery retry recorded.
- Chat ID missing.

What to check:

- Placeholder vs real private token.
- Chat ID format.
- Network availability.
- Failed alert attempts table.

Safe Codex prompt:

```text
Telegram delivery is failing in the alert-only bot. Here is the sanitized error with tokens removed. Please inspect the Telegram alert module and explain the retry path. Do not send real alerts.
```

## Options Data Issues

Current course framing:

- The bot is an options alert workflow around SPY/QQQ/IWM underlying setups.
- It is not a live options-chain selector.
- It does not recommend specific contracts, strikes, or broker actions.

If students ask for options examples:

- Keep examples educational.
- Use placeholders.
- Require manual review.
- Include liquidity, spread, affordability, and max-loss checks.

## Test Failures

Symptoms:

- pytest fails.
- Fixture mismatch.
- Dashboard optional table missing.
- Replay timing assertion fails.

What to check:

- Exact failing test.
- Expected vs actual result.
- Whether the test uses temp DBs.
- Whether optional tables degrade to empty state.
- Whether replay uses completed candles only.

Safe Codex prompt:

```text
This pytest failure happened in TEST_NAME. Here is the traceback. Please inspect the related code and explain whether the failure is setup, fixture, or behavior. Propose the smallest safe fix, and do not loosen risk logic unless the test proves it is incorrect.
```

## Common Beginner Mistakes

- Running commands outside the repo.
- Forgetting to activate `.venv`.
- Pasting real secrets into prompts.
- Assuming `80` confidence means 80 percent win probability.
- Assuming replay results predict the future.
- Treating AI summaries as rule overrides.
- Changing settings before understanding current defaults.
- Expecting alerts every scan.

## What To Copy Into A Debugging Prompt

Safe to copy:

- Command run.
- Sanitized traceback.
- File path.
- Expected result.
- Actual result.
- Placeholder names.
- Test name.
- Config keys without secrets.

Do not copy:

- Real `.env` values.
- API keys.
- Tokens.
- Passwords.
- Private keys.
- Account IDs.
- Webhook URLs.

## Debugging Mindset

Ask:

- Is this a setup problem?
- Is this a missing optional service?
- Is this stale data?
- Is this a real software bug?
- Is the bot correctly saying no-trade?
- Would a proposed fix make the bot less safe?
