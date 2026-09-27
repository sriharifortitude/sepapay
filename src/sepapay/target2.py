"""The TARGET2 calendar, which is the SEPA Credit Transfer settlement calendar.

A SCT can only be executed on a TARGET2 business day. TARGET2 is closed on
weekends and on six fixed-rule holidays: New Year's Day, Good Friday,
Easter Monday, 1 May, Christmas Day and 26 December. National holidays
don't close it: a SCT executes on German Unity Day.
"""

from __future__ import annotations

import datetime as dt


def easter_sunday(year: int) -> dt.date:
    """Gregorian Easter Sunday (the anonymous Gregorian, or Meeus/Jones/Butcher, algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 -- the algorithm's own name
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def target2_closing_days(year: int) -> dict[dt.date, str]:
    easter = easter_sunday(year)
    return {
        dt.date(year, 1, 1): "New Year's Day",
        easter - dt.timedelta(days=2): "Good Friday",
        easter + dt.timedelta(days=1): "Easter Monday",
        dt.date(year, 5, 1): "Labour Day",
        dt.date(year, 12, 25): "Christmas Day",
        dt.date(year, 12, 26): "26 December",
    }


def closed_because(day: dt.date) -> str | None:
    """Why TARGET2 is closed on this day, or None if it's a business day."""
    if day.weekday() >= 5:
        return day.strftime("%A")
    return target2_closing_days(day.year).get(day)


def next_business_day(day: dt.date) -> dt.date:
    while closed_because(day) is not None:
        day += dt.timedelta(days=1)
    return day
