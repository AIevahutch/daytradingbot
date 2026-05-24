from __future__ import annotations

from typing import Iterable, List, Tuple, TypeVar

from trading_bot.models import SetupSignal


T = TypeVar("T")


SETUP_PRIORITY = {
    "Liquidity sweep reversal": 100,
    "VWAP reclaim + retest": 85,
    "VWAP rejection + retest": 85,
    "Strat 2-1-2 continuation": 75,
    "Strat 3-1-2 reversal": 75,
    "premarket high break + hold": 65,
    "premarket low breakdown + hold": 65,
    "previous day high break + hold": 60,
    "previous day low breakdown + hold": 60,
    "weekly high break + hold": 55,
    "weekly low breakdown + hold": 55,
    "Momentum continuation": 35,
}


def setup_priority(setup: SetupSignal) -> int:
    return SETUP_PRIORITY.get(setup.setup_type, 50)


def setup_rank_key(setup: SetupSignal) -> Tuple[int, int, float]:
    return (setup_priority(setup), setup.confidence, setup.risk_reward)


def ranked_setups(setups: Iterable[SetupSignal]) -> List[SetupSignal]:
    return sorted(setups, key=setup_rank_key, reverse=True)


def ranked_records(records: Iterable[Tuple[SetupSignal, T]]) -> List[Tuple[SetupSignal, T]]:
    return sorted(records, key=lambda record: setup_rank_key(record[0]), reverse=True)
