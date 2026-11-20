"""The desk calendar also applies to international transit estimates."""

from datetime import date, timedelta

HOLIDAYS_2026 = frozenset(date.fromisoformat(day) for day in (
    "2026-01-07", "2026-01-25", "2026-03-20", "2026-04-13", "2026-04-25", "2026-05-01",
    "2026-05-26", "2026-05-27", "2026-06-30", "2026-07-23", "2026-08-25", "2026-10-06",
))


def is_business_day(day: date) -> bool:
    return day.weekday() not in (4, 5) and day not in HOLIDAYS_2026


def add_business_days(day: date, n: int) -> date:
    if not isinstance(n, int) or n < 1:
        raise ValueError("n must be a positive integer")
    while n:
        day += timedelta(days=1)
        n -= is_business_day(day)
    return day


def business_days_after(start: date, end: date) -> int:
    count = 0
    while start < end:
        start += timedelta(days=1)
        count += is_business_day(start)
    return count
