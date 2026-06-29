import pytest

from trading_bot.dashboard_navigation import dashboard_view_index, normalize_dashboard_view


VIEWS = ["Health", "Research", "Market", "Alerts"]


def test_normalize_dashboard_view_accepts_known_view():
    assert normalize_dashboard_view("Alerts", VIEWS, "Market") == "Alerts"


def test_normalize_dashboard_view_handles_streamlit_query_param_lists():
    assert normalize_dashboard_view(["Research"], VIEWS, "Market") == "Research"


def test_normalize_dashboard_view_falls_back_to_default():
    assert normalize_dashboard_view("Paper", VIEWS, "Market") == "Market"
    assert normalize_dashboard_view("", VIEWS, "Market") == "Market"


def test_normalize_dashboard_view_uses_first_allowed_view_if_default_is_bad():
    assert normalize_dashboard_view("Nope", VIEWS, "Missing") == "Health"


def test_dashboard_view_index_matches_normalized_view():
    assert dashboard_view_index("Research", VIEWS, "Market") == 1
    assert dashboard_view_index("Nope", VIEWS, "Market") == 2


def test_dashboard_view_index_requires_views():
    with pytest.raises(ValueError):
        dashboard_view_index("Market", [], "Market")
