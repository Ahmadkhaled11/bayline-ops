from datetime import date

import pytest

from bayline.business_days import add_business_days, business_days_after, is_business_day


@pytest.mark.parametrize("day,expected", [("2026-10-06", False), ("2026-10-09", False),
                                         ("2026-10-10", False), ("2026-10-11", True),
                                         ("2027-01-07", True)])
def test_calendar(day, expected):
    assert is_business_day(date.fromisoformat(day)) is expected


def test_counting():
    start = date(2026, 10, 5)
    assert add_business_days(start, 1) == date(2026, 10, 7)
    assert add_business_days(date(2026, 10, 15), 1) == date(2026, 10, 18)
    assert business_days_after(start, date(2026, 10, 8)) == 2
    assert business_days_after(start, start) == 0
    assert business_days_after(start, date(2026, 10, 1)) == 0
    with pytest.raises(ValueError):
        add_business_days(start, 0)
