"""Boundary cases for desk decisions and their recorded outcomes."""

import json
import shutil
from dataclasses import replace
from datetime import date

import pytest

from bayline import cli, policies, services
from bayline import repository as repo
from bayline.config import ROOT
from bayline.db import connect
from bayline.models import AddressChange
from bayline.rules.address import check_address_change
from bayline.rules.claims import check_claim
from bayline.rules.delays import classify_delay
from bayline.rules.returns import check_return
from bayline.timeutil import parse_utc
from tests.helpers import AT, MERCHANT, history, shipment


@pytest.fixture
def regression_db(seeded_db, tmp_path):
    path = tmp_path / "decisions.db"
    shutil.copyfile(seeded_db, path)
    with connect(path) as connection:
        yield connection


@pytest.mark.parametrize("kind", ["damage", "delay"])
@pytest.mark.parametrize("at,reason", [
    ("2026-10-26T19:59:59Z", "ELIGIBLE"),
    ("2026-10-26T20:00:00Z", "WINDOW_CLOSED"),
])
def test_claim_window_uses_dubai_midnight(kind, at, reason):
    parcel = shipment(destination_city="Dubai", service="express")
    events = history(("PICKED_UP", "2026-10-04T06:00:00Z"),
                     ("DELIVERED", "2026-10-12T10:00:00Z"))
    result = check_claim(parcel, events, kind, 10000, [], parse_utc(at))
    assert result.reason == reason
    assert result.eligible == (reason == "ELIGIBLE")
    if not result.eligible:
        assert result.payable_piastres == 0


@pytest.mark.parametrize("delivered", [False, True])
def test_delay_uses_dubai_date_after_midnight(delivered):
    parcel = shipment(destination_city="Dubai", service="express")
    pairs = [("PICKED_UP", "2026-10-11T06:00:00Z"),
             ("DEPARTED_HUB", "2026-10-14T18:00:00Z")]
    if delivered:
        pairs.append(("DELIVERED", "2026-10-14T20:30:00Z"))
    result = classify_delay(parcel, history(*pairs), parse_utc("2026-10-14T20:30:00Z"))
    assert result.promised == date(2026, 10, 14)
    assert (result.delay_class, result.late_business_days) == ("late", 1)


@pytest.mark.parametrize("delivered,at,city,reason", [
    # Summer in Egypt is UTC+3, so day 14 ends at 21:00 UTC.
    ("2026-07-01T10:00:00Z", "2026-07-15T20:30:00Z", "Cairo", "ELIGIBLE"),
    ("2026-07-01T10:00:00Z", "2026-07-15T21:30:00Z", "Alexandria", "WINDOW_CLOSED"),
    # One moment in winter: still day 14 in Egypt (UTC+2), already day 15 in Riyadh and Amman (UTC+3).
    ("2026-11-01T10:00:00Z", "2026-11-15T21:30:00Z", "Tanta", "ELIGIBLE"),
    ("2026-11-01T10:00:00Z", "2026-11-15T21:30:00Z", "Riyadh", "WINDOW_CLOSED"),
    ("2026-11-01T10:00:00Z", "2026-11-15T21:30:00Z", "Amman", "WINDOW_CLOSED"),
])
def test_damage_claim_window_follows_each_delivery_city(delivered, at, city, reason):
    result = check_claim(shipment(destination_city=city), history(("DELIVERED", delivered)),
                         "damage", 10000, [], parse_utc(at))
    assert (result.reason, result.eligible) == (reason, reason == "ELIGIBLE")


