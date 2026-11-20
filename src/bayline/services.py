"""Rule decisions and their writes share one transaction."""

from . import repository as repo
from .db import insert_record, transaction
from .models import AddressChange, Claim, ClaimKind, Reply, ReturnCase, ReturnCause, TrackingEvent
from .rules.address import check_address_change as address_rule
from .rules.claims import check_claim as claim_rule
from .rules.returns import check_return as return_rule
from .timeutil import to_utc_text


def _next_id(connection, table, prefix):
    row = connection.execute(f"SELECT max(CAST(substr(id, 5) AS INTEGER)) FROM {table}").fetchone()
    return f"{prefix}-{(row[0] or 0)+1:05}"


def _staff(connection, staff_id):
    if not repo.records(connection, "staff", "id = ?", (staff_id,)):
        raise repo.NotFoundError("Staff member not found")


def _context(connection, tn, at, by):
    _staff(connection, by)
    s = repo.get_shipment(connection, tn)
    events = repo.get_events(connection, s.tracking_number)
    times = [s.created_at, *(e.occurred_at for e in events)]
    for case in [*repo.get_returns(connection, s.tracking_number),
                 *repo.get_claims(connection, s.tracking_number)]:
        times.append(case.opened_at)
        if case.decided_at is not None:
            times.append(case.decided_at)
    times.extend(c.requested_at for c in repo.get_address_changes(connection, s.tracking_number))
    latest = max(times)
    if at < latest:
        raise ValueError(
            "The time given is earlier than the latest record for this shipment "
            f"({to_utc_text(latest)}). Check again at a time after it.")
    return s, events


def check_return(connection, tracking_number, at):
    shipment = repo.get_shipment(connection, tracking_number)
    return return_rule(shipment, repo.get_events(connection, shipment.tracking_number, at),
                       repo.get_customer(connection, shipment.merchant_id),
                       repo.get_returns(connection, shipment.tracking_number), at)


def check_claim(connection, tracking_number, kind, claimed_piastres, at):
    shipment = repo.get_shipment(connection, tracking_number)
    return claim_rule(shipment, repo.get_events(connection, shipment.tracking_number, at),
                      kind, claimed_piastres,
                      repo.get_claims(connection, shipment.tracking_number), at)


def check_address_change(connection, tracking_number, new_city, at):
    if not new_city.strip():
        raise ValueError("Parameter city cannot be empty")
    shipment = repo.get_shipment(connection, tracking_number)
    return address_rule(shipment, repo.get_events(connection, shipment.tracking_number, at),
                        new_city, repo.get_address_changes(connection, shipment.tracking_number),
                        at)


def open_return(connection, tn, reason, by, at, *, include_id=False):
    reason = ReturnCause(reason)
    with transaction(connection):
        s, _ = _context(connection, tn, at, by)
        d = check_return(connection, s.tracking_number, at)
        case_id = _next_id(connection, "return_cases", "RET")
        insert_record(connection, "return_cases", ReturnCase(case_id, s.tracking_number, at, reason,
            "open" if d.allowed else "refused", d.reason, None if d.allowed else at,
            None if d.allowed else by, ""))
    return (case_id, d) if include_id else d


def open_claim(connection, tn, kind, claimed_piastres, by, at, *, include_id=False):
    kind = ClaimKind(kind)
    with transaction(connection):
        s, _ = _context(connection, tn, at, by)
        d = check_claim(connection, s.tracking_number, kind, claimed_piastres, at)
        case_id = _next_id(connection, "claims", "CLM")
        insert_record(connection, "claims", Claim(case_id, s.tracking_number, kind, at, claimed_piastres,
            "open" if d.eligible else "refused", d.reason, d.payable_piastres, None if d.eligible else at,
            None if d.eligible else by, ""))
    return (case_id, d) if include_id else d


def record_address_change(connection, tn, new_city, new_address_line, by, at, *, include_id=False):
    if not new_address_line.strip():
        raise ValueError("New address cannot be empty")
    with transaction(connection):
        s, _ = _context(connection, tn, at, by)
        d = check_address_change(connection, s.tracking_number, new_city, at)
        case_id = _next_id(connection, "address_changes", "ADR")
        city = s.destination_city if d.allowed else new_city.strip()
        insert_record(connection, "address_changes", AddressChange(case_id, s.tracking_number, at,
            city, new_address_line.strip(), "applied" if d.allowed else "refused", d.reason, by))
        if d.allowed:
            event_id = connection.execute("SELECT coalesce(max(id),0)+1 FROM tracking_events").fetchone()[0]
            insert_record(connection, "tracking_events", TrackingEvent(event_id, s.tracking_number,
                at, "ADDRESS_CHANGED", city, "Address updated to " + new_address_line.strip()))
            connection.execute("UPDATE shipments SET address_line = ? WHERE tracking_number = ?",
                               (new_address_line.strip(), s.tracking_number))
    return (case_id, d) if include_id else d


def record_reply(connection, message_id, author, body, at):
    if not body.strip():
        raise ValueError("Reply cannot be empty")
    with transaction(connection):
        _staff(connection, author)
        message = repo.get_message(connection, message_id)
        if at < message.received_at:
            raise ValueError("Reply precedes the message")
        reply_id = _next_id(connection, "replies", "REP")
        insert_record(connection, "replies", Reply(reply_id, message_id, at, author, body))
        connection.execute("UPDATE messages SET status = 'answered' WHERE id = ?", (message_id,))
    return reply_id
