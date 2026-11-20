import shutil
import sqlite3

import pytest

from bayline import repository as repo
from bayline import services
from bayline.db import connect
from bayline.sample.generate import AS_OF
from bayline.timeutil import parse_utc


def _earlier_time_message(time):
    return ("The time given is earlier than the latest record for this shipment "
            f"({time}). Check again at a time after it.")


@pytest.fixture
def writable_db(seeded_db, tmp_path):
    path = tmp_path / "writable.db"
    shutil.copyfile(seeded_db, path)
    with connect(path) as conn:
        yield conn


def test_returns_success_refusal_and_duplicate(writable_db):
    conn = writable_db
    at = parse_utc("2026-10-24T19:40:00Z")
    d = services.open_return(conn, "BYL260411871", "not_wanted", "reem.adel", at)
    assert d.allowed
    assert repo.get_returns(conn, "BYL260411871")[-1].decision_code == d.reason
    d = services.open_return(conn, "BYL260411871", "other", "reem.adel", at)
    assert d.reason == "ALREADY_OPEN"
    assert repo.get_returns(conn, "BYL260411871")[-1].status == "refused"


def test_claims(writable_db):
    d = services.open_claim(writable_db, "BYL260455803", "damage", 850000, "reem.adel", parse_utc("2026-10-26T07:00:00Z"))
    assert d.payable_piastres == 300000
    row = repo.get_claims(writable_db, "BYL260455803")[-1]
    assert row.status == "open" and row.payable_piastres == 300000
    d = services.open_claim(writable_db, "BYL260455803", "damage", 0, "reem.adel", AS_OF)
    assert d.reason == "INVALID_AMOUNT"
    assert repo.get_claims(writable_db, "BYL260455803")[-1].status == "refused"


def test_address_change_and_refusal(writable_db):
    conn = writable_db
    at = parse_utc("2026-10-31T12:00:00Z")
    before = len(repo.get_events(conn, "BYL260462072"))
    assert services.record_address_change(conn, "BYL260462072", " cairo ", "8 Ribbon Row", "reem.adel", at).allowed
    assert len(repo.get_events(conn, "BYL260462072")) == before + 1
    assert repo.get_shipment(conn, "BYL260462072").address_line == "8 Ribbon Row"
    d = services.record_address_change(conn, "BYL260462072", "Cairo", "9 Ribbon Row", "reem.adel", AS_OF)
    assert d.reason == "ALREADY_CHANGED"
    assert len(repo.get_events(conn, "BYL260462072")) == before + 1
    assert repo.get_address_changes(conn, "BYL260462072")[-1].status == "refused"


def test_transaction_rollback_on_second_write(writable_db):
    conn = writable_db
    conn.execute("CREATE TRIGGER reject_event BEFORE INSERT ON tracking_events BEGIN SELECT RAISE(ABORT, 'event blocked'); END")
    before = repo.get_shipment(conn, "BYL260462072")
    with pytest.raises(sqlite3.IntegrityError):
        services.record_address_change(conn, before.tracking_number, "Cairo", "8 Ribbon Row", "reem.adel", AS_OF)
    assert repo.get_address_changes(conn, before.tracking_number) == []
    assert repo.get_shipment(conn, before.tracking_number) == before
    conn.execute("DROP TRIGGER reject_event")
    assert services.record_address_change(conn, before.tracking_number, "Cairo", "8 Ribbon Row", "reem.adel", AS_OF).allowed


def test_reply_and_rollback(writable_db):
    conn = writable_db
    mid = "M-01001"
    rid = services.record_reply(conn, mid, "karim.nassar", "Thank you. We have your message.", AS_OF)
    assert repo.get_message(conn, mid).status == "answered"
    assert repo.get_replies(conn, mid)[-1].id == rid
    conn.execute("CREATE TRIGGER reject_message BEFORE UPDATE ON messages BEGIN SELECT RAISE(ABORT, 'message blocked'); END")
    with pytest.raises(sqlite3.IntegrityError):
        services.record_reply(conn, "M-01002", "karim.nassar", "Thank you.", AS_OF)
    assert repo.get_replies(conn, "M-01002") == []
    assert repo.get_message(conn, "M-01002").status == "new"


def test_bad_inputs_leave_no_rows(writable_db):
    conn = writable_db
    for author, body, time, error in [("unknown", "text", AS_OF, repo.NotFoundError),
        ("karim.nassar", " ", AS_OF, ValueError),
        ("karim.nassar", "text", parse_utc("2026-08-01T00:00:00Z"), ValueError)]:
        with pytest.raises(error):
            services.record_reply(conn, "M-01001", author, body, time)
    assert repo.get_replies(conn, "M-01001") == []


