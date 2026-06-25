from __future__ import annotations

import json
from html import escape
from urllib.parse import quote, urlencode


DEFAULT_EXCHANGE = "AMEX"


def tradingview_symbol(symbol: str, exchange: str = DEFAULT_EXCHANGE) -> str:
    cleaned_symbol = str(symbol or "").strip().upper()
    cleaned_exchange = str(exchange or DEFAULT_EXCHANGE).strip().upper()
    return f"{cleaned_exchange}:{cleaned_symbol}"


def tradingview_url(symbol: str, exchange: str = DEFAULT_EXCHANGE) -> str:
    return f"https://www.tradingview.com/chart/?symbol={quote(tradingview_symbol(symbol, exchange))}"


def tradingview_widget_url(
    symbol: str,
    *,
    interval: str = "5",
    timezone: str = "America/Los_Angeles",
    theme: str = "light",
) -> str:
    tv_symbol = tradingview_symbol(symbol)
    config = {
        "symbol": tv_symbol,
        "interval": interval,
        "timezone": timezone,
        "theme": theme,
        "style": "1",
        "locale": "en",
        "allow_symbol_change": True,
        "withdateranges": True,
        "hide_side_toolbar": False,
        "save_image": True,
        "calendar": False,
        "support_host": "https://www.tradingview.com",
    }
    query = urlencode({"locale": "en"})
    config_hash = quote(json.dumps(config, separators=(",", ":")))
    return f"https://www.tradingview-widget.com/embed-widget/advanced-chart/?{query}#{config_hash}"


def tradingview_widget_html(
    symbol: str,
    *,
    height: int = 420,
    interval: str = "5",
    timezone: str = "America/Los_Angeles",
    theme: str = "light",
) -> str:
    safe_symbol = escape(str(symbol or "").strip().upper())
    fallback_url = tradingview_url(symbol)
    widget_url = tradingview_widget_url(
        symbol,
        interval=interval,
        timezone=timezone,
        theme=theme,
    )
    return f"""
<div class="tradingview-widget-container" style="height:{int(height)}px;width:100%">
  <iframe
    title="TradingView {safe_symbol} chart"
    src="{widget_url}"
    style="height:calc(100% - 32px);width:100%;border:0;display:block"
    allowtransparency="true"
    scrolling="no"
  ></iframe>
  <div class="tradingview-widget-fallback" style="font-size:12px;line-height:20px;text-align:center">
    <a href="{fallback_url}" rel="noopener noreferrer" target="_blank">Open full {safe_symbol} chart</a>
  </div>
</div>
"""
