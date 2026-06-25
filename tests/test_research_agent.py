from datetime import date, datetime, timedelta

from trading_bot.data.market_data import resample_candles
from trading_bot.models import Candle, SetupSignal, utc_now
from trading_bot.research.agent import ResearchAgent
from trading_bot.research.calendar import is_trading_day
from trading_bot.research.calendar import phase_for_datetime
from trading_bot.research.gating import apply_research_gate, research_gate_context
from trading_bot.research.models import ResearchInput
from trading_bot.research.providers import (
    EconomicCalendarProvider,
    EarningsOptionsProvider,
    NewsSentimentProvider,
    VolatilityProvider,
)
from trading_bot.research.scoring import build_research_brief
from trading_bot.scoring.scoring import ConfidenceScorer
from trading_bot.settings import Settings
from trading_bot.storage import SQLiteStore
from trading_bot.summaries import ensure_fast_momentum_exception_note


class QuietProvider:
    name = "quiet"

    def collect(self, session_date, phase, settings, store):
        return [
            ResearchInput(
                source=self.name,
                status="ok",
                category="test",
                title="Quiet test tape",
                detail="No major event in test provider.",
                impact=-10,
                bias="neutral",
            )
        ]


def make_settings(tmp_path):
    settings = Settings(database_path=str(tmp_path / "research.sqlite"))
    return settings


def one_minute_series(symbol, start, count=60, base=100.0, step=0.03):
    price = base
    candles = []
    for index in range(count):
        close = price + step
        candles.append(
            Candle(
                symbol=symbol,
                timeframe="1m",
                timestamp=start + timedelta(minutes=index),
                open=price,
                high=close + 0.05,
                low=price - 0.05,
                close=close,
                volume=1000 + index,
                source="test",
            )
        )
        price = close
    return candles


def seed_market_data(store, settings):
    start = datetime(2026, 6, 8, 9, 30)
    for symbol, base in [("SPY", 100), ("QQQ", 200), ("IWM", 150)]:
        candles = one_minute_series(symbol, start, base=base)
        store.upsert_candles(candles)
        store.upsert_candles(resample_candles(candles, "15m", 15))
        store.upsert_candles(
            [
                Candle(symbol, "1d", datetime(2026, 6, 5), base, base + 1, base - 1, base, 100000, "test"),
                Candle(symbol, "1d", datetime(2026, 6, 8), base, base + 2, base - 1, base + 1, 100000, "test"),
            ]
        )


def test_research_generates_and_stores_fallback_summary(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)
    seed_market_data(store, settings)

    result = ResearchAgent(settings, store, providers=[QuietProvider()]).run_phase(
        "premarket", session_date=date(2026, 6, 8)
    )

    assert result["decision"] == "trade_allowed"
    assert "Decision: TRADE ALLOWED" in result["summary"]
    assert "Momentum Exception:" in result["summary"]
    assert "High research risk does not block alerts anymore" in result["summary"]
    assert result["openai_status"] == "missing_api_key"
    stored = store.latest_research_brief(session_date="2026-06-08", phase="premarket")
    assert stored["risk_score"] == result["risk_score"]
    assert stored["email_status"] == "not_requested"


def test_old_research_summary_gets_fast_momentum_note_for_display():
    old_summary = "Decision: DO NOT TRADE"

    updated = ensure_fast_momentum_exception_note(old_summary)

    assert "Decision: DO NOT TRADE" in updated
    assert "Momentum Exception:" in updated
    assert updated == ensure_fast_momentum_exception_note(updated)


def test_research_tables_are_dashboard_listable(tmp_path):
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)

    assert store.list_rows("research_briefs", 5) == []
    assert store.list_rows("research_evidence", 5) == []
    assert store.list_rows("research_email_attempts", 5) == []


def test_major_macro_day_warns_without_blocking_premarket_research(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)
    result = ResearchAgent(settings, store, providers=[EconomicCalendarProvider()]).run_phase(
        "premarket", session_date=date(2026, 6, 10)
    )

    assert result["decision"] == "trade_with_caution"
    assert result["trade_today"] is True
    assert any("Consumer Price Index" in warning for warning in result["hard_blocks"])


def test_email_missing_credentials_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr("trading_bot.email.gmail.load_env_file", lambda path: None)
    for name in ["GMAIL_SMTP_USERNAME", "GMAIL_ADDRESS", "GMAIL_SMTP_PASSWORD", "GMAIL_APP_PASSWORD", "RESEARCH_EMAIL_TO"]:
        monkeypatch.delenv(name, raising=False)
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)

    result = ResearchAgent(settings, store, providers=[QuietProvider()]).run_phase(
        "midday", send_email=True, session_date=date(2026, 6, 8)
    )

    assert result["email_status"] == "not_configured"
    assert "Email is not configured" in result["email_error"]
    attempts = store.list_rows("research_email_attempts", 5)
    assert attempts[0]["delivered"] == 0
    assert result["email_result"]["status"] == "not_configured"


