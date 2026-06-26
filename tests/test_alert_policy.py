from trading_bot.alert_policy import is_current_approved_telegram_alert
from trading_bot.signal_sources import CARTER_SIGNAL_SOURCE, CORE_SIGNAL_SOURCE


def setup_row(
    setup_type,
    *,
    direction="LONG",
    confidence=100,
    timeframe="15m",
    status="alert_ready",
    source=CORE_SIGNAL_SOURCE,
):
    return {
        "setup_type": setup_type,
        "direction": direction,
        "confidence": confidence,
        "timeframe": timeframe,
        "status": status,
        "features": {"alert_source": source},
    }


def alert_row(setup_type, *, direction="LONG", confidence=100):
    return {
        "setup_type": setup_type,
        "direction": direction,
        "confidence": confidence,
    }


def test_current_telegram_policy_allows_only_core_100_liquidity_on_15m_30m():
    assert is_current_approved_telegram_alert(
        alert_row("Liquidity sweep reversal"),
        setup_row("Liquidity sweep reversal", timeframe="15m"),
        alert_threshold=80,
    )
    assert is_current_approved_telegram_alert(
        alert_row("Liquidity sweep reversal"),
        setup_row("Liquidity sweep reversal", timeframe="30m"),
        alert_threshold=80,
    )
    assert not is_current_approved_telegram_alert(
        alert_row("Liquidity sweep reversal", confidence=99),
        setup_row("Liquidity sweep reversal", confidence=99, timeframe="15m"),
        alert_threshold=80,
    )
    assert not is_current_approved_telegram_alert(
        alert_row("Liquidity sweep reversal"),
        setup_row("Liquidity sweep reversal", timeframe="5m"),
        alert_threshold=80,
    )
    assert not is_current_approved_telegram_alert(
        alert_row("Strat 2-1-2 continuation"),
        setup_row("Strat 2-1-2 continuation", timeframe="15m"),
        alert_threshold=80,
    )


def test_current_telegram_policy_allows_carter_puts_not_calls():
    assert is_current_approved_telegram_alert(
        alert_row("Carter Squeeze", direction="SHORT", confidence=98),
        setup_row(
            "Carter Squeeze",
            direction="SHORT",
            confidence=98,
            timeframe="15m",
            source=CARTER_SIGNAL_SOURCE,
        ),
        alert_threshold=80,
    )
    assert not is_current_approved_telegram_alert(
        alert_row("Carter Squeeze", direction="LONG", confidence=98),
        setup_row(
            "Carter Squeeze",
            direction="LONG",
            confidence=98,
            timeframe="15m",
            source=CARTER_SIGNAL_SOURCE,
        ),
        alert_threshold=80,
    )


def test_current_telegram_policy_allows_management_only_for_approved_core_entries():
    assert is_current_approved_telegram_alert(
        alert_row("Suggested sell/partial", confidence=100),
        setup_row("Liquidity sweep reversal", confidence=100, timeframe="15m"),
        alert_threshold=80,
    )
    assert not is_current_approved_telegram_alert(
        alert_row("Suggested sell/partial", confidence=98),
        setup_row("Liquidity sweep reversal", confidence=98, timeframe="15m"),
        alert_threshold=80,
    )
