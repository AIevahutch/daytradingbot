# Day Trading Alert Bot

This context defines the trading-language used by the alert-only SPY, QQQ, and IWM bot. It keeps experimental signals, tradable alerts, and strategy lanes distinct.

## Language

**Carter Squeeze Put Alert**:
A bearish Carter Squeeze release that is allowed to notify as its own Carter-lane alert after meeting strict confirmation rules. Carter put-side eligibility does not imply Carter call-side eligibility.
_Avoid_: Carter short, put play

**Carter Squeeze Call Signal**:
A bullish Carter Squeeze release that is not currently trusted as a tradable alert and must remain dashboard-only, blocked, or watch-only until separately proven through its own evidence and Eva approval.
_Avoid_: Carter long alert, call alert

**Carter Lane**:
The separate strategy lane for Carter Squeeze signals, tracked independently from the core model so its performance does not blend into core metrics.
_Avoid_: Core Carter, Carter core setup

**Core Tradable Alert Timeframe**:
A timeframe allowed to create a real core-model tradable alert. For the current bot, this means 15m and 30m only.
_Avoid_: Entry timeframe, signal timeframe

**Context Timeframe**:
A timeframe used for confirmation, trend context, or watch-only warnings, but not allowed to create a real core-model tradable alert by itself.
_Avoid_: Bad timeframe, ignored timeframe

**Core Tradable Setup**:
The narrow setup family trusted enough to create a real core-model tradable alert. For the current bot, this means strict 15m/30m Liquidity Sweep Reversal only.
_Avoid_: Core signal, best setup, A+ setup

**Experimental Setup Lane**:
A separately labeled paper-tracked strategy idea that may produce watch-only or experimental dashboard signals, but does not count as core until it earns enough evidence. Experimental lanes should be shown in the Paper tab under an Experimental Lanes section with separate graduation progress, not mixed into the Telegram Alert Stream.
_Avoid_: New core setup, extra alert

**Failed Auction Trap Lane**:
A dashboard-only experimental lane for fakeout reversals after price breaks a meaningful level, fails, and reclaims or rejects that level with a clear trapped side. It is separate from core Liquidity Sweep Reversal and must not be treated as a normal breakout or breakdown continuation. Valid trap locations are limited to premarket high/low, prior day high/low, and opening range high/low. The failed break must close back inside the level before the setup counts; wick-only failures are watch context, not experimental signals. Valid experimental timeframes are 5m and 15m only. SPY and QQQ must agree directionally; IWM may be used as context but cannot rescue a disagreement between SPY and QQQ. Valid experimental timing is 6:35 AM to 9:30 AM Pacific only. The setup must have at least a 1R path before the next major opposing level; otherwise it remains watch-only. The reclaim or rejection candle must show real participation through elevated relative volume or range expansion versus recent candles. Balanced or mixed regimes are allowed only when the trap is extremely clean at a range edge with an obvious trapped side; otherwise the lane remains watch-only. It remains dashboard-only until it graduates through the Telegram-Eligible Lane threshold. Call-side and put-side results must be scored separately so one weak direction can be blocked without removing the full lane.
_Avoid_: Breakout alert, failed breakout core setup

**Fast Momentum Expansion Lane**:
A dashboard-only experimental lane for strong range and volume expansion that may appear earlier than the core model, but is not a core tradable setup until it passes the Telegram-Eligible Lane threshold. It has no emergency or heads-up Telegram exception while experimental; all Fast Momentum Expansion signals must stay in the dashboard and paper-tracking evidence stream until graduation. Initial evidence tracking should include only 80+ candidates that would otherwise have been alertable, separated by 1m, 5m, 10m, symbol, and direction.
_Avoid_: Fast momentum core setup, chase setup

