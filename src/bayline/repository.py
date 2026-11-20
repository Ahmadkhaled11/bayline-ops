"""Read queries return immutable domain records."""

import json
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import get_type_hints

from .models import TABLE_MODELS, MessageStatus
from .rules.delays import classify_delay
from .status import current_status
from .timeutil import parse_utc, to_utc_text
from .tracking_numbers import is_valid, normalise


class NotFoundError(LookupError):
    pass


def json_value(value):
    if isinstance(value, datetime):
        return to_utc_text(value)
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Cannot encode {type(value).__name__}")


def model_from_row(table, row):
    model = TABLE_MODELS[table]
    values = dict(row)
    for key, typ in get_type_hints(model).items():
        value = values[key]
        if value is None:
            continue
        if typ is datetime or typ == datetime | None:
            values[key] = parse_utc(value)
        elif typ == tuple[str, ...]:
            values[key] = tuple(json.loads(value))
        elif typ is bool:
            values[key] = bool(value)
        elif isinstance(typ, type) and issubclass(typ, StrEnum):
            values[key] = typ(value)
    return model(**values)


def records(connection, table, where="", params=(), order=""):
    if table not in TABLE_MODELS:
        raise ValueError("Unknown table")
    query = f"SELECT * FROM {table}"
    if where:
        query += " WHERE " + where
    if order:
        query += " ORDER BY " + order
    return [model_from_row(table, r) for r in connection.execute(query, params)]


def _one(rows, description):
    if not rows:
        raise NotFoundError(description)
    return rows[0]


def snapshot_time(connection):
    row = connection.execute("SELECT value FROM meta WHERE key = 'as_of'").fetchone()
    if row is None:
        raise ValueError("Database has no snapshot time")
    return parse_utc(row[0])


def get_shipment(connection, tracking_number):
    tn = normalise(tracking_number)
    if not is_valid(tn):
        raise ValueError("Invalid tracking number")
    return _one(records(connection, "shipments", "tracking_number = ?", (tn,)), "Shipment not found")


def get_customer(connection, id_or_email):
    return _one(records(connection, "customers", "id = ? OR lower(email) = lower(?)",
                        (id_or_email, id_or_email)), "Customer not found")


def customer_shipments(connection, customer_id):
    return records(connection, "shipments", "merchant_id = ? OR recipient_id = ?",
                   (customer_id, customer_id), "tracking_number")


def get_events(connection, tn, at=None):
    rows = records(connection, "tracking_events", "tracking_number = ?", (tn,), "occurred_at,id")
    return [r for r in rows if at is None or r.occurred_at <= at]


def get_returns(connection, tn):
    return records(connection, "return_cases", "tracking_number = ?", (tn,), "opened_at,id")


def get_claims(connection, tn):
    return records(connection, "claims", "tracking_number = ?", (tn,), "opened_at,id")


def get_address_changes(connection, tn):
    return records(connection, "address_changes", "tracking_number = ?", (tn,), "requested_at,id")


def list_messages(connection, status=None, limit=20):
    if not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("Limit must be between 1 and 1000")
    if status is not None:
        MessageStatus(status)
    return records(connection, "messages", "status = ?" if status else "",
                   (status,) if status else (), "received_at,id")[:limit]


def get_message(connection, message_id):
    return _one(records(connection, "messages", "id = ?", (message_id,)), "Message not found")


def get_replies(connection, message_id):
    return records(connection, "replies", "message_id = ?", (message_id,), "sent_at,id")


def get_labels(connection, message_id):
    return _one(records(connection, "message_labels", "message_id = ?", (message_id,)), "Labels not found")


def shipment_summary(connection, tn, at):
    shipment = get_shipment(connection, tn)
    events = get_events(connection, shipment.tracking_number, at)
    delay = classify_delay(shipment, events, at)
    return {**asdict(shipment), "status": current_status(events), "promised_date": delay.promised,
            "delay_class": delay.delay_class, "late_business_days": delay.late_business_days}


def stats(connection, at):
    statuses, delays = Counter(), Counter()
    all_events = records(connection, "tracking_events", order="occurred_at,id")
    grouped = {}
    for event in all_events:
        grouped.setdefault(event.tracking_number, []).append(event)
    for shipment in records(connection, "shipments", order="tracking_number"):
        if shipment.created_at <= at:
            events = grouped.get(shipment.tracking_number, [])
            statuses[current_status(events, at)] += 1
            delays[classify_delay(shipment, events, at).delay_class] += 1
    messages = records(connection, "messages")
    visible = {m.id for m in messages if m.received_at <= at}
    return {"shipments_by_status": dict(sorted(statuses.items())),
        "shipments_by_delay": dict(sorted(delays.items())),
        "messages_by_status": dict(sorted(Counter(m.status for m in messages if m.id in visible).items())),
        "messages_by_topic": dict(sorted(Counter(x.primary_topic for x in records(connection, "message_labels") if x.message_id in visible).items()))}
