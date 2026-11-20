from dataclasses import FrozenInstanceError

import pytest

from bayline.db import connect, create_schema, transaction
from bayline.models import EventCode, TrackingEvent
from bayline.status import EVENT_STATUS, current_status
from bayline.timeutil import parse_utc


@pytest.mark.parametrize("code", list(EventCode))
def test_event_status(code):
    event = TrackingEvent(1, "BYL260411871", parse_utc("2026-10-01T08:00:00Z"), code, "Cairo", "")
    assert current_status([event]) == (EVENT_STATUS[code] or "created")
    with pytest.raises(FrozenInstanceError):
        event.id = 2


def test_order_and_cutoff():
    t = parse_utc("2026-10-01T08:00:00Z")
    events = [TrackingEvent(i, "BYL260411871", t, code, "Cairo", "") for i, code in
              [(3, EventCode.ADDRESS_CHANGED), (2, EventCode.DELIVERED), (1, EventCode.PICKED_UP)]]
    assert current_status(events) == "delivered"
    assert current_status(events, parse_utc("2026-09-30T08:00:00Z")) == "created"
    assert current_status([]) == "created"


def test_schema_and_rollback(tmp_path):
    import sqlite3

    with connect(tmp_path / "test.db") as conn:
        create_schema(conn)
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError), transaction(conn):
            conn.execute("INSERT INTO staff VALUES ('x', 'Test Name', 'desk', 'customer_service')")
            conn.execute("INSERT INTO staff VALUES ('y', 'Test Name', 'desk', 'bad')")
        assert conn.execute("SELECT count(*) FROM staff").fetchone()[0] == 0


@pytest.mark.parametrize("table,field,value", [
    ("shipments", "service", "bad"), ("shipments", "lane", "bad"),
    ("shipments", "pieces", 11), ("shipments", "pieces", 1.5),
    ("shipments", "weight_kg", 300.1), ("shipments", "weight_kg", 1.01),
    ("shipments", "declared_value_piastres", -1), ("shipments", "declared_value_piastres", 100.5),
    ("shipments", "merchant_id", "CUS-99999"), ("tracking_events", "code", "UNKNOWN"),
    ("return_cases", "decision_code", "UNKNOWN"), ("claims", "kind", "UNKNOWN"),
    ("address_changes", "status", "UNKNOWN"), ("messages", "channel", "UNKNOWN"),
    ("message_labels", "topics", "{}"), ("documents", "layout", "d"),
])
def test_database_constraints(seeded_db, tmp_path, table, field, value):
    import shutil
    import sqlite3

    path = tmp_path / "constraints.db"
    shutil.copyfile(seeded_db, path)
    with connect(path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"UPDATE {table} SET {field} = ?", (value,))
