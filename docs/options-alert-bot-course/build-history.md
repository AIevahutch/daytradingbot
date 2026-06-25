# Build History

## Current Bot Summary

Verified from the repository: the current bot is a local Python alert-only assistant for day-trading alerts on `SPY`, `QQQ`, and `IWM`.

It uses free best-effort market data, rule-based setup detection, confidence scoring, research gating, Telegram alerts, replay, journaling, analytics, and a Streamlit dashboard. It does not place trades or connect to a broker for execution.

## Verified Facts From The Repo

- `README.md` states the bot is local, zero-cost, alert-only, and focused on `SPY`, `QQQ`, and `IWM`.
- `config/settings.yaml` limits symbols to `SPY`, `QQQ`, and `IWM`.
- `config/settings.yaml` currently uses alert threshold `80`.
- `config/settings.yaml` currently uses alert timeframes `15m`, `30m`, and `1h`.
- `config/settings.yaml` currently uses scanner cadence `900` seconds.
- `trading_bot/cli.py` exposes bot commands for scanning, backfill, healthcheck, replay, research, Telegram tests, retry, and paper summaries.
- `trading_bot/scanner.py` orchestrates market data, no-trade/research gates, scoring, suppression, and alert delivery.
- `trading_bot/replay.py` supports offline paper replay.
- `dashboard/app.py` provides the Streamlit control and review surface.
- `docs/ACCEPTANCE_PROMPT.md` contains an exact validation prompt.
- `docs/A_PLUS_PRECISION_PROMPT.md` contains an exact A+ precision prompt.
- `docs/TESTING_VALIDATION_FRAMEWORK.md` separates software validation from real-money readiness.

## Verified Commit History

Verified from prior read-only git inspection:

- `e807c7a` on 2026-05-19: built the MVP.
- `5d9140f` on 2026-05-22: added the testing and validation framework.
- `c9234ca` on 2026-05-24: added A+ precision validation filters.
- `8011182`: merged the A+ precision work.

Current working-tree note: the repo had many modified and untracked files before this course package was created. That means git history alone does not fully explain the current local bot.

## Inferred Build History

Inferred from code structure, README, docs, tests, and history:

1. A master prompt likely defined the original local zero-cost alert-only MVP.
2. The first MVP likely created the Python package, config, yfinance data layer, SQLite storage, setup detection, scoring, Telegram alerts, Streamlit dashboard, tests, and README.
3. QA and replay hardening followed: healthcheck, replay/paper-event storage, Telegram retry persistence, tactical +1R management guidance, stricter filters, and local launch support.
4. The validation docs were added to force PASS / FAIL / BLOCKED reporting instead of vague completion claims.
5. A+ precision tuning then tightened alert selectivity and added anti-overfitting rules.
6. Later local work appears to have added or expanded research gating, OpenAI summaries, Gmail email delivery, scanner process controls, dashboard health actions, and more tests.

## Key Design Decisions

Verified or inferred:

- Keep the bot alert-only.
- Restrict the symbol universe to `SPY`, `QQQ`, and `IWM`.
- Prefer fewer higher-quality alerts over noisy alert volume.
- Treat no-trade as a valid result.
- Use raw `1m` data only as input, then evaluate alert logic on completed `15m`, `30m`, and `1h` candles.
- Use an `80` confidence threshold for alert eligibility.
- Apply hard blockers for stale data, weak conditions, bad risk/reward, chop, and other low-quality contexts.
- Keep research as a risk gate, not an independent trade creator.
- Keep recommendations pending manual review.
- Use replay and paper-trading evidence before even discussing small live testing.

## Important Turning Points

- Initial MVP: local alert-only architecture was established.
- Validation framework: the project gained explicit done gates.
- A+ precision docs: the project gained anti-overfitting standards.
- Cadence tightening: alert generation moved to completed `15m`, `30m`, and `1h` candles.
- Replay hardening: replay began separating strict win rate, move-start quality, MFE/MAE, and tactical +1R outcomes.
- Research gating: missing or high-risk research became visible risk rather than silence.

## Original Prompts Found

Exact prompt found in repo:

- `docs/ACCEPTANCE_PROMPT.md`
- `docs/A_PLUS_PRECISION_PROMPT.md`
- `trading_bot/summaries.py` OpenAI research email system prompt

Exact recommendation text found in repo:

- `trading_bot/analytics/recommendations.py`: "Add a post-trade review prompt whenever exit is worse than invalidation."

## Reconstructed Prompts Needed

Reconstructed for teaching:

- Original greenfield MVP build prompt.
- Repo setup prompt.
- Market data layer prompt.
- Strategy/scoring prompt.
- Replay validation prompt.
- Student rebuild checkpoint prompts.
- Troubleshooting prompts.

All reconstructed prompts are labeled in `prompt-library.md`.

## Known Unknowns

- The original master prompt for the first MVP was not found verbatim.
- The reason for any threshold change from older `85` references to current `80` is unclear.
- The current uncommitted working tree may contain newer functionality not represented by commit history.
- Current app/test health was not verified during this documentation-only implementation because the validation plan avoided commands that can write runtime state or call external services.

## Documentation Boundary

This file documents history only. It does not change the bot, trading logic, signal logic, risk-management logic, alert formatting, config, tests, dependencies, or runtime behavior.
