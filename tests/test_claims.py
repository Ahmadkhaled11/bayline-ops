from dataclasses import replace

import pytest

from bayline.models import Claim
from bayline.rules.claims import check_claim
from bayline.timeutil import parse_utc
from tests.helpers import AT, history, shipment


@pytest.mark.parametrize("insured,claimed,payable", [(False, 850000, 300000), (True, 850000, 850000),
    (True, 950000, 850000), (False, 10000, 10000)])
def test_damage_cap_and_day14(insured, claimed, payable):
    s = shipment(declared_value_piastres=850000, insured=insured)
    events = history(("DELIVERED", "2026-10-12T13:00:00Z"))
    result = check_claim(s, events, "damage", claimed, [], parse_utc("2026-10-26T07:00:00Z"))
    assert (result.reason, result.payable_piastres) == ("ELIGIBLE", payable)
    assert check_claim(s, events, "damage", claimed, [], AT).reason == "WINDOW_CLOSED"


def test_loss_anchor_and_returned_fee():
    s = shipment(declared_value_piastres=120000)
    events = history(("PICKED_UP", "2026-10-12T06:00:00Z"),
                     ("DEPARTED_HUB", "2026-10-14T05:00:00Z"))
    result = check_claim(s, events, "loss", 120000, [], AT)
    assert (result.reason, result.payable_piastres) == ("ELIGIBLE", 124500)


def test_delay_anchors():
    s = shipment(service="express")
    on_time = history(("PICKED_UP", "2026-10-05T07:00:00Z"), ("DELIVERED", "2026-10-07T12:00:00Z"))
    assert check_claim(s, on_time, "delay", 0, [], parse_utc("2026-10-08T08:00:00Z")).reason == "NOT_LATE_ENOUGH"
    late = history(("PICKED_UP", "2026-10-11T06:00:00Z"), ("DELIVERED", "2026-10-13T09:00:00Z"))
    assert check_claim(s, late, "delay", -1, [], parse_utc("2026-10-14T08:00:00Z")).payable_piastres == s.shipping_fee_piastres
    assert check_claim(s, late, "delay", 0, [], AT).reason == "WINDOW_CLOSED"


@pytest.mark.parametrize("kind,events,service,amount,reason", [
    ("damage", [], "standard", 0, "INVALID_AMOUNT"), ("loss", [], "standard", -1, "INVALID_AMOUNT"),
    ("damage", [], "standard", 1, "NOT_DELIVERED"), ("loss", [], "standard", 1, "NOT_LATE_ENOUGH"),
    ("delay", [], "standard", 0, "SERVICE_NOT_COVERED"), ("delay", [], "express", 0, "NOT_DELIVERED"),
    ("loss", [("DELIVERED", "2026-10-20T08:00:00Z")], "standard", 1, "DELIVERED"),
])
def test_reasons(kind, events, service, amount, reason):
    assert check_claim(shipment(service=service), history(*events), kind, amount, [], AT).reason == reason


def test_duplicate_order_and_recovery():
    s = shipment()
    c = Claim("CLM-00001", s.tracking_number, "damage", AT, 100, "open", "ELIGIBLE", 100, None, None, "")
    assert check_claim(s, [], "damage", 0, [c], AT).reason == "INVALID_AMOUNT"
    assert check_claim(s, [], "damage", 1, [c], AT).reason == "ALREADY_EXISTS"
    assert check_claim(s, [], "damage", 1, [replace(c, status="refused")], AT).reason == "NOT_DELIVERED"
    with pytest.raises(ValueError):
        check_claim(s, [], "unknown", 1, [], AT)


@pytest.mark.parametrize("kind", ["damage", "delay"])
@pytest.mark.parametrize("days,reason", [(0, "ELIGIBLE"), (14, "ELIGIBLE"), (15, "WINDOW_CLOSED")])
def test_claim_day_boundaries(kind, days, reason):
    from datetime import timedelta

    s = shipment(service="express")
    delivered = parse_utc("2026-10-13T09:00:00Z")
    events = history(("PICKED_UP", "2026-10-11T06:00:00Z"), ("DELIVERED", "2026-10-13T09:00:00Z"))
    assert check_claim(s, events, kind, 10000, [], delivered + timedelta(days=days)).reason == reason


@pytest.mark.parametrize("status", ["open", "approved", "paid"])
def test_all_duplicate_states(status):
    s = shipment()
    claim = Claim("CLM-00001", s.tracking_number, "loss", AT, 100, status, "ELIGIBLE", 100, None, None, "")
    assert check_claim(s, [], "loss", 100, [claim], AT).reason == "ALREADY_EXISTS"
    assert check_claim(s, [], "damage", 100, [claim], AT).reason == "NOT_DELIVERED"


@pytest.mark.parametrize("insured,payable", [(False, 304500), (True, 863000)])
def test_loss_cap_plus_fee(insured, payable):
    s = shipment(declared_value_piastres=850000, insured=insured)
    events = history(("PICKED_UP", "2026-10-12T06:00:00Z"), ("DEPARTED_HUB", "2026-10-14T05:00:00Z"))
    assert check_claim(s, events, "loss", 900000, [], AT).payable_piastres == payable


def test_ten_late_days_without_stale_scan():
    s = shipment()
    # Promised 15 October, then ten business days through 29 October.
    events = history(("PICKED_UP", "2026-10-12T06:00:00Z"), ("ARRIVED_HUB", "2026-10-28T05:00:00Z"))
    assert check_claim(s, events, "loss", 100, [], parse_utc("2026-10-28T07:00:00Z")).reason == "NOT_LATE_ENOUGH"
    # The fresh event removes the seven-day route, leaving the ten-day threshold.
    assert check_claim(s, events, "loss", 100, [], parse_utc("2026-10-29T07:00:00Z")).reason == "ELIGIBLE"
