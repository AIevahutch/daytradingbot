---
name: Validation checklist
about: Prove the day-trading alert bot MVP is actually done
title: "Validation: MVP done check"
labels: validation
assignees: ""
---

## Validation Target

- Commit:
- Validator:
- Date:

## Required Gates

### Phase 1: Technical Validation

- [ ] Repository is current and `.env` secrets are not committed
- [ ] Dependencies install in a local `.venv`
- [ ] `config/settings.yaml` tracks only SPY, QQQ, and IWM
- [ ] Alert threshold is 85
- [ ] `.venv/bin/python -m pytest` passes
- [ ] `.venv/bin/python -m trading_bot healthcheck` reports expected status
- [ ] `.venv/bin/python -m trading_bot backfill --days 5` works or documents data-provider blocker
- [ ] `.venv/bin/python -m trading_bot scan --once` processes SPY/QQQ/IWM
- [ ] Sub-85 setups do not send Telegram alerts
- [ ] 85+ setups are the only Telegram-eligible alerts
- [ ] Duplicate alert suppression works
- [ ] Telegram delivery is verified or explicitly blocked by missing credentials
- [ ] Dashboard renders without app errors
- [ ] Journal entry updates P/L analytics
- [ ] Scanner stability and logging are verified
- [ ] Crash recovery is verified or documented as not configured

### Phase 2: Historical Replay Testing

- [ ] Replay stores paper events
- [ ] Trend days are replayed
- [ ] Chop days are replayed
- [ ] Volatile days are replayed
- [ ] Low-volume days are replayed
- [ ] Gap days are replayed
- [ ] CPI/FOMC/news-event days are replayed or documented as unavailable
- [ ] Alert quality, false positives, no-trade filters, and risk/reward are reviewed
- [ ] Recommendations remain pending review and do not auto-change live rules

### Phase 3: Live Paper Trading

- [ ] Live alerts are manually reviewed on TradingView
- [ ] Alerted trades vs trades taken are logged
- [ ] Ignored, missed, late, and false-positive alerts are logged
- [ ] Emotional state and mistake tags are tracked
- [ ] Paper expectancy and consistency are reviewed

### Phase 4: Statistical Validation

- [ ] At least 50-100 paper/live-paper samples are collected before real-money testing
- [ ] Win rate, expectancy, profit factor, max drawdown, setup consistency, and confidence reliability are reviewed
- [ ] Best/worst setups and market conditions are identified
- [ ] Over-alerting patterns and weak filters are documented
- [ ] Proposed scoring changes include before/after evidence and overfitting risk

### Phase 5: Small-Size Live Testing

- [ ] User explicitly approved small-size real-money testing
- [ ] Position sizing is intentionally tiny
- [ ] Journaling and emotional tracking continue
- [ ] FOMO, revenge trading, oversized positions, ignored stops, and poor entries are tracked
- [ ] Capital preservation remains the priority

### Final Sign-Off

- [ ] Local deployment commands are verified or blockers are documented
- [ ] Final report confirms the system is alert-only and does not place trades
- [ ] Final report states the current phase and whether the system is PASS, FAIL, or BLOCKED

## Commands Run

```bash
.venv/bin/python -m pytest
.venv/bin/python -m trading_bot healthcheck
.venv/bin/python -m trading_bot backfill --days 5
.venv/bin/python -m trading_bot scan --once
.venv/bin/python -m trading_bot telegram_test
.venv/bin/python -m trading_bot paper_summary
.venv/bin/streamlit run dashboard/app.py
```

## Result

Overall status: PASS / FAIL / BLOCKED

Current phase: Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 5

Notes:
