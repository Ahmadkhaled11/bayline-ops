"""Sample records follow product limits and the desk's recording rules."""

from collections import defaultdict
from datetime import time, timedelta
from zoneinfo import ZoneInfo

import pytest

from bayline import repository, services
from bayline.business_days import add_business_days, is_business_day
from bayline.db import connect, create_schema, insert_record
from bayline.models import Claim, ReturnCase
from bayline.rules.address import check_address_change
from bayline.rules.claims import check_claim
from bayline.rules.delays import classify_delay
from bayline.rules.returns import check_return
from bayline.sample.anchors import ANCHOR_NUMBERS
from bayline.sample.generate import AS_OF, VALUE_RANGES, _reply_time
from bayline.sample.texts import render_reply
from bayline.timeutil import parse_utc
from tests.helpers import MERCHANT, history, shipment

CAIRO = ZoneInfo("Africa/Cairo")


def _maps(sample):
    shipments = {s.tracking_number: s for s in sample.tables["shipments"]}
    customers = {c.id: c for c in sample.tables["customers"]}
    events = defaultdict(list)
    for event in sample.tables["tracking_events"]:
        events[event.tracking_number].append(event)
    return shipments, customers, events


def test_catalog_values_stay_within_the_category_range(sample):
    for s in sample.tables["shipments"]:
        low, high = VALUE_RANGES[s.goods_category]
        assert low <= s.declared_value_piastres <= high, s.tracking_number


def test_fixed_shipment_weights_and_fees_follow_the_product(sample):
    shipments, _, _ = _maps(sample)
    assert [shipments[n].weight_kg for n in ANCHOR_NUMBERS] == [
        0.9, 0.4, 0.3, 0.4, 0.5, 0.8, 0.4, 18.5, 0.5, 0.2, 0.5, 0.6, 2.4, 0.5, 0.5]


@pytest.mark.parametrize("table", ["return_cases", "claims"])
def test_refused_cases_have_the_same_decision_fields_as_tool_records(sample, table):
    shipments, customers, events = _maps(sample)
    refused = [r for r in sample.tables[table] if r.status == "refused"]
    assert refused
    for row in refused:
        parcel = shipments[row.tracking_number]
        with connect(":memory:") as conn:
            create_schema(conn)
            for staff in sample.tables["staff"]:
                insert_record(conn, "staff", staff)
            for customer_id in (parcel.merchant_id, parcel.recipient_id):
                insert_record(conn, "customers", customers[customer_id])
            insert_record(conn, "shipments", parcel)
            for event in events[row.tracking_number]:
                if event.occurred_at <= row.opened_at:
                    insert_record(conn, "tracking_events", event)
            conn.commit()
            if table == "return_cases":
                services.open_return(conn, parcel.tracking_number, row.reason, row.decided_by, row.opened_at)
                actual = repository.get_returns(conn, parcel.tracking_number)[0]
                assert actual.decision_code == row.decision_code
            else:
                services.open_claim(conn, parcel.tracking_number, row.kind, row.claimed_piastres,
                                    row.decided_by, row.opened_at)
                actual = repository.get_claims(conn, parcel.tracking_number)[0]
                assert (actual.decision_code, actual.payable_piastres) == (row.decision_code, row.payable_piastres)
            assert (actual.opened_at, actual.decided_at, actual.decided_by, actual.status) == (
                row.opened_at, row.decided_at, row.decided_by, row.status)
            assert row.decided_by in ("hany.nassar", "dina.fawzy", "omar.elbanna")


