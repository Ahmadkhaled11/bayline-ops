from dataclasses import replace
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bayline.business_days import is_business_day
from bayline.sample.generate import (
    AS_OF,
    _customer_hour_weight,
    _customer_time,
    _message_decision,
    _message_window,
    _reply_time,
    _topic_window,
)

CAIRO = ZoneInfo("Africa/Cairo")


@pytest.mark.parametrize("hour,weight", [(0, .25), (5, .25), (6, .5), (7, .5), (8, 1), (23, 1)])
def test_customer_hour_weights(hour, weight):
    assert _customer_hour_weight(hour) == weight


@pytest.mark.parametrize("arrival,delay,expected", [
    ("2026-10-22T12:00:00", 481, "2026-10-22T12:08:01"),
    ("2026-10-22T19:50:00", 480, "2026-10-22T19:58:00"),
    ("2026-10-22T19:50:00", 600, "2026-10-25T08:05:01"),
    ("2026-10-22T19:50:00", 2700, "2026-10-25T08:05:01"),
    ("2026-10-22T03:00:00", None, "2026-10-22T08:05:01"),
    ("2026-10-23T12:00:00", None, "2026-10-25T08:05:01"),
    ("2026-10-05T21:00:00", None, "2026-10-07T08:05:01"),
])
def test_reply_clock_respects_opening_and_closing(arrival, delay, expected):
    class Draw:
        def randint(self, low, high):
            if (low, high) == (480, 2700):
                assert delay is not None
                return delay
            assert (low, high) == (0, 8700)
            return 1

    received = datetime.fromisoformat(arrival).replace(tzinfo=CAIRO)
    assert _reply_time(received, Draw()).astimezone(CAIRO) == datetime.fromisoformat(expected).replace(tzinfo=CAIRO)


def test_customer_time_keeps_partial_hour_boundaries():
    start = datetime(2026, 10, 22, 5, 59, 59, tzinfo=CAIRO)
    end = start + timedelta(seconds=1)

    class Draw:
        def __init__(self, value):
            self.value = value

        def randrange(self, size):
            assert size == 3
            return self.value

    assert _customer_time(start, end, Draw(0)) == start
    assert _customer_time(start, end, Draw(1)) == end
    assert _customer_time(start, end, Draw(2)) == end
    with pytest.raises(ValueError, match="No customer time"):
        _customer_time(end, start, Draw(0))


def test_generated_messages_obey_topic_windows(monkeypatch):
    import bayline.sample.generate as generator

    current = {}
    arrivals = {}
    original_window = generator._message_window
    original_time = generator._customer_time

    def window(topics, parcel, delivered, claim=None):
        current["parcel"] = parcel
        return original_window(topics, parcel, delivered, claim)

    def customer_time(*args):
        at = original_time(*args)
        if "parcel" in current:
            arrivals[at] = current["parcel"]
        return at

    monkeypatch.setattr(generator, "_message_window", window)
    monkeypatch.setattr(generator, "_customer_time", customer_time)
    sample = generator.generate()
    shipments = {s.tracking_number: s for s in sample.tables["shipments"]}
    messages = {m.id: m for m in sample.tables["messages"]}
    histories = {number: [] for number in shipments}
    for event in sample.tables["tracking_events"]:
        histories[event.tracking_number].append(event)
    for label in sample.tables["message_labels"]:
        message = messages[label.message_id]
        if message.origin != "generated":
            continue
        assert datetime(2026, 9, 1, tzinfo=CAIRO) <= message.received_at <= AS_OF
        parcel = arrivals[message.received_at]
        for number in [parcel.tracking_number]:
            delivered = next((e.occurred_at for e in histories[number] if e.code == "DELIVERED"), None)
            topics = set(label.topics)
            if "address_change" in topics:
                assert topics <= {"address_change", "status_question", "delay"}
                if delivered:
                    assert message.received_at < delivered
            if topics & {"return", "damage"}:
                assert delivered is not None
                assert topics <= {"return", "damage", "status_question", "delay"}
                assert message.received_at >= delivered + timedelta(hours=1)
                days = max({"return": 45, "damage": 30, "status_question": 3, "delay": 7}[t] for t in topics)
                assert message.received_at <= min(AS_OF, delivered + timedelta(days=days))
            elif label.primary_topic == "claim_followup":
                claims = [c for c in sample.tables["claims"] if c.tracking_number == number]
                if claims:
                    assert any(c.opened_at < message.received_at <= c.opened_at + timedelta(days=21) for c in claims)
                else:
                    assert delivered is not None
                    assert delivered + timedelta(hours=1) <= message.received_at <= delivered + timedelta(days=30)
            elif label.primary_topic in ("status_question", "delay", "address_change"):
                assert message.received_at >= parcel.created_at + timedelta(hours=1)
                if delivered:
                    days = {"status_question": 3, "delay": 7, "address_change": 0}[label.primary_topic]
                    assert message.received_at <= delivered + timedelta(days=days)


