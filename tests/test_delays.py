from datetime import date

import pytest

from bayline.rules.delays import classify_delay, promised_date
from bayline.timeutil import parse_utc
from tests.helpers import AT, history, shipment


@pytest.mark.parametrize("pickup,promised", [
    ("2026-10-05T07:00:00Z", date(2026, 10, 7)),
    ("2026-10-11T06:00:00Z", date(2026, 10, 12)),
    ("2026-10-15T14:30:00Z", date(2026, 10, 19)),
    ("2026-10-15T13:00:00Z", date(2026, 10, 19)),
    ("2026-10-15T12:59:00Z", date(2026, 10, 18)),
    ("2026-10-16T07:00:00Z", date(2026, 10, 19)),
])
def test_express_cutoff_and_holiday(pickup, promised):
    assert promised_date(shipment(service="express"), parse_utc(pickup)) == promised


@pytest.mark.parametrize("pickup,delivery,expected,late", [
    ("2026-10-05T07:00:00Z", "2026-10-07T12:00:00Z", "on_time", 0),
    ("2026-10-11T06:00:00Z", "2026-10-13T09:00:00Z", "late", 1),
    ("2026-10-15T14:30:00Z", "2026-10-19T10:00:00Z", "on_time", 0),
    ("2026-10-11T06:00:00Z", "2026-10-15T09:00:00Z", "very_late", 3),
])
def test_delivered_anchors(pickup, delivery, expected, late):
    result = classify_delay(shipment(service="express"), history(("PICKED_UP", pickup),
                            ("DELIVERED", delivery)), AT)
    assert (result.delay_class, result.late_business_days) == (expected, late)


def test_customs_and_lost_anchors():
    result = classify_delay(shipment(destination_city="Riyadh"), history(
        ("PICKED_UP", "2026-10-20T08:00:00Z"), ("CUSTOMS_HOLD", "2026-10-27T08:00:00Z")), AT)
    assert (result.promised, result.delay_class, result.late_business_days) == (
        date(2026, 10, 28), "very_late", 3)
    events = history(("PICKED_UP", "2026-10-12T06:00:00Z"),
                     ("DEPARTED_HUB", "2026-10-14T05:00:00Z"))
    assert classify_delay(shipment(), events, AT).delay_class == "lost_suspected"


@pytest.mark.parametrize("code,expected", [("ARRIVED_HUB", "at_risk"),
    ("OUT_FOR_DELIVERY", "on_time"), ("DELIVERY_FAILED", "at_risk"),
    ("CUSTOMS_HOLD", "at_risk"), ("RETURN_TO_SENDER", "returned"), ("RETURNED", "returned")])
def test_snapshot_classes(code, expected):
    events = history(("PICKED_UP", "2026-10-28T07:00:00Z"), (code, "2026-11-02T06:00:00Z"))
    assert classify_delay(shipment(), events, AT).delay_class == expected


def test_not_started_and_future_events():
    events = history(("PICKED_UP", "2026-11-03T07:00:00Z"))
    assert classify_delay(shipment(), events, AT).delay_class == "not_started"
    assert classify_delay(shipment(), [], AT).promised is None


def test_lost_seven_days_and_customs_exception():
    events = history(("PICKED_UP", "2026-10-20T07:00:00Z"),
                     ("ARRIVED_HUB", "2026-10-26T07:00:00Z"))
    assert classify_delay(shipment(), events, AT).delay_class == "lost_suspected"
    assert classify_delay(shipment(), events, parse_utc("2026-11-02T06:59:59Z")).delay_class == "very_late"
    customs = history(("PICKED_UP", "2026-10-20T07:00:00Z"),
                      ("CUSTOMS_HOLD", "2026-10-22T07:00:00Z"))
    assert classify_delay(shipment(), customs, AT).delay_class == "very_late"