@pytest.mark.parametrize("status,answer,next_step", [
    ("open", "Return RET-00001 is already open for BYL260411871. It was opened on Thursday 29 October 2026. A shipment can have only one open return at a time.",
     "You do not need to do anything else. We will write to you about the collection."),
    ("approved", "Return RET-00001 for BYL260411871 was opened on Thursday 29 October 2026 and has been approved. We keep one return for each shipment.",
     "Please quote the return number if you write to us about it."),
    ("received", "Return RET-00001 for BYL260411871 was opened on Thursday 29 October 2026. Our records show that the parcel has come back to us. We keep one return for each shipment.",
     "If you have a question about it, reply and quote the return number."),
])
def test_existing_return_wording_names_its_status_at_sending(status, answer, next_step):
    parcel = shipment()
    scans = history(("DELIVERED", "2026-10-28T07:00:00Z"))
    case = ReturnCase("RET-00001", parcel.tracking_number, parse_utc("2026-10-29T07:00:00Z"),
        "not_wanted", status, "ALLOWED", None if status == "open" else AS_OF, None, "")
    decision = check_return(parcel, scans, MERCHANT, [case], AS_OF)
    body = render_reply("return", decision, customer_name="Nadia Farouk", shipment=parcel,
                        events=scans, at=AS_OF, returns=[case])
    assert body == "Hello Nadia,\n\n" + answer + "\n\n" + next_step + "\n\nBayline Cargo Customer Service"
    if status != "open":
        before = render_reply("return", decision, customer_name="Nadia Farouk", shipment=parcel,
                              events=scans, at=AS_OF - timedelta(seconds=1), returns=[case])
        assert "is already open" in before and "has been approved" not in before and "come back" not in before
    at = case.opened_at - timedelta(seconds=1)
    before_decision = check_return(parcel, scans, MERCHANT, [case], at)
    assert before_decision.reason == "ALLOWED"
    before_opening = render_reply("return", before_decision, customer_name="Nadia Farouk", shipment=parcel,
                                  events=scans, at=at, returns=[case])
    assert case.id not in before_opening and "can still be returned" in before_opening


@pytest.mark.parametrize("kind,code,service,reason", [
    ("delay", "NOT_LATE_ENOUGH", "express", "It was refused because the parcel was not late. It was delivered on Monday 26 October 2026, and the promised date was Monday 26 October 2026."),
    ("delay", "SERVICE_NOT_COVERED", "standard", "It was refused because delay claims cover Express shipments only, and this shipment was sent by Standard."),
    ("delay", "SERVICE_NOT_COVERED", "economy", "It was refused because delay claims cover Express shipments only, and this shipment was sent by Economy."),
    *[(k, "WINDOW_CLOSED", "standard", "It was refused because it was made more than 14 days after delivery.") for k in ("delay", "damage")],
    *[(k, "NOT_DELIVERED", "standard", "It was refused because the parcel had not been delivered when the claim was made.") for k in ("delay", "damage")],
    ("loss", "DELIVERED", "standard", "It was refused because our records show the parcel as delivered."),
    ("loss", "NOT_LATE_ENOUGH", "standard", "It was refused because the parcel was not yet late enough for a loss claim. A loss claim can be made 10 business days after the promised date."),
    *[(k, "INVALID_AMOUNT", "standard", "It was refused because it did not state an amount above 0 EGP.") for k in ("damage", "loss")],
    *[(k, "ALREADY_EXISTS", "standard", "It was refused because the shipment already had a claim of the same kind.") for k in ("delay", "damage", "loss")],
])
def test_refused_claim_wording_names_the_stored_rule(kind, code, service, reason):
    parcel = shipment(service=service)
    scans = history(("PICKED_UP", "2026-10-25T07:00:00Z"), ("DELIVERED", "2026-10-26T07:00:00Z"))
    case = Claim("CLM-00001", parcel.tracking_number, kind, parse_utc("2026-10-28T07:00:00Z"),
                 0, "refused", code, 0, parse_utc("2026-10-28T07:00:00Z"), "dina.fawzy", "")
    body = render_reply("claim_followup", None, customer_name="Nadia Farouk", shipment=parcel,
                        events=scans, at=AS_OF, claims=[case])
    assert body == ("Hello Nadia,\n\nYour claim CLM-00001 for BYL260411871 was opened on Wednesday 28 October 2026. "
        + reason + "\n\nIf you think the decision is wrong, reply and tell us why, and we will pass it to the claims team."
        "\n\nBayline Cargo Customer Service")


def test_sample_invalid_number_reply_asks_for_a_new_copy(sample):
    labels = {label.message_id: label for label in sample.tables["message_labels"]}
    replies = [r for r in sample.tables["replies"] if labels[r.message_id].invalid_tracking_mentions]
    assert replies
    for reply in replies:
        number = labels[reply.message_id].invalid_tracking_mentions[0]
        assert reply.body.split("\n\n")[1] == (f"The number you sent, {number}, is not a valid Bayline tracking number. "
            "One of the digits may be wrong. Please copy the number again from the merchant's email and reply with it.")