@pytest.mark.parametrize("delivered", [False, True])
@pytest.mark.parametrize("city,picked_up,at,late", [
    # Summer in Egypt is UTC+3, so the promised day, Wednesday 8 July, ends at 21:00 UTC.
    ("Cairo", "2026-07-05T06:00:00Z", "2026-07-08T20:30:00Z", 0),
    ("Giza", "2026-07-05T06:00:00Z", "2026-07-08T21:30:00Z", 1),
    # Winter: Egypt is UTC+2, so 21:30 UTC is still the promised day, Wednesday 11 November.
    ("Tanta", "2026-11-08T06:00:00Z", "2026-11-11T21:30:00Z", 0),
    # Riyadh and Amman are UTC+3 all year: the promised day, Monday 16 November, ends at 21:00 UTC.
    ("Riyadh", "2026-11-08T06:00:00Z", "2026-11-16T20:30:00Z", 0),
    ("Riyadh", "2026-11-08T06:00:00Z", "2026-11-16T21:30:00Z", 1),
    ("Amman", "2026-11-08T06:00:00Z", "2026-11-16T21:30:00Z", 1),
])
def test_delay_day_follows_each_delivery_city(delivered, city, picked_up, at, late):
    pairs = [("PICKED_UP", picked_up), ("ARRIVED_HUB", at[:11] + "06:00:00Z")]
    if delivered:
        pairs.append(("DELIVERED", at))
    result = classify_delay(shipment(destination_city=city), history(*pairs), parse_utc(at))
    on_the_day = "on_time" if delivered else "at_risk"
    assert (result.delay_class, result.late_business_days) == ("late" if late else on_the_day, late)


def test_return_last_day_is_delivery_local_date_plus_thirty():
    result = check_return(shipment(destination_city="Dubai"),
                          history(("DELIVERED", "2026-10-01T20:30:00Z")),
                          MERCHANT, [], parse_utc("2026-10-31T20:30:00Z"))
    assert (result.reason, result.day_number, result.last_day) == (
        "ALLOWED", 30, date(2026, 11, 1))


@pytest.mark.parametrize("code,expected", [
    ("ARRIVED_HUB", "on_time"), ("DELIVERY_FAILED", "at_risk"),
])
def test_failed_delivery_is_at_risk_even_before_promised_date(code, expected):
    events = history(("PICKED_UP", "2026-10-12T06:00:00Z"),
                     (code, "2026-10-12T10:00:00Z"))
    result = classify_delay(shipment(), events, parse_utc("2026-10-12T11:00:00Z"))
    assert result.promised == date(2026, 10, 15)
    assert (result.delay_class, result.late_business_days) == (expected, 0)


def test_delay_claim_checks_lateness_before_window():
    events = history(("PICKED_UP", "2026-10-11T06:00:00Z"),
                     ("DELIVERED", "2026-10-12T10:00:00Z"))
    result = check_claim(shipment(service="express"), events, "delay", 0, [], AT)
    assert (result.reason, result.payable_piastres) == ("NOT_LATE_ENOUGH", 0)


def test_refused_address_change_does_not_use_the_one_change_allowance():
    parcel = shipment()
    refused = AddressChange("ADR-00001", parcel.tracking_number,
                            parse_utc("2026-10-30T10:00:00Z"), "Giza", "19 Sorrel Street",
                            "refused", "DIFFERENT_CITY", "reem.adel")
    result = check_address_change(parcel, [], "Cairo", [refused], AT)
    assert result.allowed and result.reason == "ALLOWED"


def test_backdated_return_cannot_open_a_second_case(regression_db):
    connection = regression_db
    tn = "BYL260411871"
    assert services.open_return(connection, tn, "not_wanted", "karim.nassar",
                                parse_utc("2026-10-24T19:40:00Z")).allowed
    before = connection.total_changes
    with pytest.raises(ValueError) as error:
        services.open_return(connection, tn, "not_wanted", "karim.nassar",
                             parse_utc("2026-10-24T19:00:00Z"))
    assert str(error.value) == (
        "The time given is earlier than the latest record for this shipment "
        "(2026-10-24T19:40:00Z). Check again at a time after it.")
    assert connection.total_changes == before
    assert len(repo.get_returns(connection, tn)) == 1
    assert sum(case.status == "open" for case in repo.get_returns(connection, tn)) == 1


