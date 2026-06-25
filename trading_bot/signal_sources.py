from __future__ import annotations

from trading_bot.models import SetupSignal


CORE_SIGNAL_SOURCE = "core_model"
CORE_SOURCE_LABEL = "Core Model"
CARTER_SIGNAL_SOURCE = "carter_squeeze"
CARTER_SOURCE_LABEL = "Carter Squeeze"
FAILED_AUCTION_TRAP_SIGNAL_SOURCE = "failed_auction_trap"
FAILED_AUCTION_TRAP_SOURCE_LABEL = "Failed Auction Trap"
FAST_MOMENTUM_SIGNAL_SOURCE = "fast_momentum_expansion"
FAST_MOMENTUM_SOURCE_LABEL = "Fast Momentum Expansion"
LIVE_CORE_100_PAPER_SOURCE = "live_100_alerts"
LIVE_CARTER_PAPER_SOURCE = "live_carter_squeeze"
LIVE_FAILED_AUCTION_TRAP_PAPER_SOURCE = "live_failed_auction_trap"
LIVE_FAST_MOMENTUM_PAPER_SOURCE = "live_fast_momentum_experiment"

FEATURE_ALERT_SOURCE = "alert_source"
FEATURE_SOURCE_LABEL = "source_label"


def tag_alert_source(setup: SetupSignal, source_key: str, source_label: str) -> SetupSignal:
    setup.features = dict(setup.features or {})
    setup.features[FEATURE_ALERT_SOURCE] = source_key
    setup.features[FEATURE_SOURCE_LABEL] = source_label
    return setup


def alert_source_from_setup(setup: SetupSignal) -> str:
    return str((setup.features or {}).get(FEATURE_ALERT_SOURCE) or CORE_SIGNAL_SOURCE)


def source_label_from_setup(setup: SetupSignal) -> str:
    return str((setup.features or {}).get(FEATURE_SOURCE_LABEL) or CORE_SOURCE_LABEL)
