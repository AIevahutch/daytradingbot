from __future__ import annotations

import json
import os
import csv
from http.client import RemoteDisconnected
from datetime import date, datetime, timedelta
from io import StringIO
from socket import gaierror, timeout as SocketTimeout
from typing import List
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading_bot.research.calendar import events_near
from trading_bot.research.models import ResearchInput
from trading_bot.settings import PROJECT_ROOT, Settings, load_env_file
from trading_bot.storage import SQLiteStore

INDEX_WEIGHT_EARNINGS_SYMBOLS = {
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "GOOG",
    "TSLA",
    "AVGO",
    "JPM",
    "LLY",
    "BRK.B",
    "UNH",
    "V",
    "MA",
    "XOM",
    "COST",
    "HD",
    "NFLX",
    "AMD",
}


class EconomicCalendarProvider:
    name = "economic_calendar"

    def collect(self, session_date: date, phase: str, settings: Settings, store: SQLiteStore) -> List[ResearchInput]:
        items: List[ResearchInput] = []
        for event in events_near(session_date, lookahead_days=1):
            days_ahead = int(event.get("days_ahead", "0"))
            impact = 30 if days_ahead == 0 else 14
            detail = f"{event['source']} {event['name']} scheduled"
            if event.get("time"):
                detail = f"{detail} at {event['time']} ET"
            if days_ahead:
                detail = f"{detail} tomorrow"
            items.append(
                ResearchInput(
                    source=self.name,
                    status="ok",
                    category="macro_calendar",
                    title=event["name"],
                    detail=detail,
                    impact=impact,
                    bias="neutral",
                    occurred_at=event["date"],
                    metadata=event,
                )
            )
        if not items:
            items.append(
                ResearchInput(
                    source=self.name,
                    status="ok",
                    category="macro_calendar",
                    title="No major scheduled macro event found",
                    detail="No CPI, jobs, or FOMC event is in the local high-impact calendar window.",
                    impact=-4,
                    bias="neutral",
                    occurred_at=session_date.isoformat(),
                )
            )
        return items


class MarketStructureProvider:
    name = "market_structure"

    def collect(self, session_date: date, phase: str, settings: Settings, store: SQLiteStore) -> List[ResearchInput]:
        rows = []
        for symbol in settings.symbols:
            candles = store.latest_candles(symbol, "1m", limit=120)
            if len(candles) < 20:
                continue
            candles = sorted(candles, key=lambda candle: candle.timestamp)
            first = candles[0].close
            last = candles[-1].close
            move_pct = (last - first) / first * 100 if first else 0
            range_pct = (max(c.high for c in candles) - min(c.low for c in candles)) / last * 100 if last else 0
            rows.append((symbol, move_pct, range_pct))
        if not rows:
            return [
                ResearchInput(
                    source=self.name,
                    status="warn",
                    category="market_structure",
                    title="Market structure unavailable",
                    detail="No recent SPY/QQQ/IWM candles are available for research context.",
                    impact=10,
                    bias="neutral",
                )
            ]
        avg_move = sum(row[1] for row in rows) / len(rows)
        avg_range = sum(row[2] for row in rows) / len(rows)
        bias = "bullish" if avg_move > 0.25 else "bearish" if avg_move < -0.25 else "neutral"
        impact = 8 if avg_range > 1.2 else -3 if avg_range < 0.35 else 0
        detail = ", ".join(f"{symbol} {move_pct:+.2f}% range {range_pct:.2f}%" for symbol, move_pct, range_pct in rows)
        return [
            ResearchInput(
                source=self.name,
                status="ok",
                category="market_structure",
                title="SPY/QQQ/IWM current tape",
                detail=detail,
                impact=impact,
                bias=bias,
                metadata={"average_move_pct": round(avg_move, 2), "average_range_pct": round(avg_range, 2)},
            )
        ]