def test_gmail_app_password_whitespace_is_normalized(tmp_path, monkeypatch):
    monkeypatch.setattr("trading_bot.email.gmail.load_env_file", lambda path: None)
    monkeypatch.setenv("GMAIL_SMTP_USERNAME", "eva@example.com")
    monkeypatch.setenv("GMAIL_SMTP_PASSWORD", "abcd efgh\u00a0ijkl mnop")
    monkeypatch.setenv("RESEARCH_EMAIL_TO", "eva@example.com")
    settings = make_settings(tmp_path)

    from trading_bot.email.gmail import GmailSMTPClient

    client = GmailSMTPClient(settings)

    assert client.configured is True
    assert client.password == "abcdefghijklmnop"


class FakeAlphaVantageResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


def test_missing_alpha_vantage_key_is_required_context(tmp_path, monkeypatch):
    monkeypatch.setattr("trading_bot.research.providers.load_env_file", lambda path: None)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)

    inputs = QuietProvider().collect(date(2026, 6, 8), "premarket", settings, store)
    inputs.extend(NewsSentimentProvider().collect(date(2026, 6, 8), "premarket", settings, store))
    brief = build_research_brief(date(2026, 6, 8), "premarket", inputs)

    assert brief.source_status["news_sentiment"] == "missing"
    assert brief.risk_score == 23
    assert any("ALPHA_VANTAGE_API_KEY" in driver for driver in brief.drivers)


def test_alpha_vantage_news_sentiment_feed_is_used(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)

    def fake_urlopen(request, timeout):
        return FakeAlphaVantageResponse(
            b"""
            {
              "feed": [
                {"title": "Stocks slide as yields rise", "overall_sentiment_score": "-0.35"},
                {"title": "Traders brace for macro data", "overall_sentiment_score": "-0.20"}
              ]
            }
            """
        )

    monkeypatch.setattr("trading_bot.research.providers.urlopen", fake_urlopen)
    items = NewsSentimentProvider().collect(date(2026, 6, 8), "premarket", settings, store)

    assert items[0].status == "ok"
    assert items[0].bias == "bearish"
    assert items[0].impact == 10
    assert "Stocks slide" in items[0].detail


def test_alpha_vantage_news_sentiment_retries_broad_query_on_invalid_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            return FakeAlphaVantageResponse(
                b'{"Information": "Invalid inputs. Please refer to the API documentation https://www.alphavantage.co/documentation#newsapi and try again."}'
            )
        return FakeAlphaVantageResponse(
            b"""
            {
              "feed": [
                {"title": "Markets steady after macro data", "overall_sentiment_score": "0.15"}
              ]
            }
            """
        )

    monkeypatch.setattr("trading_bot.research.providers.urlopen", fake_urlopen)
    items = NewsSentimentProvider().collect(date(2026, 6, 8), "premarket", settings, store)

    assert len(calls) == 2
    assert "topics=" in calls[0]
    assert "topics=" not in calls[1]
    assert items[0].status == "ok"
    assert items[0].metadata["fallback_used"] is True
    assert "Broad fallback used" in items[0].detail


def test_alpha_vantage_news_sentiment_invalid_inputs_stays_clean_if_fallback_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)

    def fake_urlopen(request, timeout):
        return FakeAlphaVantageResponse(
            b'{"Information": "Invalid inputs. Please refer to the API documentation https://www.alphavantage.co/documentation#newsapi and try again."}'
        )

    monkeypatch.setattr("trading_bot.research.providers.urlopen", fake_urlopen)
    items = NewsSentimentProvider().collect(date(2026, 6, 8), "premarket", settings, store)

    assert items[0].status == "warn"
    assert items[0].title == "News sentiment unavailable"
    assert "Alpha Vantage rejected the filtered news query" in items[0].detail
    assert "Please refer to the API documentation" not in items[0].detail


def test_alpha_vantage_news_network_error_is_user_friendly(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)

    def fake_urlopen(request, timeout):
        raise OSError("[Errno 8] nodename nor servname provided, or not known")

    monkeypatch.setattr("trading_bot.research.providers.urlopen", fake_urlopen)
    items = NewsSentimentProvider().collect(date(2026, 6, 8), "premarket", settings, store)

    assert items[0].status == "warn"
    assert items[0].title == "News sentiment unavailable"
    assert "temporarily unavailable" in items[0].detail
    assert "nodename" not in items[0].detail
    assert "urlopen" not in items[0].detail


def test_alpha_vantage_earnings_calendar_feed_is_used(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)

    def fake_urlopen(request, timeout):
        return FakeAlphaVantageResponse(
            b"""symbol,name,reportDate,fiscalDateEnding,estimate,currency
AAPL,Apple Inc,2026-06-08,2026-03-31,1.25,USD
XYZ,Example Corp,2026-06-08,2026-03-31,0.50,USD
MSFT,Microsoft Corp,2026-06-10,2026-03-31,2.00,USD
"""
        )

    monkeypatch.setattr("trading_bot.research.providers.urlopen", fake_urlopen)
    items = EarningsOptionsProvider().collect(date(2026, 6, 8), "premarket", settings, store)

    assert items[0].status == "ok"
    assert items[0].impact == 12
    assert "2 earnings today" in items[0].detail
    assert items[0].metadata["watched_symbols"] == ["AAPL", "MSFT"]


