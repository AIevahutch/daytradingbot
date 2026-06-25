# Failed Auction Trap Branch Summary

This branch stack tracks the dashboard-only Failed Auction Trap experiment separately from the existing core and Carter lanes.

## Branches

### `failed-auction-context`

Summary: Documents the grilled strategy contract in `CONTEXT.md`.

Description:
- Defines Failed Auction Trap as a dashboard-only experimental lane.
- Limits valid locations to premarket high/low, prior day high/low, and opening range high/low.
- Requires close back inside the level, 5m/15m only, SPY/QQQ agreement, 6:35-9:30 AM Pacific timing, a clean +1R path, participation, and side-specific scoring.
- Keeps Telegram reserved for current core alerts and Carter Squeeze put-side alerts.

Rollback scope: Removes only the written glossary/context contract.

### `failed-auction-engine`

Summary: Adds the detector and source-separated paper/replay plumbing.

Description:
- Adds `failed_auction_trap` settings and source labels.
- Adds `trading_bot/failed_auction_trap.py`.
- Records live experimental signals as paper-only rows without sending Telegram messages.
- Adds source-aware live paper helpers and replay support.
- Adds focused tests for clean traps, wick-only rejections, SPY/QQQ disagreement, and Telegram isolation.

Rollback scope: Removes the experimental lane logic and paper/replay tracking.

### `failed-auction-dashboard`

Summary: Adds dashboard visibility for the experimental lane.

Description:
- Adds a Paper Trading section for Failed Auction Trap metrics.
- Shows paper-tracked count, wins, losses, open, not-triggered, win rate, tracking-since, and recent rows.
- Labels the lane as dashboard-only until it graduates.
- Keeps live source paper runs out of archived replay tables.

Rollback scope: Removes the dashboard panel while leaving detector/paper storage intact.

### `failed-auction-tracking-summary`

Summary: Adds this tracking document.

Description:
- Captures branch purpose, scope, and rollback notes.
- Provides a quick map for debugging or reverting the feature.

Rollback scope: Removes only this summary file.

## Safety Notes

- The bot remains alert-only.
- Failed Auction Trap does not send Telegram alerts.
- Failed Auction Trap must graduate through the existing Telegram-Eligible Lane threshold before notifications are considered.
- Call-side and put-side results must be reviewed separately.