class VolatilityProvider:
    name = "volatility"

    def collect(self, session_date: date, phase: str, settings: Settings, store: SQLiteStore) -> List[ResearchInput]:
        try:
            import yfinance as yf  # type: ignore
        except ImportError:
            return [self._missing("yfinance is not installed.")]

        cache_dir = PROJECT_ROOT / "data" / "yfinance_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(yf, "set_tz_cache_location"):
            yf.set_tz_cache_location(str(cache_dir))
        try:
            frame = yf.download("^VIX", period="5d", interval="1d", progress=False, auto_adjust=False, threads=False)
        except Exception as exc:
            cached = _latest_cached_research_input(store, self.name)
            if cached:
                return [cached]
            return [self._missing(_clean_fetch_error(exc, "VIX data"))]
        if frame is None or getattr(frame, "empty", True):
            cached = _latest_cached_research_input(store, self.name)
            if cached:
                return [cached]
            return [self._missing("VIX data is temporarily unavailable from the free feed.")]
        try:
            close_data = frame["Close"].dropna()
            if hasattr(close_data, "to_numpy"):
                values = close_data.to_numpy().flatten().tolist()
            else:
                values = close_data.tolist()
            closes = [float(value) for value in values]
        except Exception:
            return [self._missing("VIX close data could not be parsed.")]
        if not closes:
            return [self._missing("VIX close data is empty.")]
        latest = closes[-1]
        prior = closes[-2] if len(closes) > 1 else latest
        change = latest - prior
        if latest >= 25 or change >= 3:
            impact = 18
        elif latest >= 20:
            impact = 9
        elif latest <= 13:
            impact = -4
        else:
            impact = 0
        bias = "bearish" if change > 1.5 else "bullish" if change < -1.5 else "neutral"
        return [
            ResearchInput(
                source=self.name,
                status="ok",
                category="volatility",
                title="VIX volatility check",
                detail=f"VIX latest {latest:.2f}, change {change:+.2f} from prior close.",
                impact=impact,
                bias=bias,
                metadata={"vix": round(latest, 2), "vix_change": round(change, 2)},
            )
        ]

    def _missing(self, detail: str) -> ResearchInput:
        return ResearchInput(
            source=self.name,
            status="warn",
            category="volatility",
            title="VIX unavailable",
            detail=detail,
            impact=6,
            bias="neutral",
        )


class NewsSentimentProvider:
    name = "news_sentiment"

    def collect(self, session_date: date, phase: str, settings: Settings, store: SQLiteStore) -> List[ResearchInput]:
        load_env_file(PROJECT_ROOT / ".env")
        api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
        if not api_key:
            return [
                ResearchInput(
                    source=self.name,
                    status="missing",
                    category="news",
                    title="Live news sentiment key missing",
                    detail="Set ALPHA_VANTAGE_API_KEY to include required live market news sentiment.",
                    impact=8,
                    bias="neutral",
                )
            ]
        primary_params = {
            "function": "NEWS_SENTIMENT",
            "topics": "financial_markets,economy_macro,economy_monetary,earnings",
            "sort": "LATEST",
            "limit": "25",
            "apikey": api_key,
        }
        fallback_params = {
            "function": "NEWS_SENTIMENT",
            "sort": "LATEST",
            "limit": "25",
            "apikey": api_key,
        }
        payload, error = self._fetch_payload(primary_params)
        used_fallback = False
        if payload is not None and _alpha_vantage_invalid_inputs(payload):
            fallback_payload, fallback_error = self._fetch_payload(fallback_params)
            if fallback_payload is not None:
                payload = fallback_payload
                used_fallback = True
            else:
                error = fallback_error

        if error:
            return [
                ResearchInput(
                    source=self.name,
                    status="warn",
                    category="news",
                    title="News sentiment unavailable",
                    detail=_clean_fetch_error(error, "news sentiment"),
                    impact=6,
                    bias="neutral",
                )
            ]
        payload = payload or {}
        feed = payload.get("feed") or []
        scored = []
        for article in feed[:10]:
            try:
                scored.append(float(article.get("overall_sentiment_score", 0)))
            except (TypeError, ValueError):
                continue
        if not scored:
            return [
                ResearchInput(
                    source=self.name,
                    status="warn",
                    category="news",
                    title="News sentiment unavailable",
                    detail=_alpha_vantage_detail(payload),
                    impact=6,
                    bias="neutral",
                )
            ]
        avg_score = sum(scored) / len(scored)
        bias = "bullish" if avg_score > 0.12 else "bearish" if avg_score < -0.12 else "neutral"
        impact = 10 if avg_score < -0.25 else -5 if avg_score > 0.25 else 0
        headlines = [str(article.get("title", "")).strip() for article in feed[:3] if article.get("title")]
        fallback_note = "Broad fallback used after filtered query was rejected. " if used_fallback else ""
        return [
            ResearchInput(
                source=self.name,
                status="ok",
                category="news",
                title="Market news sentiment",
                detail=fallback_note + (" | ".join(headlines) or f"Average sentiment score {avg_score:.2f}."),
                impact=impact,
                bias=bias,
                metadata={
                    "average_sentiment": round(avg_score, 3),
                    "article_count": len(feed),
                    "fallback_used": used_fallback,
                },
            )
        ]

    @staticmethod
    def _fetch_payload(params: dict) -> tuple:
        url = f"https://www.alphavantage.co/query?{urlencode(params)}"
        try:
            with urlopen(Request(url), timeout=12) as response:
                return json.loads(response.read().decode("utf-8")), None
        except Exception as exc:
            return None, str(exc)


