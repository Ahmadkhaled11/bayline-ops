from dataclasses import replace

import pytest

from bayline.models import ReturnCase
from bayline.rules.returns import check_return
from bayline.timeutil import parse_utc
from tests.helpers import AT, MERCHANT, history, shipment


@pytest.mark.parametrize("delivered,at,city,reason,day", [
    ("2026-09-24T11:10:00Z", "2026-10-24T19:40:00Z", "Cairo", "ALLOWED", 30),
    ("2026-09-23T13:00:00Z", "2026-10-24T06:15:00Z", "Giza", "WINDOW_CLOSED", 31),
    ("2026-10-01T10:00:00Z", "2026-10-31T20:30:00Z", "Dubai", "WINDOW_CLOSED", 31),
    ("2026-10-12T13:00:00Z", "2026-10-26T07:00:00Z", "Port Said", "ALLOWED", 14),
    ("2026-10-20T10:00:00Z", "2026-10-20T10:00:00Z", "Cairo", "ALLOWED", 0),
    # Summer in Egypt is UTC+3: 20:30 UTC is still 31 July in Cairo, 21:30 UTC is already 1 August.
    ("2026-07-01T10:00:00Z", "2026-07-31T20:30:00Z", "Cairo", "ALLOWED", 30),
    ("2026-07-01T10:00:00Z", "2026-07-31T21:30:00Z", "Alexandria", "WINDOW_CLOSED", 31),
    # One moment in winter: still day 30 in Egypt (UTC+2), already day 31 in Riyadh and Amman (UTC+3).
    ("2026-11-01T10:00:00Z", "2026-12-01T21:30:00Z", "Tanta", "ALLOWED", 30),
    ("2026-11-01T10:00:00Z", "2026-12-01T21:30:00Z", "Riyadh", "WINDOW_CLOSED", 31),
    ("2026-11-01T10:00:00Z", "2026-12-01T21:30:00Z", "Amman", "WINDOW_CLOSED", 31),
])
def test_boundaries_and_anchors(delivered, at, city, reason, day):
    result = check_return(shipment(destination_city=city), history(("DELIVERED", delivered)),
                          MERCHANT, [], parse_utc(at))
    assert (result.reason, result.day_number) == (reason, day)


@pytest.mark.parametrize("category", ["perishable", "battery", "hazardous"])
def test_exclusions(category):
    result = check_return(shipment(goods_category=category),
        history(("DELIVERED", "2026-10-20T08:00:00Z")), MERCHANT, [], AT)
    assert result.reason == "CATEGORY_EXCLUDED"


def test_priority_and_existing_returns():
    s = shipment()
    events = history(("DELIVERED", "2026-10-20T10:00:00Z"))
    case = ReturnCase("RET-00001", s.tracking_number, parse_utc("2026-10-22T08:00:00Z"),
                      "other", "open", "ALLOWED", None, None, "")
    assert check_return(s, events, MERCHANT, [case], AT).reason == "ALREADY_OPEN"
    assert check_return(s, events, MERCHANT, [replace(case, status="refused")], AT).allowed
    assert check_return(s, events, replace(MERCHANT, returns_plan=False), [case], AT).reason == "MERCHANT_NOT_ON_PLAN"
    assert check_return(s, [], replace(MERCHANT, returns_plan=False), [case], AT).reason == "NOT_DELIVERED"
    assert check_return(s, events, MERCHANT, [case], parse_utc("2026-10-19T08:00:00Z")).reason == "NOT_DELIVERED"
    assert check_return(s, events, MERCHANT, [case], parse_utc("2026-10-21T08:00:00Z")).allowed


@pytest.mark.parametrize("status,expected", [("open", "ALREADY_OPEN"), ("approved", "ALREADY_OPEN"),
    ("received", "ALREADY_OPEN"), ("refused", "WINDOW_CLOSED")])
def test_existing_status_precedes_window(status, expected):
    s = shipment()
    case = ReturnCase("RET-00001", s.tracking_number, parse_utc("2026-09-25T08:00:00Z"),
        "other", status, "ALLOWED" if status != "refused" else "CATEGORY_EXCLUDED", None, None, "")
    result = check_return(s, history(("DELIVERED", "2026-09-24T11:10:00Z")), MERCHANT, [case], AT)
    assert result.reason == expected
