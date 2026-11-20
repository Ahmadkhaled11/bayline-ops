import pytest

from bayline.models import AddressChange
from bayline.rules.address import check_address_change
from bayline.timeutil import parse_utc
from tests.helpers import AT, history, shipment


@pytest.mark.parametrize("code,expected", [
    ("CREATED", "ALLOWED"), ("PICKED_UP", "ALLOWED"), ("ARRIVED_HUB", "ALLOWED"),
    ("DELIVERY_FAILED", "ALLOWED"), ("OUT_FOR_DELIVERY", "TOO_LATE"),
    ("DELIVERED", "TOO_LATE"), ("RETURN_TO_SENDER", "TOO_LATE"), ("RETURNED", "TOO_LATE"),
    ("CUSTOMS_HOLD", "CUSTOMS_HOLD"),
])
def test_statuses(code, expected):
    assert check_address_change(shipment(), history((code, "2026-11-02T06:30:00Z")),
                                " cairo ", [], AT).reason == expected


def test_existing_and_city_order():
    s = shipment()
    c = AddressChange("ADR-00001", s.tracking_number, AT, "Cairo", "Parcel Lane 2", "applied", "ALLOWED", "reem.adel")
    assert check_address_change(s, [], "Giza", [c], AT).reason == "ALREADY_CHANGED"
    assert check_address_change(s, [], "Giza", [], AT).reason == "DIFFERENT_CITY"
    assert check_address_change(s, [], "Cairo", [c], parse_utc("2026-10-31T12:00:00Z")).allowed


def test_anchor_times():
    events = history(("PICKED_UP", "2026-10-29T07:00:00Z"), ("ARRIVED_HUB", "2026-10-30T09:00:00Z"))
    assert check_address_change(shipment(), events, "Cairo", [], parse_utc("2026-10-31T12:00:00Z")).allowed
    assert check_address_change(shipment(), events, "Giza", [], parse_utc("2026-10-31T13:00:00Z")).reason == "DIFFERENT_CITY"