def _alpha_vantage_detail(payload: dict) -> str:
    detail = (
        payload.get("Information")
        or payload.get("Error Message")
        or payload.get("Note")
        or "No scored news articles returned."
    )
    detail = str(detail).strip()
    if "Invalid inputs" in detail:
        return (
            "Alpha Vantage rejected the filtered news query. "
            "The bot treated news sentiment as unavailable for this research run."
        )
    return detail


def _alpha_vantage_invalid_inputs(payload: dict) -> bool:
    raw_detail = (
        payload.get("Information")
        or payload.get("Error Message")
        or payload.get("Note")
        or ""
    )
    return "Invalid inputs" in str(raw_detail)


class EarningsOptionsProvider:
    name = "earnings_options"

    def collect(self, session_date: date, phase: str, settings: Settings, store: SQLiteStore) -> List[ResearchInput]:
        load_env_file(PROJECT_ROOT / ".env")
        api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
        if not api_key:
            return [
                ResearchInput(
                    source=self.name,
                    status="missing",
                    category="earnings_options",
                    title="Earnings calendar key missing",
                    detail="Set ALPHA_VANTAGE_API_KEY to include required earnings calendar context.",
                    impact=5,
                    bias="neutral",
                )
            ]
        params = {
            "function": "EARNINGS_CALENDAR",
            "horizon": str(settings.research.get("earnings_horizon", "3month")),
            "apikey": api_key,
        }
        url = f"https://www.alphavantage.co/query?{urlencode(params)}"
        try:
            with urlopen(Request(url), timeout=12) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            return [
                ResearchInput(
                    source=self.name,
                    status="warn",
                    category="earnings_options",
                    title="Earnings/options unavailable",
                    detail=_clean_fetch_error(exc, "earnings/options data"),
                    impact=5,
                    bias="neutral",
                )
            ]
        rows = [row for row in csv.DictReader(StringIO(raw)) if row.get("symbol")]
        if not rows:
            detail = raw.strip().replace("\n", " ")[:240] or "No earnings calendar rows returned."
            return [
                ResearchInput(
                    source=self.name,
                    status="warn",
                    category="earnings_options",
                    title="Earnings calendar unavailable",
                    detail=detail,
                    impact=5,
                    bias="neutral",
                )
            ]

        today = session_date.isoformat()
        soon_dates = {(session_date + timedelta(days=offset)).isoformat() for offset in range(0, 3)}
        today_rows = [row for row in rows if row.get("reportDate") == today]
        soon_rows = [row for row in rows if row.get("reportDate") in soon_dates]
        watched_rows = [
            row
            for row in soon_rows
            if row.get("symbol", "").upper() in INDEX_WEIGHT_EARNINGS_SYMBOLS
        ]
        watched_symbols = [row.get("symbol", "").upper() for row in watched_rows[:8]]
        if watched_rows:
            impact = 12
        elif len(today_rows) >= 100:
            impact = 10
        elif len(today_rows) >= 40:
            impact = 5
        elif not today_rows:
            impact = -2
        else:
            impact = 0

        detail = f"{len(today_rows)} earnings today; {len(soon_rows)} within 3 trading-context days."
        if watched_symbols:
            detail = f"{detail} Index-weight names near today: {', '.join(watched_symbols)}."
        return [
            ResearchInput(
                source=self.name,
                status="ok",
                category="earnings_options",
                title="Alpha Vantage earnings calendar",
                detail=detail,
                impact=impact,
                bias="neutral",
                metadata={
                    "today_count": len(today_rows),
                    "near_term_count": len(soon_rows),
                    "watched_symbols": watched_symbols,
                    "total_returned": len(rows),
                },
            )
        ]


