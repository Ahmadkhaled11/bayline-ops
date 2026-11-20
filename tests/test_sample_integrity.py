"""Customer records and tracking histories must tell the same story."""

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from bayline.business_days import is_business_day
from bayline.geography import CITIES
from bayline.rules.address import check_address_change
from bayline.sample.anchors import ANCHOR_NUMBERS
from bayline.sample.generate import AS_OF, _destination_arrival
from bayline.sample.names import FIRST_NAMES, LAST_NAMES, STAFF


def _histories(sample):
    histories = defaultdict(list)
    for event in sample.tables["tracking_events"]:
        histories[event.tracking_number].append(event)
    return {number: sorted(events, key=lambda event: (event.occurred_at, event.id))
            for number, events in histories.items()}


def test_record_numbers_follow_the_order_records_were_made(sample):
    tables = sample.tables
    for name, field, prefix in (("return_cases", "opened_at", "RET-"),
                                ("claims", "opened_at", "CLM-"),
                                ("address_changes", "requested_at", "ADR-"),
                                ("replies", "sent_at", "REP-"),
                                ("tracking_events", "occurred_at", None),
                                ("messages", "received_at", "M-")):
        rows = tables[name]
        if name == "messages":
            rows = [row for row in rows if row.origin == "generated"]
        rows = sorted(rows, key=lambda row: row.id)
        assert [row.id for row in rows] == [f"{prefix}{i:05}" if prefix else i
                                             for i in range(1, len(rows) + 1)]
        assert [getattr(row, field) for row in rows] == sorted(getattr(row, field) for row in rows)

    shipments = sorted((s for s in tables["shipments"] if s.tracking_number in sample.scenarios),
                       key=lambda s: s.tracking_number)
    assert [s.created_at for s in shipments] == sorted(s.created_at for s in shipments)
    customers = sorted(tables["customers"], key=lambda c: c.id)
    assert [c.kind for c in customers] == ["merchant"] * 20 + ["recipient"] * 280
    assert all(AS_OF - timedelta(days=730) <= c.created_at < AS_OF for c in customers)
    assert all(a.created_at <= b.created_at for a, b in zip(customers, customers[1:], strict=False))
    customer_times = {c.id: c.created_at for c in customers}
    assert all(customer_times[s.merchant_id] < s.created_at and
               customer_times[s.recipient_id] <= s.created_at for s in tables["shipments"])
    messages = {m.id: m for m in tables["messages"]}
    assert {m.id for m in messages.values() if m.origin == "authored"} == {
        f"M-{i:05}" for i in range(1001, 1041)}
    assert {label.message_id for label in tables["message_labels"]} == messages.keys()
    assert all(reply.message_id in messages and messages[reply.message_id].received_at <= reply.sent_at
               for reply in tables["replies"])


def test_recipient_location_and_phone_match_every_shipment(sample):
    customers = {customer.id: customer for customer in sample.tables["customers"]}
    prefixes = {"EG": "+20 100 555 0", "AE": "+971 50 555 0",
                "SA": "+966 50 555 0", "JO": "+962 79 555 0"}
    for shipment in sample.tables["shipments"]:
        recipient = customers[shipment.recipient_id]
        assert recipient.kind == "recipient"
        assert recipient.city == shipment.destination_city, shipment.tracking_number
        assert recipient.country == shipment.destination_country
        assert recipient.phone.startswith(prefixes[shipment.destination_country])


def test_customer_contact_details_are_unique(sample):
    customers = sample.tables["customers"]
    assert len({customer.email.casefold() for customer in customers}) == len(customers)
    assert len({customer.phone for customer in customers}) == len(customers)


def test_customer_contacts_use_names_and_fictional_phone_blocks(sample):
    for customer in sample.tables["customers"]:
        local, domain = customer.email.split("@")
        assert local == customer.name.lower().replace(" ", ".")
        assert domain in ("example.com", "example.net", "example.org")
        prefix = {"EG": "+20 100", "AE": "+971 50", "SA": "+966 50", "JO": "+962 79"}[customer.country]
        assert customer.phone.startswith(prefix + " 555 0")
        assert len(customer.phone.removeprefix(prefix + " 555 0")) == 3