def test_generated_delay_claims_need_no_amount(sample):
    for claim in sample.tables["claims"]:
        if claim.kind == "delay":
            assert claim.claimed_piastres == 0


def test_replies_keep_decisions_and_visible_cases_at_both_times(sample):
    messages = {m.id: m for m in sample.tables["messages"]}
    labels = {label.message_id: label for label in sample.tables["message_labels"]}
    shipments = {s.tracking_number: s for s in sample.tables["shipments"]}
    customers = {c.id: c for c in sample.tables["customers"]}
    histories = {number: [] for number in shipments}
    for event in sample.tables["tracking_events"]:
        histories[event.tracking_number].append(event)
    for reply in sample.tables["replies"]:
        received = messages[reply.message_id].received_at
        sent = reply.sent_at.astimezone(CAIRO)
        assert received < reply.sent_at <= AS_OF
        assert is_business_day(sent.date()) and time(8) <= sent.time() < time(20)
        label = labels[reply.message_id]
        for number in label.tracking_numbers:
            parcel = shipments[number]
            for topic in label.topics:
                answers = [_message_decision(topic, parcel, histories[number],
                    customers[parcel.merchant_id], sample.tables, at) for at in (received, reply.sent_at)]
                assert answers[0] == answers[1], reply.id


@pytest.mark.parametrize("topic,days", [("status_question", 3), ("delay", 7), ("return", 45), ("damage", 30)])
def test_topic_window_ends_at_the_defined_delivery_offset(sample, topic, days):
    parcel = replace(sample.tables["shipments"][0], created_at=datetime(2026, 9, 1, tzinfo=CAIRO))
    delivered = datetime(2026, 9, 10, 12, tzinfo=CAIRO)
    lower, upper = _topic_window(topic, parcel, delivered)
    assert upper == delivered + timedelta(days=days)
    if topic in ("return", "damage"):
        assert lower == delivered + timedelta(hours=1)


@pytest.mark.parametrize("second", [0, 8700])
def test_next_opening_reply_includes_both_morning_boundaries(second):
    class Draw:
        def randint(self, low, high):
            assert (low, high) == (0, 8700)
            return second

    received = datetime(2026, 10, 22, 3, tzinfo=CAIRO)
    sent = _reply_time(received, Draw()).astimezone(CAIRO)
    assert sent == datetime(2026, 10, 22, 8, 5, tzinfo=CAIRO) + timedelta(seconds=second)


def test_topic_windows_reject_expired_and_undelivered_requests(sample):
    parcel = sample.tables["shipments"][0]
    delivered = datetime(2026, 7, 1, tzinfo=CAIRO)
    for topic in ("status_question", "delay", "address_change", "return", "damage", "claim_followup"):
        assert _topic_window(topic, parcel, delivered) is None
    for topic in ("return", "damage", "claim_followup"):
        assert _topic_window(topic, parcel, None) is None
    for topic in ("status_question", "delay", "address_change"):
        assert _topic_window(topic, parcel, None) == (parcel.created_at + timedelta(hours=1), AS_OF)


