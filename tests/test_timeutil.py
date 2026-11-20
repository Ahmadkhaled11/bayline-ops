from datetime import date, datetime

import pytest

from bayline.timeutil import format_day, local_date, parse_utc, to_utc_text


@pytest.mark.parametrize("value", ["bad", "2026-10-01", "2026-10-01T12:00:00", None])
def test_reject_bad_times(value):
    with pytest.raises(ValueError):
        parse_utc(value)


def test_dst_and_local_date():
    assert local_date(parse_utc("2026-10-29T21:30:00Z"), "Africa/Cairo") == date(2026, 10, 29)
    assert local_date(parse_utc("2026-10-31T20:30:00Z"), "Asia/Dubai") == date(2026, 11, 1)
    assert to_utc_text(parse_utc("2026-10-31T23:30:00+03:00")) == "2026-10-31T20:30:00Z"
    assert format_day(date(2026, 10, 24)) == "Saturday 24 October 2026"
    with pytest.raises(ValueError):
        to_utc_text(datetime(2026, 10, 1))
    with pytest.raises(ValueError):
        local_date(datetime(2026, 10, 1), "Africa/Cairo")
