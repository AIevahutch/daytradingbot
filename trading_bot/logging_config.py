from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(level: int = logging.INFO) -> None:
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/trading_bot.log", encoding="utf-8"),
        ],
    )