class FearGreedProxyProvider:
    name = "fear_greed_proxy"

    def collect(self, session_date: date, phase: str, settings: Settings, store: SQLiteStore) -> List[ResearchInput]:
        lookback_start = datetime.combine(session_date - timedelta(days=5), datetime.min.time())
        lookback_end = datetime.combine(session_date + timedelta(days=1), datetime.min.time())
        moves = []
        for symbol in settings.symbols:
            candles = store.candles_between(symbol, "1d", lookback_start, lookback_end)
            candles = sorted(candles, key=lambda candle: candle.timestamp)
            if len(candles) >= 2 and candles[0].close:
                moves.append((candles[-1].close - candles[0].close) / candles[0].close * 100)
        if not moves:
            return [
                ResearchInput(
                    source=self.name,
                    status="warn",
                    category="sentiment",
                    title="Fear/greed proxy unavailable",
                    detail="No recent daily candles are available to compute the internal sentiment proxy.",
                    impact=4,
                    bias="neutral",
                )
            ]
        avg_move = sum(moves) / len(moves)
        proxy = max(0, min(100, int(round(50 + avg_move * 8))))
        bias = "bullish" if proxy >= 58 else "bearish" if proxy <= 42 else "neutral"
        impact = 6 if proxy >= 75 or proxy <= 25 else -2 if 45 <= proxy <= 55 else 0
        return [
            ResearchInput(
                source=self.name,
                status="ok",
                category="sentiment",
                title="Internal fear/greed proxy",
                detail=f"Proxy reads {proxy}/100 from recent SPY/QQQ/IWM daily momentum.",
                impact=impact,
                bias=bias,
                metadata={"proxy": proxy, "average_move_pct": round(avg_move, 2)},
            )
        ]


def _clean_fetch_error(error, label: str) -> str:
    text = str(error or "").strip()
    lower = text.lower()
    if isinstance(error, (URLError, gaierror, SocketTimeout, TimeoutError, RemoteDisconnected)) or any(
        phrase in lower
        for phrase in (
            "nodename nor servname provided",
            "name or service not known",
            "temporary failure in name resolution",
            "timed out",
            "connection reset",
            "connection refused",
            "network is unreachable",
        )
    ):
        return f"{label.title()} is temporarily unavailable because the free research feed could not be reached."
    if isinstance(error, HTTPError):
        return f"{label.title()} is temporarily unavailable from the free feed right now."
    if "invalid inputs" in lower:
        return f"{label.title()} returned an unavailable response from the free feed."
    return f"{label.title()} is temporarily unavailable from the free feed right now."


def _latest_cached_research_input(store: SQLiteStore, source: str) -> ResearchInput:
    try:
        rows = store.list_rows("research_evidence", 100)
    except Exception:
        return None
    for row in rows:
        if row.get("source") != source or row.get("status") != "ok":
            continue
        try:
            metadata = json.loads(row.get("metadata_json") or "{}")
        except Exception:
            metadata = {}
        return ResearchInput(
            source=source,
            status="ok",
            category=row.get("category") or "",
            title=f"{row.get('title') or source} (cached)",
            detail=f"{row.get('detail') or 'Recent cached research value used.'} Cached because the live free feed is temporarily unavailable.",
            impact=int(row.get("impact") or 0),
            bias=row.get("bias") or "neutral",
            occurred_at=row.get("occurred_at"),
            metadata={**metadata, "cached": True},
        )
    return None