def test_sample_received_return_reply_reports_that_the_parcel_is_back(sample):
    labels = {label.message_id: label for label in sample.tables["message_labels"]}
    replies = []
    for reply in sample.tables["replies"]:
        label = labels[reply.message_id]
        if "return" not in label.topics or not label.tracking_numbers:
            continue
        cases = [c for c in sample.tables["return_cases"] if c.tracking_number == label.tracking_numbers[0]
                 and c.status == "received" and c.decided_at <= reply.sent_at]
        for case in cases:
            assert case.id in reply.body and "parcel has come back to us" in reply.body
            assert "collection" not in reply.body
            replies.append(reply.id)
    assert replies


def test_sample_refused_claim_reply_explains_the_rule(sample):
    replies = [r for r in sample.tables["replies"] if "It was refused because" in r.body]
    assert replies
    for reply in replies:
        assert "parcel was not late" in reply.body
        assert "promised date was" in reply.body
        assert "If you think the decision is wrong" in reply.body


def test_reply_rule_decisions_agree_at_arrival_and_sending(sample):
    shipments, customers, events = _maps(sample)
    messages = {m.id: m for m in sample.tables["messages"]}
    labels = {label.message_id: label for label in sample.tables["message_labels"]}
    for reply in sample.tables["replies"]:
        message, label = messages[reply.message_id], labels[reply.message_id]
        if not label.tracking_numbers:
            continue
        parcel = shipments[label.tracking_numbers[0]]
        results = []
        for at in (message.received_at, reply.sent_at):
            answers = []
            for topic in label.topics:
                if topic == "return":
                    d = check_return(parcel, events[parcel.tracking_number], customers[parcel.merchant_id], sample.tables["return_cases"], at)
                    answers.append((d.allowed, d.reason))
                elif topic == "damage":
                    answers.append(check_claim(parcel, events[parcel.tracking_number], "damage", max(100, parcel.declared_value_piastres), sample.tables["claims"], at))
                elif topic == "address_change":
                    answers.append(check_address_change(parcel, events[parcel.tracking_number], parcel.destination_city, sample.tables["address_changes"], at))
                elif topic in ("delay", "status_question"):
                    answers.append(classify_delay(parcel, events[parcel.tracking_number], at))
                if topic in ("claim_followup", "return"):
                    table = "claims" if topic == "claim_followup" else "return_cases"
                    answers.append(tuple((c.id, "open" if c.decided_at is None or c.decided_at > at else c.status)
                        for c in sample.tables[table] if c.tracking_number == parcel.tracking_number and c.opened_at <= at))
            results.append(answers)
        assert results[0] == results[1], reply.id


def test_sample_reply_times_follow_the_desk_response_window(sample):
    messages = {m.id: m for m in sample.tables["messages"]}
    for reply in sample.tables["replies"]:
        received = messages[reply.message_id].received_at
        local = received.astimezone(CAIRO)
        sent = reply.sent_at.astimezone(CAIRO)
        if is_business_day(local.date()) and time(8) <= local.time() < time(20):
            if sent.date() == local.date():
                assert 8 * 60 <= (reply.sent_at - received).total_seconds() <= 45 * 60
                assert sent.time() < time(20)
            else:
                assert local.time() >= time(19, 15)
                assert sent.date() == add_business_days(local.date(), 1)
                assert time(8, 5) <= sent.time() <= time(10, 30)
        else:
            expected_day = (local.date() if is_business_day(local.date()) and local.time() < time(8)
                            else add_business_days(local.date(), 1))
            assert sent.date() == expected_day
            assert time(8, 5) <= sent.time() <= time(10, 30)
        assert reply.sent_at <= AS_OF


@pytest.mark.parametrize("arrival", [
    "2026-10-25T07:00:00Z", "2026-10-23T21:00:00Z", "2026-10-25T01:00:00Z",
    "2026-10-05T20:00:00Z", "2026-10-06T06:00:00Z",
])
def test_response_clock_uses_seconds_and_the_next_desk_opening(arrival):
    import random
    received = parse_utc(arrival)
    local = received.astimezone(CAIRO)
    rng = random.Random(41)
    for _ in range(20):
        sent = _reply_time(received, rng).astimezone(CAIRO)
        if is_business_day(local.date()) and time(8) <= local.time() < time(20):
            assert 480 <= (sent - received).total_seconds() <= 2700
        else:
            expected_day = (local.date() if is_business_day(local.date()) and local.time() < time(8)
                            else add_business_days(local.date(), 1))
            assert sent.date() == expected_day
            assert time(8, 5) <= sent.time() <= time(10, 30)