def test_backdated_address_change_cannot_apply_a_second_change(regression_db):
    connection = regression_db
    tn = "BYL260462072"
    first_line = "Building 12, Street 9, Flat 4"
    assert services.record_address_change(connection, tn, "Cairo", first_line, "karim.nassar",
                                          parse_utc("2026-10-31T12:00:00Z")).allowed
    before = connection.total_changes
    with pytest.raises(ValueError) as error:
        services.record_address_change(connection, tn, "Cairo", "19 Sorrel Street",
                                       "karim.nassar", parse_utc("2026-10-31T11:00:00Z"))
    assert str(error.value) == (
        "The time given is earlier than the latest record for this shipment "
        "(2026-10-31T12:00:00Z). Check again at a time after it.")
    assert connection.total_changes == before
    assert len(repo.get_address_changes(connection, tn)) == 1
    assert sum(change.status == "applied"
               for change in repo.get_address_changes(connection, tn)) == 1
    assert repo.get_shipment(connection, tn).address_line == first_line
    events = [event for event in repo.get_events(connection, tn) if event.code == "ADDRESS_CHANGED"]
    assert len(events) == 1 and first_line in events[0].detail


def test_allowed_return_is_recorded_open_pending_a_decision(regression_db):
    case_id, decision = services.open_return(
        regression_db, "BYL260411871", "not_wanted", "reem.adel",
        parse_utc("2026-10-24T19:40:00Z"), include_id=True)
    row = repo.records(regression_db, "return_cases", "id = ?", (case_id,))[0]
    assert decision.allowed
    assert (row.status, row.decision_code, row.decided_at, row.decided_by) == (
        "open", "ALLOWED", None, None)


def test_eligible_claim_is_recorded_open_pending_a_decision(regression_db):
    case_id, decision = services.open_claim(
        regression_db, "BYL260455803", "damage", 850000, "reem.adel",
        parse_utc("2026-10-26T07:00:00Z"), include_id=True)
    row = repo.records(regression_db, "claims", "id = ?", (case_id,))[0]
    assert decision.eligible
    assert (row.status, row.decision_code, row.decided_at, row.decided_by) == (
        "open", "ELIGIBLE", None, None)


def test_address_update_does_not_reset_the_last_tracking_scan():
    events = history(("PICKED_UP", "2026-10-12T06:00:00Z"),
                     ("DEPARTED_HUB", "2026-10-14T05:00:00Z"),
                     ("ADDRESS_CHANGED", "2026-10-30T10:00:00Z"))
    result = classify_delay(shipment(), events, AT)
    assert result.delay_class == "lost_suspected"


def test_document_reader_rejects_existing_repository_readme():
    assert (ROOT / "README.md").is_file()
    with pytest.raises(repo.NotFoundError):
        policies.get_document("../../README", ROOT / "docs")


def test_document_reader_rejects_existing_file_outside_document_folders(tmp_path):
    docs = tmp_path / "docs"
    (docs / "policies").mkdir(parents=True)
    (docs / "handbook").mkdir()
    (tmp_path / "outside.md").write_text("# Outside\nA separate document.", encoding="utf-8")
    assert (docs / "policies" / "../../outside.md").is_file()
    with pytest.raises(repo.NotFoundError):
        policies.get_document("../../outside", docs)


@pytest.mark.parametrize("machine", [False, True])
def test_checksum_command_prints_the_saved_snapshot_digest(seeded_db, capsys, machine):
    expected = (ROOT / "tests/fixtures/sample_checksum.txt").read_text(encoding="utf-8").strip()
    assert len(expected) == 64 and all(char in "0123456789abcdef" for char in expected)
    args = ["checksum", "--db", str(seeded_db)] + (["--json"] if machine else [])
    assert cli.main(args) == 0
    output = capsys.readouterr().out
    assert (json.loads(output) if machine else output.strip()) == expected


def test_return_plan_check_precedes_excluded_category():
    parcel = shipment(goods_category="battery")
    result = check_return(parcel, history(("DELIVERED", "2026-10-20T10:00:00Z")),
                          replace(MERCHANT, returns_plan=False), [], AT)
    assert result.reason == "MERCHANT_NOT_ON_PLAN"


def test_uninsured_damage_cap_is_three_thousand_egp():
    result = check_claim(shipment(declared_value_piastres=850000),
                         history(("DELIVERED", "2026-10-20T10:00:00Z")),
                         "damage", 850000, [], AT)
    assert (result.reason, result.payable_piastres) == ("ELIGIBLE", 300000)