def test_generated_names_use_large_pools_without_fixed_customer_names(sample):
    fixed = [customer for customer in sample.tables["customers"]
             if customer.kind == "recipient" and 101 <= int(customer.id[4:]) <= 115]
    fixed_first = {customer.name.split()[0] for customer in fixed}
    fixed_last = {customer.name.split()[-1] for customer in fixed}
    assert len(set(FIRST_NAMES)) >= 60
    assert len(set(LAST_NAMES)) >= 60
    assert not fixed_first.intersection(FIRST_NAMES)
    assert not fixed_last.intersection(LAST_NAMES)
    assert not {row[1].split()[-1] for row in STAFF}.intersection(LAST_NAMES)
    generated = [customer for customer in sample.tables["customers"]
                 if customer.kind == "recipient" and int(customer.id[4:]) >= 116]
    assert len({customer.name for customer in generated}) == len(generated)
    for customer in generated:
        first, last = customer.name.split()
        assert first in FIRST_NAMES and first not in fixed_first
        assert last in LAST_NAMES and last not in fixed_last


def test_fixed_goods_descriptions_match_customer_messages(sample):
    descriptions = ("jacket", "dress", "smart watch", "phone", "laptop charger", "tablet",
                    "power bank", "coffee table", "wireless headphones", "cotton scarf",
                    "linen trousers", "cotton sweater", "laptop", "two shirts", "dress")
    shipments = {shipment.tracking_number: shipment for shipment in sample.tables["shipments"]}
    for number, description in zip(ANCHOR_NUMBERS, descriptions, strict=True):
        assert shipments[number].goods_description == description


def test_creation_pickup_and_origin_handling_use_origin_hub(sample):
    histories = _histories(sample)
    for shipment in sample.tables["shipments"]:
        history = histories[shipment.tracking_number]
        origin = CITIES[shipment.origin_city].hub
        for event in history:
            if event.code in ("CREATED", "PICKED_UP"):
                assert event.location == origin, (shipment.tracking_number, event.code)
        departures = [event for event in history if event.code == "DEPARTED_HUB"]
        if departures:
            assert departures[0].location == origin
            for event in history:
                if event.code == "ARRIVED_HUB" and event.occurred_at < departures[0].occurred_at:
                    assert event.location == origin
    for number in ANCHOR_NUMBERS[10:12]:
        assert histories[number][-1].code == "ARRIVED_HUB"
        assert histories[number][-1].location == "Cairo Hub"


def test_international_route_uses_export_desk_and_destination_customs(sample):
    histories = _histories(sample)
    for shipment in sample.tables["shipments"]:
        history = histories[shipment.tracking_number]
        if shipment.lane == "international" and any(e.code == "PICKED_UP" for e in history):
            assert any(e.code == "DEPARTED_HUB" and e.location == "Cairo Airport Export Desk"
                       for e in history), shipment.tracking_number
        for event in history:
            if event.code in ("CUSTOMS_HOLD", "CUSTOMS_CLEARED"):
                assert shipment.lane == "international"
                assert event.location == f"{shipment.destination_city} customs"
    held = next(event for event in histories["BYL260467527"] if event.code == "CUSTOMS_HOLD")
    assert held.location == "Riyadh customs"


def test_delivery_scans_name_the_destination_city(sample):
    shipments = {shipment.tracking_number: shipment for shipment in sample.tables["shipments"]}
    for event in sample.tables["tracking_events"]:
        if event.code in ("OUT_FOR_DELIVERY", "DELIVERY_FAILED", "DELIVERED"):
            assert event.location == shipments[event.tracking_number].destination_city


def test_pickups_use_working_days_and_collection_hours(sample):
    pickups = [event for event in sample.tables["tracking_events"] if event.code == "PICKED_UP"]
    local_times = [event.occurred_at.astimezone(ZoneInfo("Africa/Cairo")) for event in pickups]
    assert all(is_business_day(value.date()) for value in local_times)
    assert all(time(8) <= value.time() < time(19) for value in local_times)


def test_each_failed_delivery_has_an_earlier_delivery_round(sample):
    failures = 0
    for number, history in _histories(sample).items():
        for event in history:
            if event.code == "DELIVERY_FAILED":
                failures += 1
                assert any(prior.code == "OUT_FOR_DELIVERY" and prior.occurred_at < event.occurred_at
                           for prior in history), number
    assert failures > 0


