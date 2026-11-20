from datetime import datetime

import pytest

from bayline import repository as repo
from bayline.db import connect
from bayline.models import Service
from bayline.sample.generate import AS_OF


def test_lookup_and_models(seeded_db):
    with connect(seeded_db) as conn:
        s = repo.get_shipment(conn, "byl 2604-11871")
        assert s.service is Service.STANDARD
        assert isinstance(s.created_at, datetime) and s.created_at.tzinfo
        c = repo.get_customer(conn, "TAREK.SOROUR@EXAMPLE.COM")
        assert c.id == "CUS-00101"
        assert repo.get_customer(conn, c.id) == c
        assert [x.tracking_number for x in repo.customer_shipments(conn, c.id)] == [s.tracking_number]
        events = repo.get_events(conn, s.tracking_number)
        assert events == sorted(events, key=lambda e: (e.occurred_at, e.id))
        assert repo.snapshot_time(conn) == AS_OF
        summary = repo.shipment_summary(conn, s.tracking_number, AS_OF)
        assert summary["status"] == "delivered"
        stats = repo.stats(conn, AS_OF)
        assert sum(stats["shipments_by_status"].values()) == 400
        assert sum(stats["shipments_by_delay"].values()) == 400
        assert sum(stats["messages_by_status"].values()) == 240
        assert sum(stats["messages_by_topic"].values()) == 240


@pytest.mark.parametrize("lookup,value", [(repo.get_shipment, "BYL260480009"),
    (repo.get_customer, "CUS-99999"), (repo.get_message, "M-99999"), (repo.get_labels, "M-99999")])
def test_not_found(seeded_db, lookup, value):
    with connect(seeded_db) as conn, pytest.raises(repo.NotFoundError):
        lookup(conn, value)


def test_messages_and_limits(seeded_db):
    with connect(seeded_db) as conn:
        messages = repo.list_messages(conn, "new", 5)
        assert len(messages) == 5 and all(m.status == "new" for m in messages)
        assert not hasattr(messages[0], "labels")
        assert repo.get_labels(conn, messages[0].id).message_id == messages[0].id
        assert len(repo.get_replies(conn, "M-00001")) == 1
        for limit in (-1, 0, 1001):
            with pytest.raises(ValueError):
                repo.list_messages(conn, limit=limit)
        with pytest.raises(ValueError):
            repo.list_messages(conn, status="invalid")
        with pytest.raises(ValueError):
            repo.get_shipment(conn, "BYL260411872")