def test_address_and_claim_windows_keep_their_second_boundaries(sample):
    parcel = sample.tables["shipments"][0]
    delivered = datetime(2026, 10, 1, tzinfo=CAIRO)
    assert _topic_window("address_change", parcel, delivered)[1] == delivered - timedelta(seconds=1)
    claim = replace(sample.tables["claims"][0], opened_at=datetime(2026, 10, 5, tzinfo=CAIRO))
    assert _topic_window("claim_followup", parcel, delivered, claim) == (
        claim.opened_at + timedelta(seconds=1), claim.opened_at + timedelta(days=21))


@pytest.mark.parametrize("topics,days", [
    (("status_question", "return"), 45),
    (("delay", "damage"), 30),
    (("damage", "return"), 45),
    (("address_change", "delay"), 0),
])
def test_second_topic_uses_the_shared_delivery_window(sample, topics, days):
    parcel = replace(sample.tables["shipments"][0], created_at=datetime(2026, 9, 1, tzinfo=CAIRO))
    delivered = datetime(2026, 9, 10, tzinfo=CAIRO)
    lower, upper = _message_window(topics, parcel, delivered)
    if "address_change" in topics:
        assert lower == parcel.created_at + timedelta(hours=1)
        assert upper == delivered - timedelta(seconds=1)
    else:
        assert lower == delivered + timedelta(hours=1)
        assert upper == delivered + timedelta(days=days)


def test_required_case_enquiries_remain_available(sample):
    messages = {m.id: m for m in sample.tables["messages"]}
    labels = {label.message_id: label for label in sample.tables["message_labels"]}
    seen = set()
    for reply in sample.tables["replies"]:
        label = labels[reply.message_id]
        if not label.tracking_numbers:
            continue
        number = label.tracking_numbers[0]
        at = messages[reply.message_id].received_at
        if label.primary_topic == "claim_followup":
            claims = [c for c in sample.tables["claims"] if c.tracking_number == number and c.opened_at < at]
            if not claims:
                seen.add("no_claim")
            if len(claims) == 1 and claims[0].status == "refused" and claims[0].decided_at <= at:
                seen.add("refused_claim")
        if label.primary_topic == "return" and any(
            r.tracking_number == number and r.status == "received" and r.decided_at < at
            for r in sample.tables["return_cases"]
        ):
            seen.add("received_return")
    assert seen == {"no_claim", "refused_claim", "received_return"}


def test_message_selection_stops_when_no_window_remains(monkeypatch):
    import bayline.sample.generate as generator

    monkeypatch.setattr(generator, "_message_window", lambda *args: None)
    with pytest.raises(ValueError, match="No shipment and arrival"):
        generator.generate()


def test_shared_window_can_outlast_an_expired_status_window(sample):
    parcel = sample.tables["shipments"][0]
    delivered = datetime(2026, 8, 20, tzinfo=CAIRO)
    assert _topic_window("status_question", parcel, delivered) is None
    assert _message_window(("status_question", "return"), parcel, delivered) == (
        datetime(2026, 9, 1, tzinfo=CAIRO), delivered + timedelta(days=45))


def test_customer_time_keeps_both_hours_when_cairo_clocks_go_back():
    start = datetime(2026, 10, 29, 23, tzinfo=CAIRO, fold=0)
    end = datetime(2026, 10, 29, 23, 59, 59, tzinfo=CAIRO, fold=1)

    class Draw:
        def randrange(self, size):
            assert size == 2 * 3600 * 4
            return 3600 * 4

    at = _customer_time(start, end, Draw()).astimezone(CAIRO)
    assert at.hour == 23 and at.minute == 0 and at.second == 0 and at.fold == 1