def test_staff_replies_are_sent_in_business_desk_hours(sample):
    messages = {message.id: message for message in sample.tables["messages"]}
    for reply in sample.tables["replies"]:
        local = reply.sent_at.astimezone(ZoneInfo("Africa/Cairo"))
        assert is_business_day(local.date()), reply.id
        assert time(8) <= local.time() < time(20), reply.id
        assert messages[reply.message_id].received_at <= reply.sent_at


def test_address_changes_obey_the_rule_and_desk_calendar(sample):
    histories = _histories(sample)
    shipments = {shipment.tracking_number: shipment for shipment in sample.tables["shipments"]}
    changes = sample.tables["address_changes"]
    assert Counter(change.status for change in changes) == {"applied": 6, "refused": 6}
    assert len({change.tracking_number for change in changes}) == 12
    for change in changes:
        local = change.requested_at.astimezone(ZoneInfo("Africa/Cairo"))
        assert is_business_day(local.date())
        assert time(8) <= local.time() < time(20)
        assert change.requested_at < AS_OF
        shipment = shipments[change.tracking_number]
        result = check_address_change(shipment, histories[change.tracking_number],
                                      change.new_city, [], change.requested_at)
        assert result.reason == change.decision_code
        assert result.allowed == (change.status == "applied")
        if result.allowed:
            assert shipment.address_line == change.new_address_line
            assert any(event.code == "ADDRESS_CHANGED" and event.occurred_at == change.requested_at
                       for event in histories[change.tracking_number])


def test_deliveries_use_working_days_and_cases_precede_the_snapshot(sample):
    shipments = {shipment.tracking_number: shipment for shipment in sample.tables["shipments"]}
    days = [event.occurred_at.astimezone(ZoneInfo(shipments[event.tracking_number].destination_tz)).date()
            for event in sample.tables["tracking_events"]
            if event.code == "DELIVERED" and event.tracking_number in sample.scenarios]
    assert all(is_business_day(day) for day in days)
    assert all(case.opened_at <= AS_OF for table in ("return_cases", "claims")
               for case in sample.tables[table])


def test_destination_arrival_respects_departure_and_delivery_round():
    departed = datetime(2026, 8, 1, 18, 0, tzinfo=ZoneInfo("UTC"))
    final = datetime(2026, 8, 2, 16, 0, tzinfo=ZoneInfo("UTC"))
    round_start = datetime(2026, 8, 2, 8, 0, tzinfo=ZoneInfo("UTC"))

    usual = _destination_arrival(departed, round_start, final, 12, 30)
    assert usual == final - timedelta(hours=12, minutes=30)

    late_final = final + timedelta(hours=4)
    after_round = _destination_arrival(departed, round_start, late_final, 10, 0)
    assert departed + timedelta(hours=2) <= after_round < round_start
    assert late_final - timedelta(hours=10) >= round_start

    late_departure = datetime(2026, 8, 2, 4, 30, tzinfo=ZoneInfo("UTC"))
    short_journey = _destination_arrival(late_departure, round_start, final, 10, 0)
    assert final - timedelta(hours=10) < late_departure + timedelta(hours=2)
    assert late_departure + timedelta(hours=2) <= short_journey < round_start

    close_departure = round_start - timedelta(hours=1)
    close_arrival = _destination_arrival(close_departure, round_start, final, 10, 0)
    assert close_departure < close_arrival < round_start


def test_destination_hub_arrival_precedes_delivery_round(sample):
    for number, history in _histories(sample).items():
        first_hub = next((event.location for event in history if event.code == "ARRIVED_HUB"), None)
        arrivals = [event for event in history
                    if event.code == "ARRIVED_HUB" and event.location != first_hub]
        rounds = [event for event in history if event.code == "OUT_FOR_DELIVERY"]
        if not arrivals or not rounds:
            continue
        departure = next(event for event in history
                         if event.code == "DEPARTED_HUB" and event.location == first_hub)
        for arrival in arrivals:
            assert departure.occurred_at + timedelta(hours=2) <= arrival.occurred_at, number
            assert arrival.occurred_at < rounds[0].occurred_at, number
