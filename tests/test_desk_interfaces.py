"""Desk output and request errors remain useful without reading raw records."""

import json

import pytest

from bayline import cli, services
from bayline.db import connect
from bayline.sample.generate import AS_OF
from bayline.timeutil import parse_utc
from bayline.web import create_app
from tests.test_web import request


@pytest.mark.parametrize("args,lines", [
    (["shipment", "BYL260442157"], ["Shipment BYL260442157", "Cairo to Cairo", "Tracking history:"]),
    (["customer", "CUS-00101"], ["Customer CUS-00101: Tarek Sorour", "Email:", "Shipments:"]),
    (["message", "M-01001"], ["Message M-01001", "From:", "Subject:", "Replies:"]),
    (["stats"], ["Shipments by status:", "Shipments by delay:", "Messages by topic:"]),
])
def test_desk_text_is_readable_and_json_remains_available(seeded_db, capsys, args, lines):
    assert cli.main([*args, "--db", str(seeded_db)]) == 0
    text = capsys.readouterr().out
    assert not text.lstrip().startswith(("{", "["))
    for line in lines:
        assert line in text
    assert text.isascii()
    assert cli.main([*args, "--db", str(seeded_db), "--json"]) == 0
    assert isinstance(json.loads(capsys.readouterr().out), dict)


def test_refused_claim_text_gives_reason_without_a_payment(seeded_db, capsys):
    assert cli.main(["claim-check", "BYL260455803", "--kind", "damage", "--amount", "8500",
                     "--at", "2026-11-02T07:00:00Z", "--db", str(seeded_db)]) == 1
    assert capsys.readouterr().out.strip() == "WINDOW_CLOSED"


def test_message_queue_starts_with_the_oldest_new_message(seeded_db, sample, capsys):
    expected = sorted([message for message in sample.tables["messages"] if message.status == "new"],
                      key=lambda message: (message.received_at, message.id))[:7]
    assert cli.main(["messages", "--status", "new", "--limit", "7", "--db", str(seeded_db)]) == 0
    assert [line.split()[0] for line in capsys.readouterr().out.splitlines()] == [
        message.id for message in expected]
    code, result = request(create_app(seeded_db), "/messages", "status=new&limit=7")
    assert code == 200
    assert [message["id"] for message in result["messages"]] == [message.id for message in expected]


@pytest.mark.parametrize("path,query,detail", [
    ("/shipments/BYL260411872", "", "Invalid tracking number"),
    ("/health", "at=not-a-time", "ISO 8601 time with a time zone"),
    ("/shipments/BYL260411871/checks/claim", "", "Missing parameter: kind"),
    ("/shipments/BYL260411871/checks/claim", "kind=damage", "Missing parameter: amount"),
    ("/shipments/BYL260411871/checks/address", "", "Missing parameter: city"),
    ("/shipments/BYL260411871/checks/address", "city=", "city cannot be empty"),
])
def test_bad_requests_explain_the_specific_problem(seeded_db, path, query, detail):
    code, result = request(create_app(seeded_db), path, query)
    assert code == 400 and result["error"] == "bad_request"
    assert detail in result["detail"]


def test_shared_check_helpers_do_not_write(seeded_db):
    with connect(seeded_db) as connection:
        before = connection.total_changes
        returned = services.check_return(connection, "BYL260411871", parse_utc("2026-10-24T19:40:00Z"))
        claimed = services.check_claim(connection, "BYL260455803", "damage", 850000,
                                       parse_utc("2026-10-26T07:00:00Z"))
        addressed = services.check_address_change(connection, "BYL260462072", "Cairo", AS_OF)
        assert (returned.reason, returned.day_number) == ("ALLOWED", 30)
        assert (claimed.reason, claimed.payable_piastres) == ("ELIGIBLE", 300000)
        assert addressed.reason == "ALLOWED"
        assert connection.total_changes == before


@pytest.mark.parametrize("command", ["address-check", "change-address"])
@pytest.mark.parametrize("city", ["", "   "])
def test_empty_city_is_bad_input_in_both_desk_commands(seeded_db, capsys, command, city):
    args = [command, "BYL260462072", "--city", city, "--db", str(seeded_db)]
    if command == "change-address":
        args.extend(["--line", "14 Oak Street", "--by", "karim.nassar"])
    with connect(seeded_db) as connection:
        before = connection.iterdump()
        original = list(before)
    assert cli.main(args) == 2
    assert capsys.readouterr().out.strip() == "Parameter city cannot be empty"
    with connect(seeded_db) as connection:
        assert list(connection.iterdump()) == original


@pytest.mark.parametrize("command,options", [
    ("open-return", ["--reason", "not_wanted"]),
    ("open-claim", ["--kind", "damage", "--amount", "500"]),
    ("change-address", ["--city", "Tanta", "--line", "14 Oak Street"]),
])
def test_backdated_cli_writes_are_bad_input_and_leave_no_record(seeded_db, capsys, command, options):
    with connect(seeded_db) as connection:
        original = list(connection.iterdump())
    assert cli.main([command, "BYL260448907", *options, "--by", "karim.nassar",
                     "--at", "2026-10-17T10:00:00Z", "--db", str(seeded_db)]) == 2
    assert capsys.readouterr().out.strip() == (
        "The time given is earlier than the latest record for this shipment "
        "(2026-10-19T10:00:00Z). Check again at a time after it.")
    with connect(seeded_db) as connection:
        assert list(connection.iterdump()) == original