def test_account_join_dates_follow_the_account_period_and_first_booking(sample):
    customers = sample.tables["customers"]
    first_shipments = {}
    for parcel in sample.tables["shipments"]:
        first_shipments[parcel.recipient_id] = min(first_shipments.get(parcel.recipient_id, AS_OF), parcel.created_at)
    fixed = set(f"CUS-{i:05}" for i in range(101, 116))
    last_fixed = max(c.created_at for c in customers if c.id in fixed)
    for customer in customers:
        local = customer.created_at.astimezone(CAIRO)
        if customer.kind == "merchant":
            assert parse_utc("2024-11-01T00:00:00Z") <= customer.created_at < parse_utc("2026-01-01T00:00:00Z")
            assert time(8) <= local.time() < time(22)
        elif customer.id in fixed:
            assert parse_utc("2026-01-01T00:00:00Z") <= customer.created_at < parse_utc("2026-05-01T00:00:00Z")
            assert time(8) <= local.time() < time(22)
        elif customer.id not in first_shipments or customer.created_at != first_shipments[customer.id]:
            assert last_fixed < customer.created_at <= parse_utc("2026-08-01T00:00:00Z")
        else:
            assert customer.created_at == first_shipments[customer.id]
    merchants = sorted((c for c in customers if c.kind == "merchant"), key=lambda c: c.id)
    for earlier, later in zip(merchants, merchants[1:], strict=False):
        assert 3 <= (later.created_at.astimezone(CAIRO).date() - earlier.created_at.astimezone(CAIRO).date()).days <= 30


def test_generated_claim_followups_use_generated_shipments(sample):
    labels = {label.message_id: label for label in sample.tables["message_labels"]}
    for message in sample.tables["messages"]:
        if message.origin == "generated":
            assert not set(labels[message.id].tracking_numbers).intersection(ANCHOR_NUMBERS)


@pytest.mark.parametrize("arrival,limits", [
    ("2026-10-25T07:00:00Z", (480, 2700)),
    ("2026-10-23T21:00:00Z", (0, 8700)),
])
def test_reply_delay_draw_accepts_an_individual_second(arrival, limits):
    class Draw:
        def randint(self, low, high):
            assert (low, high) == limits
            return low + 1
    received = parse_utc(arrival)
    sent = _reply_time(received, Draw())
    if limits[0]:
        assert sent - received == timedelta(seconds=481)
    else:
        assert sent.astimezone(CAIRO).time() == time(8, 5, 1)


def test_each_generated_case_keeps_one_request_time_draw(monkeypatch):
    import bayline.sample.generate as generator
    original = generator._case_times
    draws = []
    def record(*args, **kwargs):
        result = original(*args, **kwargs)
        draws.append(result[0])
        return result
    monkeypatch.setattr(generator, "_case_times", record)
    data = generator.generate()
    cases = [row for table in ("return_cases", "claims") for row in data.tables[table]
             if row.tracking_number not in ANCHOR_NUMBERS]
    assert len(draws) == len(cases) == 89
    assert set(draws) == {row.opened_at for row in cases}


def test_destination_hub_scan_follows_origin_departure_on_a_next_day_delivery():
    from bayline.geography import CITIES
    from bayline.sample.generate import _events

    class Draw:
        def choice(self, values):
            return 15 if 15 in values else values[0]

        def randint(self, low, high):
            return low if (low, high) in ((12, 20), (7, 10)) else high

        def randrange(self, stop):
            return stop - 1

    parcel = shipment(service="express", origin_city="Alexandria", destination_city="Cairo")
    _, scans = _events(parcel, "delivered_on_time", Draw())
    departed = next(at for code, at, place in scans if code == "DEPARTED_HUB")
    destination = next(at for code, at, place in scans
                       if code == "ARRIVED_HUB" and place == CITIES[parcel.destination_city].hub)
    out = next(at for code, at, place in scans if code == "OUT_FOR_DELIVERY")
    assert departed < destination < out
