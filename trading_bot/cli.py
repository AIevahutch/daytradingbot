from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
import time

from trading_bot.alerts.telegram import TelegramClient
from trading_bot.health import run_healthcheck
from trading_bot.logging_config import configure_logging
from trading_bot.replay import HistoricalReplay
from trading_bot.research.agent import ResearchAgent, run_research_schedule
from trading_bot.research.calendar import PHASES
from trading_bot.runtime.scanner_process import watchdog_scanner_once
from trading_bot.scanner import TradingScanner
from trading_bot.settings import load_settings
from trading_bot.storage import SQLiteStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m trading_bot",
        description="Local alert-only day-trading assistant for SPY, QQQ, and IWM.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Continuously scan for high-confidence setups.")
    scan.add_argument("--once", action="store_true", help="Run a single scan cycle and exit.")

    backfill = sub.add_parser("backfill", help="Backfill recent market context.")
    backfill.add_argument("--days", type=int, default=5, help="Number of recent days to fetch.")

    sub.add_parser("telegram_test", help="Send a Telegram test message.")

    sub.add_parser("healthcheck", help="Validate local runtime health and readiness.")

    watchdog = sub.add_parser(
        "watchdog",
        help="Keep the background scanner alive and restart it if its heartbeat goes stale.",
    )
    watchdog.add_argument("--once", action="store_true", help="Run one watchdog check and exit.")
    watchdog.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="Seconds between watchdog checks when running continuously.",
    )
    watchdog.add_argument(
        "--stale-after-seconds",
        type=int,
        help="Restart scanner when the latest heartbeat is older than this.",
    )

    replay = sub.add_parser("replay", help="Run historical paper-trading replay.")
    replay.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD.")
    replay.add_argument("--to", dest="to_date", required=True, help="End date YYYY-MM-DD.")
    replay.add_argument("--csv-dir", type=Path, help="Optional folder with SPY.csv/QQQ.csv/IWM.csv.")
    replay.add_argument("--symbols", nargs="*", help="Optional subset of symbols to replay.")

    retry = sub.add_parser("retry_failed_alerts", help="Retry undelivered Telegram alerts.")
    retry.add_argument("--limit", type=int, default=50, help="Maximum failed alerts to retry.")

    summary = sub.add_parser("paper_summary", help="Show aggregate paper-trading replay results.")
    summary.add_argument("--run-id", type=int, help="Optional paper run id.")

    research = sub.add_parser("research", help="Generate market research briefs.")
    research.add_argument("--phase", choices=PHASES, default="premarket", help="Research phase to run.")
    research.add_argument("--email", action="store_true", help="Email the research summary after saving it.")
    research.add_argument("--json", action="store_true", help="Print the full research payload as JSON.")
    research.add_argument("--schedule", action="store_true", help="Run the trading-day research scheduler.")
    research.add_argument("--test-email", action="store_true", help="Send a research email delivery test.")
    return parser


