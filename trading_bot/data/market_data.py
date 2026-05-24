from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List

from trading_bot.models import Candle, utc_now
from trading_bot.settings import PROJECT_ROOT

logger = logging.getLogger(__name__)


TIMEFRAME_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "60m": 60, "1h": 60}


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
            raise DataUnavailable(f"Could not fetch {symbol} {interval}: {exc}") from exc

        if frame is None or getattr(frame, "empty", True):
            raise DataUnavailable(f"No data returned for {symbol} {interval}.")
        return self._normalize_frame(symbol, interval, frame)

    def fetch_symbol_context(self, symbol: str, days: int = 5) -> Dict[str, List[Candle]]:
        period = f"{max(days, 1)}d"
        one_minute = self.fetch_recent(symbol, interval="1m", period=period, prepost=True)
        context = {
            "1m": one_minute,
            "5m": resample_candles(one_minute, "5m", 5),
            "15m": resample_candles(one_minute, "15m", 15),
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
