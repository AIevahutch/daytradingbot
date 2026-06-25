from __future__ import annotations

import json
import logging
import math
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List

from trading_bot.models import Candle, utc_now
from trading_bot.settings import PROJECT_ROOT

logger = logging.getLogger(__name__)


TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "10m": 10,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "1h": 60,
}


class DataUnavailable(RuntimeError):
    pass


def _bucket_start(ts: datetime, minutes: int) -> datetime:
    minute = (ts.minute // minutes) * minutes
    return ts.replace(minute=minute, second=0, microsecond=0)


def resample_candles(
    candles: Iterable[Candle], timeframe: str, minutes: int
) -> List[Candle]:
    candles = sorted(candles, key=lambda candle: candle.timestamp)
    buckets: Dict[datetime, List[Candle]] = {}
    for candle in candles:
        buckets.setdefault(_bucket_start(candle.timestamp, minutes), []).append(candle)

    resampled: List[Candle] = []
    for ts, group in sorted(buckets.items()):
        first = group[0]
        last = group[-1]
        resampled.append(
            Candle(
                symbol=first.symbol,
                timeframe=timeframe,
                timestamp=ts,
                open=first.open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=last.close,
                volume=sum(c.volume for c in group),
                source=first.source,
            )
        )
    return resampled


def completed_candles_for_timeframe(
    candles_by_tf: Dict[str, List[Candle]], timeframe: str
) -> List[Candle]:
    candles = list(candles_by_tf.get(timeframe) or [])
    minutes = TIMEFRAME_MINUTES.get(timeframe)
    if timeframe == "1m" or not minutes:
        return candles
    one_minute = candles_by_tf.get("1m") or []
    if not one_minute:
        return candles
    latest_raw = max(candle.timestamp for candle in one_minute)
    completion_delta = timedelta(minutes=max(minutes - 1, 0))
    return [
        candle for candle in candles if candle.timestamp + completion_delta <= latest_raw
    ]


def latest_age_minutes(candles: List[Candle], now: datetime = None) -> float:
    if not candles:
        return float("inf")
    now = now or utc_now()
    latest = max(candle.timestamp for candle in candles)
    return (now - latest).total_seconds() / 60


def is_stale(candles: List[Candle], stale_minutes: int, now: datetime = None) -> bool:
    return latest_age_minutes(candles, now=now) > stale_minutes


class MarketDataEngine:
    """Best-effort free data adapter.

    yfinance is imported only when needed so tests and core analytics can run
    without optional runtime dependencies installed.
    """

    def fetch_recent(
        self,
        symbol: str,
        interval: str = "1m",
        period: str = "2d",
        prepost: bool = True,
    ) -> List[Candle]:
        try:
            import yfinance as yf  # type: ignore
        except ImportError as exc:
            raise DataUnavailable(
                "yfinance is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        cache_dir = PROJECT_ROOT / "data" / "yfinance_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(yf, "set_tz_cache_location"):
            yf.set_tz_cache_location(str(cache_dir))

        try:
            frame = yf.download(
                symbol,
                interval=interval,
                period=period,
                prepost=prepost,
                progress=False,
                auto_adjust=False,
                threads=False,
            )
        except Exception as exc:
            logger.warning("yfinance failed for %s %s; trying Yahoo curl fallback: %s", symbol, interval, exc)
            return self._fetch_recent_with_yahoo_chart_curl(symbol, interval, period, prepost)

        if frame is None or getattr(frame, "empty", True):
            logger.warning("yfinance returned no data for %s %s; trying Yahoo curl fallback", symbol, interval)
            return self._fetch_recent_with_yahoo_chart_curl(symbol, interval, period, prepost)
        candles = self._normalize_frame(symbol, interval, frame)
        if interval in {"1m", "2m", "5m", "15m", "30m", "60m", "1h"} and latest_age_minutes(candles) > 3:
            logger.warning(
                "yfinance returned stale %s %s data; trying Yahoo curl fallback",
                symbol,
                interval,
            )
            try:
                fallback = self._fetch_recent_with_yahoo_chart_curl(symbol, interval, period, prepost)
            except DataUnavailable:
                return candles
            if latest_age_minutes(fallback) < latest_age_minutes(candles):
                return fallback
        return candles

    def _fetch_recent_with_yahoo_chart_curl(
        self,
        symbol: str,
        interval: str,
        period: str,
        prepost: bool,
    ) -> List[Candle]:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            f"?range={period}&interval={interval}&includePrePost={str(prepost).lower()}"
        )
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-fsSL",
                    "--max-time",
                    "15",
                    "-A",
                    "Mozilla/5.0",
                    url,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
        except Exception as exc:
            raise DataUnavailable(f"Could not fetch {symbol} {interval} with Yahoo fallback: {exc}") from exc

        try:
            chart_result = payload["chart"]["result"][0]
            timestamps = chart_result.get("timestamp") or []
            quote = chart_result["indicators"]["quote"][0]
        except Exception as exc:
            raise DataUnavailable(f"Yahoo fallback returned an unusable payload for {symbol} {interval}.") from exc

        candles: List[Candle] = []
        for index, raw_ts in enumerate(timestamps):
            try:
                open_price = float(quote["open"][index])
                high = float(quote["high"][index])
                low = float(quote["low"][index])
                close = float(quote["close"][index])
                volume = float((quote.get("volume") or [0])[index] or 0)
            except Exception:
                continue
            if not all(math.isfinite(value) for value in (open_price, high, low, close)):
                continue
            if not math.isfinite(volume):
                volume = 0.0
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=interval,
                    timestamp=datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
                    .replace(tzinfo=None, microsecond=0),
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    source="yahoo_chart_curl",
                )
            )
        if not candles:
            raise DataUnavailable(f"No data returned for {symbol} {interval}.")
        return candles

    def fetch_symbol_context(self, symbol: str, days: int = 5) -> Dict[str, List[Candle]]:
        period = f"{max(days, 1)}d"
        one_minute = self.fetch_recent(symbol, interval="1m", period=period, prepost=True)
        context = {
            "1m": one_minute,
            "5m": resample_candles(one_minute, "5m", 5),
            "10m": resample_candles(one_minute, "10m", 10),
            "15m": resample_candles(one_minute, "15m", 15),
            "30m": resample_candles(one_minute, "30m", 30),
            "1h": resample_candles(one_minute, "1h", 60),
        }
        try:
            context["1d"] = self.fetch_recent(
                symbol, interval="1d", period=f"{max(days + 15, 30)}d", prepost=False
            )
        except DataUnavailable:
            logger.warning("Daily data unavailable for %s; deriving daily context locally", symbol)
            context["1d"] = resample_candles(one_minute, "1d", 60 * 24)
        return context

    @staticmethod
    def _normalize_frame(symbol: str, interval: str, frame) -> List[Candle]:
        if hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1:
            try:
                frame = frame.xs(symbol, axis=1, level=1)
            except Exception:
                frame.columns = [col[0] if isinstance(col, tuple) else col for col in frame.columns]

        candles: List[Candle] = []
        for index, row in frame.iterrows():
            timestamp = index.to_pydatetime()
            if getattr(timestamp, "tzinfo", None) is not None:
                timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
            try:
                open_price = float(row["Open"])
                high = float(row["High"])
                low = float(row["Low"])
                close = float(row["Close"])
                volume = float(row.get("Volume", 0) or 0)
            except Exception:
                continue
            if not all(math.isfinite(value) for value in (open_price, high, low, close)):
                continue
            if not math.isfinite(volume):
                volume = 0.0
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=interval,
                    timestamp=timestamp.replace(microsecond=0),
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    source="yfinance",
                )
            )
        return candles


def synthetic_candles(
    symbol: str = "SPY",
    start: datetime = None,
    count: int = 60,
    start_price: float = 500.0,
    step: float = 0.05,
) -> List[Candle]:
    start = start or utc_now() - timedelta(minutes=count)
    candles = []
    price = start_price
    for index in range(count):
        ts = start + timedelta(minutes=index)
        close = price + step
        candles.append(
            Candle(
                symbol=symbol,
                timeframe="1m",
                timestamp=ts,
                open=price,
                high=max(price, close) + 0.03,
                low=min(price, close) - 0.03,
                close=close,
                volume=1000 + index,
                source="synthetic",
            )
        )
        price = close
    return candles
