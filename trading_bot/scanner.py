from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List

from trading_bot.alerts.telegram import TelegramClient, format_alert
from trading_bot.data.market_data import DataUnavailable, MarketDataEngine, is_stale
from trading_bot.levels.levels import LevelEngine
from trading_bot.models import Candle
from trading_bot.psychology.no_trade import NoTradeEngine
from trading_bot.scoring.scoring import ConfidenceScorer
from trading_bot.settings import Settings
from trading_bot.storage import SQLiteStore
from trading_bot.strategy.engine import StrategyEngine, trend_bias

logger = logging.getLogger(__name__)


class TradingScanner:
    def __init__(
        self,
        settings: Settings,
        store: SQLiteStore,
        data_engine: MarketDataEngine = None,
        telegram: TelegramClient = None,
    ):
        self.settings = settings
        self.store = store
        self.data_engine = data_engine or MarketDataEngine()
        self.telegram = telegram or TelegramClient()
        self.level_engine = LevelEngine()
        self.strategy = StrategyEngine()
        self.no_trade = NoTradeEngine(settings)
        self.scorer = ConfidenceScorer(settings)

    def backfill(self, days: int = 5) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for symbol in self.settings.symbols:
            context = self.data_engine.fetch_symbol_context(symbol, days=days)
            symbol_count = 0
            for candles in context.values():
                symbol_count += self.store.upsert_candles(candles)
            levels = self.level_engine.compute_levels(
                symbol, context.get("1m", []), context.get("1d", [])
            )
            if levels:
                self.store.replace_levels(symbol, levels[0].session_date, levels)
            counts[symbol] = symbol_count
        return counts

    def scan_once(self) -> Dict[str, List[str]]:
        started_at = datetime.utcnow().replace(microsecond=0)
        result: Dict[str, List[str]] = {"alerts": [], "watch_only": [], "no_trade": [], "errors": []}
        contexts: Dict[str, Dict[str, List[Candle]]] = {}
        market_biases: Dict[str, str] = {}

        for symbol in self.settings.symbols:
            try:
                context = self.data_engine.fetch_symbol_context(symbol, days=5)
            except DataUnavailable as exc:
                message = f"{symbol}: {exc}"
                logger.warning(message)
                result["errors"].append(message)
                self.store.upsert_daily_review(
                    datetime.utcnow().date().isoformat(),
                    "low_quality",
                    notes=message,
                    no_trade_reason="stale or missing market data",
                )
                continue
            contexts[symbol] = context
            for candles in context.values():
                self.store.upsert_candles(candles)
            market_biases[symbol] = trend_bias(context.get("5m", []))

        for symbol, context in contexts.items():
            intraday = context.get("1m", [])
            five = context.get("5m", [])
            daily = context.get("1d", [])
            stale = is_stale(intraday, self.settings.stale_data_minutes)
            levels = self.level_engine.compute_levels(symbol, intraday, daily)
            if levels:
                self.store.replace_levels(symbol, levels[0].session_date, levels)

            no_trade_state = self.no_trade.evaluate(
                symbol, five, levels, market_biases, stale_data=stale
            )
            setups = self.strategy.detect(symbol, context, levels, market_biases, stale_data=stale)
            if not setups:
                reason = no_trade_state.get("reason") or "No A+ setups detected"
                result["no_trade"].append(f"{symbol}: {reason}")
                self.store.upsert_daily_review(
                    datetime.utcnow().date().isoformat(),
                    no_trade_state.get("market_condition", "balanced"),
                    notes=f"{symbol}: {reason}",
                    no_trade_reason=reason,
                )
                continue

            for setup in setups:
                scored = self.scorer.score(setup, no_trade_state)
                setup_id = self.store.insert_setup(scored)
                if not self.scorer.is_alertable(scored):
                    result["watch_only"].append(
                        f"{symbol}: {scored.setup_type} {scored.confidence}/100"
                    )
                    continue
                if self.store.alert_count_today(symbol) >= self.settings.max_alerts_per_symbol_per_day:
                    result["no_trade"].append(f"{symbol}: daily alert cap reached")
                    continue
                if self.store.has_recent_duplicate_alert(
                    scored, int(self.settings.strategy.get("duplicate_alert_minutes", 90))
                ):
                    result["no_trade"].append(f"{symbol}: duplicate alert suppressed")
                    continue
                message = format_alert(scored)
                delivery = self.telegram.send_message(
                    message,
                    max_attempts=self.settings.telegram_max_attempts,
                    retry_delay_seconds=self.settings.telegram_retry_delay_seconds,
                )
                alert_id = self.store.insert_alert(
                    setup_id,
                    scored,
                    message,
                    delivered=delivery.delivered,
                    delivery_error=delivery.error,
                )
                self.store.insert_telegram_attempt(
                    symbol=symbol,
                    message=message,
                    delivered=delivery.delivered,
                    attempt_number=delivery.attempts,
                    error=delivery.error,
                    alert_id=alert_id,
                    setup_id=setup_id,
                )
                result["alerts"].append(
                    f"{symbol}: {scored.setup_type} {scored.confidence}/100"
                )
        status = "degraded" if result["errors"] else "ok"
        self.store.insert_scan_heartbeat(
            started_at, datetime.utcnow().replace(microsecond=0), status, result
        )
        return result

    def run_forever(self) -> None:
        logger.info("Starting scanner for %s", ", ".join(self.settings.symbols))
        while True:
            try:
                outcome = self.scan_once()
                logger.info("Scan outcome: %s", outcome)
            except KeyboardInterrupt:
                logger.info("Scanner stopped by user")
                raise
            except Exception:
                logger.exception("Scanner cycle failed")
                now = datetime.utcnow().replace(microsecond=0)
                self.store.insert_scan_heartbeat(
                    now,
                    now,
                    "failed",
                    {"alerts": [], "watch_only": [], "no_trade": [], "errors": ["scanner cycle failed"]},
                )
            time.sleep(self.settings.scan_cadence_seconds)
