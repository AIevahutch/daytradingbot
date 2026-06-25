from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, List


PHASES = ("premarket", "morning", "midday", "eod")
PHASE_LABELS = {
    "premarket": "Premarket",
    "morning": "Morning",
    "midday": "Midday",
    "eod": "End Of Day",
}


def phase_for_datetime(now: datetime, phase_times: Dict[str, str]) -> str:
    morning = _parse_phase_time(phase_times.get("morning", "10:00"))
    midday = _parse_phase_time(phase_times.get("midday", "12:00"))
    eod = _parse_phase_time(phase_times.get("eod", "16:10"))
    current = now.time()
    if current < morning:
        return "premarket"
    if current < midday:
        return "morning"
    if current < eod:
        return "midday"
    return "eod"


def _parse_phase_time(value: str) -> time:
    try:
        hour, minute = str(value).split(":", 1)
        return time(int(hour), int(minute))
    except Exception:
        return time(0, 0)


MAJOR_2026_EVENTS: Dict[date, List[Dict[str, str]]] = {
    date(2026, 1, 9): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 1, 13): [{"name": "Consumer Price Index", "source": "BLS", "time": "08:30"}],
    date(2026, 1, 27): [{"name": "FOMC meeting day 1", "source": "Federal Reserve", "time": ""}],
    date(2026, 1, 28): [{"name": "FOMC policy decision", "source": "Federal Reserve", "time": "14:00"}],
    date(2026, 2, 11): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 2, 13): [{"name": "Consumer Price Index", "source": "BLS", "time": "08:30"}],
    date(2026, 3, 6): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 3, 11): [{"name": "Consumer Price Index", "source": "BLS", "time": "08:30"}],
    date(2026, 3, 17): [{"name": "FOMC meeting day 1", "source": "Federal Reserve", "time": ""}],
    date(2026, 3, 18): [{"name": "FOMC policy decision and projections", "source": "Federal Reserve", "time": "14:00"}],
    date(2026, 4, 3): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 4, 10): [{"name": "Consumer Price Index", "source": "BLS", "time": "08:30"}],
    date(2026, 4, 28): [{"name": "FOMC meeting day 1", "source": "Federal Reserve", "time": ""}],
    date(2026, 4, 29): [{"name": "FOMC policy decision", "source": "Federal Reserve", "time": "14:00"}],
    date(2026, 5, 8): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 5, 12): [{"name": "Consumer Price Index", "source": "BLS", "time": "08:30"}],
    date(2026, 6, 5): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 6, 10): [{"name": "Consumer Price Index", "source": "BLS", "time": "08:30"}],
    date(2026, 6, 16): [{"name": "FOMC meeting day 1", "source": "Federal Reserve", "time": ""}],
    date(2026, 6, 17): [{"name": "FOMC policy decision and projections", "source": "Federal Reserve", "time": "14:00"}],
    date(2026, 7, 2): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 7, 14): [{"name": "Consumer Price Index", "source": "BLS", "time": "08:30"}],
    date(2026, 7, 28): [{"name": "FOMC meeting day 1", "source": "Federal Reserve", "time": ""}],
    date(2026, 7, 29): [{"name": "FOMC policy decision", "source": "Federal Reserve", "time": "14:00"}],
    date(2026, 8, 7): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 8, 12): [{"name": "Consumer Price Index", "source": "BLS", "time": "08:30"}],
    date(2026, 9, 4): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 9, 15): [{"name": "FOMC meeting day 1", "source": "Federal Reserve", "time": ""}],
    date(2026, 9, 16): [{"name": "FOMC policy decision and projections", "source": "Federal Reserve", "time": "14:00"}],
    date(2026, 10, 2): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 10, 27): [{"name": "FOMC meeting day 1", "source": "Federal Reserve", "time": ""}],
    date(2026, 10, 28): [{"name": "FOMC policy decision", "source": "Federal Reserve", "time": "14:00"}],
    date(2026, 11, 6): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 12, 4): [{"name": "Employment Situation", "source": "BLS", "time": "08:30"}],
    date(2026, 12, 8): [{"name": "FOMC meeting day 1", "source": "Federal Reserve", "time": ""}],
    date(2026, 12, 9): [{"name": "FOMC policy decision and projections", "source": "Federal Reserve", "time": "14:00"}],
}


def events_near(session_date: date, lookahead_days: int = 1) -> List[Dict[str, str]]:
    events: List[Dict[str, str]] = []
    for offset in range(0, lookahead_days + 1):
        day = session_date + timedelta(days=offset)
        for item in MAJOR_2026_EVENTS.get(day, []):
            event = dict(item)
            event["date"] = day.isoformat()
            event["days_ahead"] = str(offset)
            events.append(event)
    return events


def is_trading_day(session_date: date) -> bool:
    if session_date.weekday() >= 5:
        return False
    return session_date not in market_holidays(session_date.year)


def market_holidays(year: int) -> set:
    holidays = {
        observed(date(year, 1, 1)),
        nth_weekday(year, 1, 0, 3),
        nth_weekday(year, 2, 0, 3),
        good_friday(year),
        last_weekday(year, 5, 0),
        observed(date(year, 6, 19)),
        observed(date(year, 7, 4)),
        nth_weekday(year, 9, 0, 1),
        nth_weekday(year, 11, 3, 4),
        observed(date(year, 12, 25)),
    }
    return holidays


def observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    day = date(year, month, 1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day + timedelta(days=7 * (nth - 1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        day = date(year, month + 1, 1) - timedelta(days=1)
    while day.weekday() != weekday:
        day -= timedelta(days=1)
    return day


def good_friday(year: int) -> date:
    return easter_sunday(year) - timedelta(days=2)


def easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)