def test_missing_alpha_vantage_key_marks_earnings_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("trading_bot.research.providers.load_env_file", lambda path: None)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)

    items = EarningsOptionsProvider().collect(date(2026, 6, 8), "premarket", settings, store)

    assert items[0].status == "missing"
    assert "ALPHA_VANTAGE_API_KEY" in items[0].detail


def test_alpha_vantage_earnings_network_error_is_user_friendly(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)

    def fake_urlopen(request, timeout):
        raise OSError("[Errno 8] nodename nor servname provided, or not known")

    monkeypatch.setattr("trading_bot.research.providers.urlopen", fake_urlopen)
    items = EarningsOptionsProvider().collect(date(2026, 6, 8), "premarket", settings, store)

    assert items[0].status == "warn"
    assert items[0].title == "Earnings/options unavailable"
    assert "temporarily unavailable" in items[0].detail
    assert "nodename" not in items[0].detail


def test_vix_empty_free_feed_is_user_friendly(tmp_path, monkeypatch):
    import pandas as pd
    import yfinance as yf

    monkeypatch.setattr(yf, "download", lambda *args, **kwargs: pd.DataFrame())
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)

    items = VolatilityProvider().collect(date(2026, 6, 8), "premarket", settings, store)

    assert items[0].status == "warn"
    assert items[0].title == "VIX unavailable"
    assert items[0].detail == "VIX data is temporarily unavailable from the free feed."


def test_trading_day_helper_skips_weekends_and_market_holidays():
    assert is_trading_day(date(2026, 6, 8))
    assert not is_trading_day(date(2026, 6, 6))
    assert not is_trading_day(date(2026, 6, 19))


def test_research_phase_for_datetime_uses_phase_windows():
    phase_times = {"premarket": "08:15", "morning": "10:00", "midday": "12:00", "eod": "14:30"}

    assert phase_for_datetime(datetime(2026, 6, 16, 9, 45), phase_times) == "premarket"
    assert phase_for_datetime(datetime(2026, 6, 16, 10, 15), phase_times) == "morning"
    assert phase_for_datetime(datetime(2026, 6, 16, 12, 30), phase_times) == "midday"
    assert phase_for_datetime(datetime(2026, 6, 16, 14, 30), phase_times) == "eod"
    assert phase_for_datetime(datetime(2026, 6, 16, 16, 30), phase_times) == "eod"


def test_research_gate_blocks_missing_brief_and_penalizes_contra_bias(tmp_path):
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)
    gate = research_gate_context(settings, store, datetime(2026, 6, 8, 14, 0))
    assert gate["hard_block"]

    result = ResearchAgent(settings, store, providers=[QuietProvider()]).run_phase(
        "premarket", session_date=date(2026, 6, 8)
    )
    gate = research_gate_context(settings, store, datetime(2026, 6, 8, 14, 0))
    assert not gate["hard_block"]
    assert gate["risk_score"] == result["risk_score"]

    setup = SetupSignal(
        symbol="SPY",
        setup_type="test",
        direction="SHORT",
        timeframe="15m",
        created_at=utc_now(),
        entry_low=100,
        entry_high=100.2,
        stop_loss=100.8,
        target1=99,
        target2=98,
        invalidation=100.8,
        risk_reward=2.0,
        features={},
    )
    gate["bias"] = "bullish"
    no_trade = apply_research_gate({"is_no_trade": False, "market_condition": "balanced", "hard_blocks": []}, gate)
    scored = ConfidenceScorer(settings).score(setup, no_trade)
    penalties = scored.features["score_breakdown"]["penalties"]
    assert any(item["factor"] == "research_bias_conflict" for item in penalties)


def test_high_research_risk_warns_but_does_not_block_alerts(tmp_path):
    settings = make_settings(tmp_path)
    store = SQLiteStore(settings.database_file)
    inputs = [
        ResearchInput(
            source="macro",
            status="ok",
            category="macro_calendar",
            title="High-risk macro day",
            detail="Major event risk is elevated.",
            impact=45,
            bias="neutral",
        )
    ]
    brief = build_research_brief(date(2026, 6, 8), "midday", inputs)
    store.upsert_research_brief(brief)

    gate = research_gate_context(settings, store, datetime(2026, 6, 8, 14, 0))
    no_trade = apply_research_gate(
        {"is_no_trade": False, "market_condition": "trending", "hard_blocks": []},
        gate,
    )

    assert gate["risk_score"] >= 65
    assert gate["hard_block"] is False
    assert gate["penalty"] == 0
    assert "be careful" in gate["reason"]
    assert no_trade["is_no_trade"] is False
    assert no_trade["research"]["warnings"]
