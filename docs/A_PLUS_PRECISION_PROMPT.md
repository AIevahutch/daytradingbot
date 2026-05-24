# A+ Precision Validation Prompt

Use this prompt when tuning the bot for a higher win rate. The goal is to increase real signal quality without overfitting one replay day or hiding risk.

```text
You are validating the A+ precision mode for the SPY/QQQ/IWM alert bot.

Primary objective:
- Maximize disciplined alert precision while preserving positive expectancy.
- Prefer fewer high-quality alerts over more marginal alerts.
- Never optimize solely to make one historical replay look good.

Required constraints:
- The bot remains alert-only and never places trades.
- Only SPY, QQQ, and IWM are allowed.
- Telegram alerts must still be a subset of 85-100 confidence setups.
- Strategy changes are recommendations until manually reviewed and approved.
- Free data quality limitations must be called out.

Optimization gates:
1. Run tests with `.venv/bin/python -m pytest`.
2. Run historical replay on at least 20 varied sessions before trusting the result.
3. Include trend days, chop days, gap days, volatile days, quiet days, and major-news days.
4. Report alert count, win rate, total R, expectancy, profit factor, and max losing streak.
5. Compare before/after against the previous rule set.
6. PASS only if win rate improves without destroying total R or reducing samples to a meaningless number.
7. BLOCK if the improvement depends on one date, one symbol, one setup, or fewer than 50 alerted samples.
8. Keep all changes reviewable in `config/settings.yaml` or explicit strategy/scoring code.

Preferred A+ behavior:
- 0-3 alerts per day is acceptable.
- NO TRADE is acceptable and expected.
- Midday chop, weak volume, opening noise, closing-window emotion, and repeated same-symbol alerts should be filtered aggressively.
- Liquidity sweeps and clean VWAP retests should outrank generic momentum and Strat continuation until journal data proves otherwise.

Final answer format:
- Overall result: PASS, FAIL, or BLOCKED.
- Replay date range and sample size.
- Before/after win rate and total R.
- Which filters improved precision.
- Which setups were suppressed.
- Overfitting risk.
- Whether the bot is ready for live paper trading, not real money.
```

## Win-Rate Target

An 80% replay win rate is a precision target, not a guarantee. It is only meaningful after enough independent samples across different market regimes.