**High-Potential Balanced Liquidity Sweep Lane**:
A dashboard-only candidate lane for 90-99 confidence Liquidity Sweep Reversal signals that look structurally good but do not meet the current strict core Telegram rule. It is for 15m and 30m sweeps only, requires SPY and QQQ directional agreement, may allow IWM to be neutral when SPY and QQQ agree, and must have clean structure plus a realistic +1R path. It must be tracked separately from core 100/100 Liquidity Sweep Reversal alerts and cannot send Telegram until it graduates through the Telegram-Eligible Lane threshold. Initial evidence tracking intentionally excludes 80-89 confidence balanced sweeps to keep the sample conservative.
_Avoid_: Failed core alert, weak sweep, balanced core setup

**Telegram-Eligible Lane**:
An experimental lane that has earned notification privileges by reaching at least 25 closed paper-tracked signals, 80%+ win rate, positive expectancy of +0.40R or better, profit factor 2.0+, controlled drawdown, performance across at least three trading days, and Eva approval. Graduation is lane-specific: Fast Momentum Expansion, High-Potential Balanced Liquidity Sweep, Failed Auction Trap, and any future experimental lane must each earn separate evidence and separate Eva approval.
_Avoid_: Proven setup, promoted setup

**Core Candidate Lane**:
An experimental lane that may be considered for core after roughly 50 closed paper alerts, 80%+ win rate, positive expectancy near +0.50R or better, profit factor 2.5+, stable behavior, and manual false-positive review.
_Avoid_: Core setup, production setup

**Signal Quality Benchmark**:
The paper-trading pass/fail measure for whether a setup reaches +1R before invalidation. It evaluates setup quality separately from partial-profit execution plans.
_Avoid_: Full trade plan, sell rule

**Day-Trade Contract**:
The rule set that decides whether an otherwise valid setup is tight enough for Eva's same-session index options alerts. It checks timeframe, entry-zone width, risk per share, target distance, and same-day expiration. A setup can have a good directional thesis but fail the Day-Trade Contract if the entry, stop, or target is too wide for a practical day trade.
_Avoid_: Swing-trade stop, wide alert, eventually-right setup

**Expired Day Trade**:
A paper-tracked alert that triggered but did not hit the +1R target or invalidation before the same-day cutoff. It is closed for day-trade quality metrics and should not remain open across sessions.
_Avoid_: Still open, unresolved winner

**Partial-Profit Plan**:
The manual execution idea of selling about 70% of contracts at +1R and optionally letting the remainder seek a larger target. It is not the same thing as the signal quality benchmark.
_Avoid_: Paper win rule, setup score

**Call-Side Idea**:
A bullish directional alert or watch-only signal. It does not recommend a specific options contract, strike, expiration, order, or broker action.
_Avoid_: Call contract, buy call alert

**Put-Side Idea**:
A bearish directional alert or watch-only signal. It does not recommend a specific options contract, strike, expiration, order, or broker action.
_Avoid_: Put contract, buy put alert

**Telegram Alert Stream**:
The smallest user-facing notification stream, reserved only for current-rule approved alerts: strict core 100/100 Liquidity Sweep Reversal alerts on 15m/30m, Carter Squeeze Put Alerts, and management alerts tied to an approved Telegram entry. Core setups below 100/100, non-liquidity core setups, 5m/1h liquidity sweeps, Carter call-side signals, and experimental setup lanes remain dashboard-only unless a lane separately graduates and Eva approves it.
_Avoid_: All alerts, watchlist feed

**Telegram Management Alert**:
A follow-up notification such as Suggested sell/partial that is allowed only when the original setup was a Telegram-entry alert. Dashboard-only experimental lanes may show +1R or management progress in the dashboard/Paper tab, but must not create Telegram follow-up alerts before graduation.
_Avoid_: Experimental sell alert, paper sell alert

**Approved Alert Lane**:
A setup lane that Eva may consider from Telegram and the dashboard because it is either the current Core Tradable Setup, the Carter Squeeze Put Alert lane, or an Experimental Setup Lane that has graduated through the Telegram-Eligible Lane threshold.
_Avoid_: High-score setup, any 80+ setup
