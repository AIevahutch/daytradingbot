from urllib.parse import unquote, urlparse

from trading_bot.tradingview import (
    tradingview_symbol,
    tradingview_url,
    tradingview_widget_html,
    tradingview_widget_url,
)


def test_tradingview_symbol_uses_symbol_specific_exchanges():
    assert tradingview_symbol("SPY") == "AMEX:SPY"
    assert tradingview_symbol("qqq") == "NASDAQ:QQQ"


def test_tradingview_url_encodes_symbol():
    assert tradingview_url("IWM").endswith("?symbol=AMEX%3AIWM")
    assert tradingview_url("QQQ").endswith("?symbol=NASDAQ%3AQQQ")


def test_tradingview_widget_url_points_to_direct_iframe_widget():
    widget_url = tradingview_widget_url("QQQ")
    parsed = urlparse(widget_url)

    assert parsed.scheme == "https"
    assert parsed.netloc == "www.tradingview-widget.com"
    assert parsed.path == "/embed-widget/advanced-chart/"
    assert parsed.query == "locale=en"
    decoded_config = unquote(parsed.fragment)
    assert '"symbol":"NASDAQ:QQQ"' in decoded_config
    assert '"interval":"5"' in decoded_config
    assert '"timezone":"America/Los_Angeles"' in decoded_config


def test_tradingview_widget_html_contains_direct_iframe_and_fallback_link():
    html = tradingview_widget_html("SPY")

    assert "https://www.tradingview-widget.com/embed-widget/advanced-chart/" in html
    assert "%22symbol%22%3A%22AMEX%3ASPY%22" in html
    assert "Open full SPY chart" in html
    assert "https://www.tradingview.com/chart/?symbol=AMEX%3ASPY" in html
    assert "<iframe" in html
    assert "embed-widget-advanced-chart.js" not in html