def test_second_claim_cannot_precede_the_existing_claim(writable_db):
    conn = writable_db
    tn = "BYL260448907"
    assert services.open_claim(conn, tn, "damage", 50000, "karim.nassar",
                               parse_utc("2026-11-01T10:00:00Z")).eligible
    before = conn.total_changes
    with pytest.raises(ValueError) as error:
        services.open_claim(conn, tn, "damage", 50000, "karim.nassar",
                            parse_utc("2026-11-01T09:00:00Z"))
    assert str(error.value) == _earlier_time_message("2026-11-01T10:00:00Z")
    assert conn.total_changes == before
    assert len(repo.get_claims(conn, tn)) == 1
    assert repo.get_claims(conn, tn)[0].status == "open"


def test_address_change_cannot_precede_a_delivery(writable_db):
    conn = writable_db
    tn = "BYL260448907"
    shipment = repo.get_shipment(conn, tn)
    events = repo.get_events(conn, tn)
    before = conn.total_changes
    with pytest.raises(ValueError) as error:
        services.record_address_change(conn, tn, "Tanta", "14 Oak Street", "karim.nassar",
                                       parse_utc("2026-10-17T10:00:00Z"))
    assert str(error.value) == _earlier_time_message("2026-10-19T10:00:00Z")
    assert conn.total_changes == before
    assert repo.get_shipment(conn, tn) == shipment
    assert repo.get_events(conn, tn) == events
    assert repo.get_address_changes(conn, tn) == []


@pytest.mark.parametrize("command", ["return", "claim", "address"])
def test_write_at_the_latest_scan_is_allowed(writable_db, command):
    conn = writable_db
    tn = "BYL260448907"
    at = parse_utc("2026-10-19T10:00:00Z")
    if command == "return":
        assert services.open_return(conn, tn, "not_wanted", "karim.nassar", at).allowed
        assert repo.get_returns(conn, tn)[-1].opened_at == at
    elif command == "claim":
        assert services.open_claim(conn, tn, "damage", 50000, "karim.nassar", at).eligible
        assert repo.get_claims(conn, tn)[-1].opened_at == at
    else:
        result = services.record_address_change(conn, tn, "Tanta", "14 Oak Street",
                                                "karim.nassar", at)
        assert result.reason == "TOO_LATE"
        assert repo.get_address_changes(conn, tn)[-1].requested_at == at


@pytest.mark.parametrize("existing", ["return", "claim", "address"])
@pytest.mark.parametrize("command", ["return", "claim", "address"])
def test_write_cannot_precede_any_kind_of_case(writable_db, existing, command):
    conn = writable_db
    tn = "BYL260448907"

    def write(kind, at):
        if kind == "return":
            return services.open_return(conn, tn, "not_wanted", "karim.nassar", at)
        if kind == "claim":
            return services.open_claim(conn, tn, "damage", 50000, "karim.nassar", at)
        return services.record_address_change(conn, tn, "Tanta", "14 Oak Street",
                                              "karim.nassar", at)

    write(existing, parse_utc("2026-11-01T10:00:00Z"))
    before = conn.total_changes
    with pytest.raises(ValueError) as error:
        write(command, parse_utc("2026-11-01T09:00:00Z"))
    assert str(error.value) == _earlier_time_message("2026-11-01T10:00:00Z")
    assert conn.total_changes == before


def test_write_at_the_latest_case_time_is_allowed(writable_db):
    conn = writable_db
    tn = "BYL260448907"
    at = parse_utc("2026-11-01T10:00:00Z")
    assert services.open_claim(conn, tn, "damage", 50000, "karim.nassar", at).eligible
    result = services.open_claim(conn, tn, "damage", 50000, "karim.nassar", at)
    assert result.reason == "ALREADY_EXISTS"
    assert [c.status for c in repo.get_claims(conn, tn)] == ["open", "refused"]


def test_historical_read_checks_remain_available_after_a_later_record(writable_db):
    conn = writable_db
    tn = "BYL260448907"
    assert services.open_claim(conn, tn, "damage", 50000, "karim.nassar",
                               parse_utc("2026-11-01T10:00:00Z")).eligible
    before = conn.total_changes
    at = parse_utc("2026-11-01T09:00:00Z")
    assert services.check_claim(conn, tn, "damage", 50000, at).eligible
    assert services.check_return(conn, tn, at).allowed
    assert services.check_address_change(conn, tn, "Tanta", parse_utc("2026-10-17T10:00:00Z")).allowed
    assert conn.total_changes == before


def test_write_cannot_precede_a_recorded_case_decision(writable_db):
    conn = writable_db
    tn = "BYL260448907"
    case_id, _ = services.open_claim(conn, tn, "damage", 50000, "karim.nassar",
                                    parse_utc("2026-11-01T10:00:00Z"), include_id=True)
    conn.execute("UPDATE claims SET status = 'approved', decided_at = ?, decided_by = ? WHERE id = ?",
                 ("2026-11-01T12:00:00Z", "karim.nassar", case_id))
    conn.commit()
    before = conn.total_changes
    with pytest.raises(ValueError) as error:
        services.open_return(conn, tn, "not_wanted", "karim.nassar",
                             parse_utc("2026-11-01T11:00:00Z"))
    assert str(error.value) == _earlier_time_message("2026-11-01T12:00:00Z")
    assert conn.total_changes == before
    assert repo.get_returns(conn, tn) == []