def main(argv=None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    settings = load_settings()
    store = SQLiteStore(settings.database_file)
    scanner = TradingScanner(settings, store)

    if args.command == "healthcheck":
        health = run_healthcheck(settings, store)
        print(json.dumps(health, indent=2))
        return 0 if health["status"] != "fail" else 1

    if args.command == "watchdog":
        stale_after_seconds = args.stale_after_seconds or max(
            settings.scan_cadence_seconds * 3,
            300,
        )

        def run_watchdog_check():
            heartbeat = store.latest_scan_heartbeat()
            result = watchdog_scanner_once(
                heartbeat["completed_at"] if heartbeat else None,
                stale_after_seconds=stale_after_seconds,
            )
            payload = {
                "ok": result.ok,
                "action": result.action,
                "running": result.status.running,
                "pid": result.status.pid,
                "message": result.message,
                "latest_heartbeat_completed_at": result.latest_heartbeat_completed_at,
                "stale_after_seconds": result.stale_after_seconds,
            }
            return result, payload

        if args.once:
            result, payload = run_watchdog_check()
            print(json.dumps(payload, indent=2))
            return 0 if result.ok else 1

        logger = logging.getLogger(__name__)
        logger.info(
            "Starting scanner watchdog every %s seconds; stale after %s seconds",
            args.interval_seconds,
            stale_after_seconds,
        )
        while True:
            result, payload = run_watchdog_check()
            logger.info("Scanner watchdog: %s", payload)
            time.sleep(max(args.interval_seconds, 10))

    if args.command == "replay":
        replay = HistoricalReplay(settings, store)
        summary = replay.run(
            start_date=args.from_date,
            end_date=args.to_date,
            symbols=args.symbols or settings.symbols,
            csv_dir=args.csv_dir,
        )
        print(json.dumps(summary, indent=2))
        return 0

    if args.command == "retry_failed_alerts":
        telegram = TelegramClient()
        retried = []
        for row in store.list_failed_alerts(limit=args.limit):
            delivery = telegram.send_message(
                row["message"],
                max_attempts=settings.telegram_max_attempts,
                retry_delay_seconds=settings.telegram_retry_delay_seconds,
            )
            store.update_alert_delivery(row["id"], delivery.delivered, delivery.error)
            store.insert_telegram_attempt(
                symbol=row["symbol"],
                message=row["message"],
                delivered=delivery.delivered,
                attempt_number=delivery.attempts,
                error=delivery.error,
                alert_id=row["id"],
                setup_id=row.get("setup_id"),
            )
            retried.append(
                {
                    "alert_id": row["id"],
                    "symbol": row["symbol"],
                    "delivered": delivery.delivered,
                    "error": delivery.error,
                }
            )
        print(json.dumps({"retried": retried}, indent=2))
        return 0 if all(item["delivered"] for item in retried) else 1

    if args.command == "paper_summary":
        print(json.dumps(store.paper_summary(args.run_id), indent=2))
        return 0

    if args.command == "research":
        agent = ResearchAgent(settings, store)
        if args.schedule:
            run_research_schedule(settings, store)
            return 0
        if args.test_email:
            result = agent.send_test_email()
            print(json.dumps(result, indent=2))
            return 0 if result.get("delivered") else 1
        result = agent.run_phase(args.phase, send_email=args.email)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(
                f"{result.get('phase')} research {result.get('decision', result.get('status'))}: "
                f"risk {result.get('risk_score', '-')}/100 | email {result.get('email_status', 'not_requested')}"
            )
        if result.get("status") == "skipped":
            return 0
        if args.email and result.get("email_status") == "failed":
            return 1
        return 0

    if args.command == "scan":
        if args.once:
            outcome = scanner.scan_once()
            print(outcome)
            return 0 if not outcome["errors"] else 1
        scanner.run_forever()
        return 0

    if args.command == "backfill":
        try:
            counts = scanner.backfill(days=args.days)
        except Exception as exc:
            logging.getLogger(__name__).error("Backfill failed: %s", exc)
            print(f"Backfill failed: {exc}", file=sys.stderr)
            return 1
        print(f"Backfilled candles: {counts}")
        return 0

    if args.command == "telegram_test":
        telegram = TelegramClient()
        message = (
            "SPY/QQQ/IWM alert bot test message. Telegram delivery is working. "
            "This is an operational test only, not a trade alert."
        )
        result = telegram.send_message(
            message,
            max_attempts=settings.telegram_max_attempts,
            retry_delay_seconds=settings.telegram_retry_delay_seconds,
        )
        store.insert_telegram_attempt(
            symbol="SYSTEM",
            message=message,
            delivered=result.delivered,
            attempt_number=result.attempts,
            error=result.error,
        )
        if result.delivered:
            print("Telegram test delivered.")
            return 0
        print(f"Telegram test failed: {result.error}", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
