import json
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bayline.db import connect
from bayline.rules.address import check_address_change
from bayline.rules.claims import check_claim
from bayline.rules.delays import classify_delay
from bayline.rules.pricing import shipping_fee
from bayline.rules.returns import check_return
from bayline.sample.anchors import ANCHOR_NUMBERS
from bayline.sample.authored import load_authored, validate_labels
from bayline.sample.generate import AS_OF, SCENARIOS, generate
from bayline.sample.load import checksum, seed_database
from bayline.timeutil import parse_utc
from bayline.tracking_numbers import is_valid


def maps(sample):
    tables = sample.tables
    shipments = {s.tracking_number: s for s in tables["shipments"]}
    customers = {c.id: c for c in tables["customers"]}
    events = {tn: [] for tn in shipments}
    for e in tables["tracking_events"]:
        events[e.tracking_number].append(e)
    return shipments, customers, events


def test_counts(sample):
    for table, count in {"meta": 3, "staff": 9, "customers": 300, "shipments": 400,
        "return_cases": 60, "claims": 31, "address_changes": 12, "messages": 240,
        "message_labels": 240, "replies": 140, "documents": 60}.items():
        assert len(sample.tables[table]) == count, table
    assert sum(c.kind == "merchant" for c in sample.tables["customers"]) == 20
    assert sum(c.returns_plan for c in sample.tables["customers"]) == 14
    assert Counter(r.status for r in sample.tables["return_cases"]) == dict(approved=30, refused=15, open=10, received=5)
    assert Counter(c.kind for c in sample.tables["claims"]) == dict(damage=14, loss=6, delay=11)
    assert Counter(sample.scenarios.values()) == {s: count for s, (count, _) in SCENARIOS.items()}


def test_scenarios_and_prices(sample):
    shipments, _, events = maps(sample)
    for tn, scenario in sample.scenarios.items():
        s = shipments[tn]
        assert classify_delay(s, events[tn], AS_OF).delay_class == SCENARIOS[scenario][1], (tn, scenario)
    for tn, s in shipments.items():
        assert is_valid(tn)
        assert s.shipping_fee_piastres == shipping_fee(s.lane, s.service, s.weight_kg, s.insured, s.declared_value_piastres)


def test_events_and_dates(sample):
    shipments, _, events = maps(sample)
    for tn, history in events.items():
        assert history == sorted(history, key=lambda e: (e.occurred_at, e.id))
        assert all(shipments[tn].created_at <= e.occurred_at <= AS_OF for e in history)
        for e in history:
            local = e.occurred_at.astimezone(ZoneInfo(shipments[tn].destination_tz))
            if e.code == "PICKED_UP":
                assert parse_utc("2026-08-02T00:00:00Z") <= e.occurred_at <= parse_utc("2026-10-30T23:59:59Z")
            if e.code == "OUT_FOR_DELIVERY":
                assert 7 <= local.hour < 21
            if e.code == "DELIVERED":
                assert 9 <= local.hour < 21 and local.weekday() != 4
        if sample.scenarios.get(tn) == "out_for_delivery":
            assert parse_utc("2026-11-02T05:00:00Z") <= history[-1].occurred_at < parse_utc("2026-11-02T07:00:00Z")


def test_stored_decisions(sample):
    shipments, customers, events = maps(sample)
    for row in sample.tables["return_cases"]:
        s = shipments[row.tracking_number]
        prior = [r for r in sample.tables["return_cases"] if r.id != row.id and r.opened_at <= row.opened_at]
        result = check_return(s, events[s.tracking_number], customers[s.merchant_id], prior, row.opened_at)
        assert result.reason == row.decision_code
        assert result.allowed == (row.status != "refused")
    for row in sample.tables["claims"]:
        s = shipments[row.tracking_number]
        prior = [c for c in sample.tables["claims"] if c.id != row.id and c.opened_at <= row.opened_at]
        result = check_claim(s, events[s.tracking_number], row.kind, row.claimed_piastres, prior, row.opened_at)
        assert (result.reason, result.payable_piastres) == (row.decision_code, row.payable_piastres)
        assert result.eligible == (row.status != "refused")
    for row in sample.tables["address_changes"]:
        s = shipments[row.tracking_number]
        prior = [c for c in sample.tables["address_changes"] if c.id != row.id and c.requested_at <= row.requested_at]
        assert check_address_change(s, events[s.tracking_number], row.new_city, prior, row.requested_at).reason == row.decision_code
    assert not any(r.tracking_number in ANCHOR_NUMBERS for r in sample.tables["address_changes"])
    fixed_claims = [r for r in sample.tables["claims"] if r.tracking_number in ANCHOR_NUMBERS]
    assert len(fixed_claims) == 1
    assert fixed_claims[0].id == "CLM-00016"
    assert fixed_claims[0].tracking_number == "BYL260442157"
    assert (fixed_claims[0].kind, fixed_claims[0].status, fixed_claims[0].decision_code,
            fixed_claims[0].payable_piastres) == ("delay", "refused", "NOT_LATE_ENOUGH", 0)
    assert parse_utc("2026-10-07T12:00:00Z") < fixed_claims[0].opened_at == fixed_claims[0].decided_at
    assert parse_utc("2026-10-08T05:00:00Z") <= fixed_claims[0].decided_at < parse_utc("2026-10-08T09:10:00Z")
    assert fixed_claims[0].decided_by in ("karim.nassar", "dina.fawzy", "omar.elbanna")
    anchor_cases = [r for r in sample.tables["return_cases"] if r.tracking_number in ANCHOR_NUMBERS]
    assert len(anchor_cases) == 1
    assert anchor_cases[0].tracking_number == "BYL260473640"
    assert anchor_cases[0].opened_at == parse_utc("2026-10-22T08:00:00Z")
    assert anchor_cases[0].status == "open"
    cited = {m.id for m in sample.tables["messages"] if anchor_cases[0].id in m.body}
    assert cited == {"M-01024", "M-01028"}


@pytest.mark.parametrize("index,at,reason,day", [
    (0, "2026-10-24T19:40:00Z", "ALLOWED", 30), (1, "2026-10-24T06:15:00Z", "WINDOW_CLOSED", 31),
    (2, "2026-10-31T20:30:00Z", "WINDOW_CLOSED", 31), (6, "2026-10-22T09:00:00Z", "CATEGORY_EXCLUDED", 2),
    (7, "2026-10-21T10:00:00Z", "MERCHANT_NOT_ON_PLAN", 3), (8, "2026-10-26T07:00:00Z", "ALLOWED", 14),
    (14, "2026-10-27T09:00:00Z", "ALREADY_OPEN", 7),
])
def test_anchor_returns(sample, index, at, reason, day):
    shipments, customers, events = maps(sample)
    s = shipments[ANCHOR_NUMBERS[index]]
    result = check_return(s, events[s.tracking_number], customers[s.merchant_id], sample.tables["return_cases"], parse_utc(at))
    assert (result.reason, result.day_number) == (reason, day)


def test_anchor_other_outcomes(sample):
    shipments, _, events = maps(sample)
    for index, promised, delay, late in [(3, "2026-10-07", "on_time", 0), (4, "2026-10-12", "late", 1),
        (5, "2026-10-19", "on_time", 0), (10, "2026-11-03", "on_time", 0), (12, "2026-10-28", "very_late", 3)]:
        s = shipments[ANCHOR_NUMBERS[index]]
        d = classify_delay(s, events[s.tracking_number], AS_OF)
        assert (d.promised.isoformat(), d.delay_class, d.late_business_days) == (promised, delay, late)
    for index, at, city, reason in [(9, "2026-11-02T06:45:00Z", "Cairo", "TOO_LATE"),
        (10, "2026-10-31T12:00:00Z", "Cairo", "ALLOWED"), (11, "2026-10-31T13:00:00Z", "Giza", "DIFFERENT_CITY"),
        (12, "2026-11-02T07:00:00Z", "Riyadh", "CUSTOMS_HOLD")]:
        s = shipments[ANCHOR_NUMBERS[index]]
        assert check_address_change(s, events[s.tracking_number], city, [], parse_utc(at)).reason == reason
    for index, kind, amount, at, reason, payable in [
        (3, "delay", 0, "2026-10-08T08:00:00Z", "NOT_LATE_ENOUGH", 0),
        (4, "delay", 0, "2026-10-14T08:00:00Z", "ELIGIBLE", 7500),
        (4, "delay", 0, "2026-11-02T07:00:00Z", "WINDOW_CLOSED", 0),
        (8, "damage", 850000, "2026-10-26T07:00:00Z", "ELIGIBLE", 300000),
        (13, "loss", 120000, "2026-11-02T07:00:00Z", "ELIGIBLE", 124500)]:
        s = shipments[ANCHOR_NUMBERS[index]]
        result = check_claim(s, events[s.tracking_number], kind, amount, [], parse_utc(at))
        assert (result.reason, result.payable_piastres) == (reason, payable)


def test_message_truth_and_mix(sample):
    shipments, customers, events = maps(sample)
    emails = {c.email: c.id for c in customers.values()}
    labels = {x.message_id: x for x in sample.tables["message_labels"]}
    generated = [m for m in sample.tables["messages"] if m.origin == "generated"]
    for m in sample.tables["messages"]:
        label = asdict(labels[m.id])
        label.pop("message_id")
        for key in ("topics", "tracking_numbers", "invalid_tracking_mentions", "missing"):
            label[key] = list(label[key])
        validate_labels(label, m.body, shipments)
        assert m.customer_id == emails.get(m.from_email.lower())
        assert parse_utc("2026-09-01T00:00:00Z") <= m.received_at <= AS_OF
        for tn in label["tracking_numbers"]:
            assert shipments[tn].created_at <= m.received_at
            if set(label["topics"]) & {"return", "damage"}:
                assert any(e.code == "DELIVERED" and e.occurred_at <= m.received_at for e in events[tn])
    assert Counter(labels[m.id].primary_topic for m in generated) == {"status_question": 50, "delay": 40, "return": 40, "damage": 30, "address_change": 20, "claim_followup": 10, "other": 10}
    assert sum(len(labels[m.id].topics) == 2 for m in generated) == 30
    assert sum("tracking_number" in labels[m.id].missing for m in generated) == 25
    assert sum(bool(labels[m.id].invalid_tracking_mentions) for m in generated) == 8
    assert sum(m.customer_id is None for m in generated) == 15
    assert Counter(m.status for m in generated) == {"new": 60, "answered": 70, "closed": 70}
    replies = Counter(r.message_id for r in sample.tables["replies"])
    assert all(replies[m.id] == (m.status != "new") for m in generated)
    authored = [labels[m.id] for m in sample.tables["messages"] if m.origin == "authored"]
    assert sum(bool(x.missing) for x in authored) >= 6
    assert sum(len(x.topics) >= 2 for x in authored) >= 6
    assert sum(bool(x.invalid_tracking_mentions) for x in authored) == 4
    assert sum(x.contains_instructions for x in authored) == 3
    assert sum(x.escalation == "legal_threat" for x in authored) == 3
    assert sum(x.escalation == "abusive" for x in authored) == 1
    assert sum(x.primary_topic == "address_change" for x in authored) == 3
    assert sum(x.primary_topic == "other" for x in authored) == 2


def test_documents(sample):
    from bayline.money import egp_to_piastres, format_egp

    shipments, _, _ = maps(sample)
    assert Counter(d.kind for d in sample.tables["documents"]) == {"waybill": 40, "commercial_invoice": 20}
    assert {d.layout for d in sample.tables["documents"]} == {"a", "b", "c"}
    for d in sample.tables["documents"]:
        s = shipments[d.tracking_number]
        assert s.tracking_number in d.body and s.address_line in d.body
        assert format_egp(s.declared_value_piastres) in d.body
        if d.kind == "commercial_invoice":
            assert s.lane == "international"
            amounts = [egp_to_piastres(line.split(": ")[1].replace(" EGP", "").replace(",", ""))
                       for line in d.body.splitlines() if line.startswith("Item ")]
            assert sum(amounts) == s.declared_value_piastres


def test_checksum_and_force(tmp_path, seeded_db):
    second = tmp_path / "second.db"
    seed_database(second)
    with connect(seeded_db) as a, connect(second) as b:
        expected = Path(__file__).with_name("fixtures").joinpath("sample_checksum.txt").read_text().strip()
        assert checksum(a) == checksum(b) == expected
    with pytest.raises(FileExistsError):
        seed_database(second)
    seed_database(second, force=True)
    with connect(second) as conn:
        assert checksum(conn) == expected


@pytest.mark.parametrize("mutation", ["broken_json", "bad_id", "bad_label", "too_early", "bad_email"])
def test_authored_failure_reports_line(sample, tmp_path, mutation):
    from bayline.config import ROOT

    lines = (ROOT / "data/authored/messages.jsonl").read_text().splitlines()
    row = json.loads(lines[1])
    if mutation == "bad_id":
        row["id"] = "M-99999"
    elif mutation == "bad_label":
        row["labels"]["tracking_numbers"] = ["BYL260480009"]
    elif mutation == "too_early":
        row["received_at"] = "2026-08-01T00:00:00Z"
    elif mutation == "bad_email":
        row["from_email"] = "missing-domain"
    lines[1] = "{" if mutation == "broken_json" else json.dumps(row)
    path = tmp_path / "messages.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        load_authored(path, sample.tables["shipments"], sample.tables["tracking_events"], sample.tables["customers"], AS_OF)


def test_another_seed_changes_data():
    a, b = generate(7), generate(8)
    assert len(a.tables["shipments"]) == len(b.tables["shipments"]) == 400
    assert a.tables["shipments"] != b.tables["shipments"]


def test_reply_times(sample):
    messages = {m.id: m for m in sample.tables["messages"]}
    for reply in sample.tables["replies"]:
        assert messages[reply.message_id].received_at <= reply.sent_at <= AS_OF
        from bayline.business_days import add_business_days
        local = messages[reply.message_id].received_at.astimezone(ZoneInfo("Africa/Cairo"))
        assert reply.sent_at.astimezone(ZoneInfo("Africa/Cairo")).date() <= add_business_days(local.date(), 1)


def test_failed_reseed_preserves_existing_database(tmp_path):
    path = tmp_path / "stable.db"
    seed_database(path)
    before = path.read_bytes()
    broken = tmp_path / "broken.jsonl"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        seed_database(path, force=True, authored_path=broken)
    assert path.read_bytes() == before
    assert not path.with_name(path.name + ".building").exists()


def test_generated_replies_agree_with_checks(sample):
    import re

    from bayline.business_days import is_business_day
    from bayline.money import format_egp
    from bayline.rules.claims import liability_cap
    from bayline.status import current_status, events_at
    from bayline.timeutil import format_day, local_date

    shipments, customers, events = maps(sample)
    messages = {m.id: m for m in sample.tables["messages"]}
    labels = {label.message_id: label for label in sample.tables["message_labels"]}
    day_pattern = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) \d{1,2} [A-Z][a-z]+ \d{4}"
    other_answers = {
        "what are your desk hours": "Our desk is open Sunday to Thursday, 08:00 to 20:00 Cairo time. We are closed on Friday, Saturday and public holidays.",
        "how do i contact the desk": "You can reach the desk by replying to this email, or through the contact form. We answer Sunday to Thursday, 08:00 to 20:00 Cairo time.",
        "please explain what a waybill means": "A waybill is the record that travels with a parcel. It shows the tracking number, the sender, the recipient and the delivery address.",
        "i need help reading my parcel record": "Each line in a parcel record is one scan: where the parcel was, and when. The newest line is its latest position. If one line is unclear, reply and tell us which one.",
    }
    for reply in sample.tables["replies"]:
        m, label = messages[reply.message_id], labels[reply.message_id]
        context = (reply.id, m.id, reply.body)
        assert reply.body.startswith(f"Hello {m.from_name.split()[0]},\n\n"), context
        assert reply.body.endswith("\nBayline Cargo Customer Service"), context
        assert not any(word in reply.body for word in ("WINDOW_CLOSED", "lost_suspected", "ALREADY_OPEN", "ELIGIBLE")), context
        assert not any(promise in reply.body.lower() for promise in (
            "payable", "we will pay", "we will refund", "you will receive", "you will get")), context
        assert "0 business days" not in reply.body and "1 business days" not in reply.body, context
        assert reply.body.isascii(), context
        desk_time = reply.sent_at.astimezone(ZoneInfo("Africa/Cairo"))
        assert is_business_day(desk_time.date()) and 8 <= desk_time.hour < 20, context
        topics = [label.primary_topic, *(t for t in label.topics if t != label.primary_topic)]
        if not label.tracking_numbers:
            topics = [*(t for i, t in enumerate(topics) if t == "other" or not any(p != "other" for p in topics[:i]))]
        elif "delay" in topics and "status_question" in topics:
            topics.remove("status_question" if topics[0] == "delay" else "delay")
        content = reply.body.split("\n\n")[1:-1]
        if len(topics) > 1:
            assert len(content) == len(topics), context
            paragraphs = content
        else:
            assert 1 <= len(content) <= 2, context
            paragraphs = [" ".join(content)]
        for topic, paragraph in zip(topics, paragraphs, strict=True):
            expected_dates = set()
            allowed_numbers = set()
            if topic == "other":
                matching = [answer for question, answer in other_answers.items() if question in m.body.lower()]
                assert len(matching) == 1 and paragraph == matching[0], context
                assert "BYL" not in paragraph, context
                continue
            if not label.tracking_numbers:
                from bayline.sample.texts import TRACKING_REQUESTS
                if label.invalid_tracking_mentions:
                    assert paragraph == (f"The number you sent, {label.invalid_tracking_mentions[0]}, is not a valid Bayline tracking number. "
                        "One of the digits may be wrong. Please copy the number again from the merchant's email and reply with it."), context
                else:
                    assert paragraph in TRACKING_REQUESTS, context
                continue
            s = shipments[label.tracking_numbers[0]]
            assert s.tracking_number in paragraph, context
            damage_window = check_claim(s, events[s.tracking_number], "damage",
                max(100, s.declared_value_piastres), [], reply.sent_at)
            if damage_window.reason == "WINDOW_CLOSED":
                assert "photos" not in reply.body.lower(), context
            history = events_at(events[s.tracking_number], reply.sent_at)
            delivered = [e for e in history if e.code == "DELIVERED"]
            today = local_date(reply.sent_at, s.destination_tz)
            date = format_day(today)
            delivery_date = local_date(delivered[-1].occurred_at, s.destination_tz) if delivered else None
            if topic == "return":
                d = check_return(s, history, customers[s.merchant_id], sample.tables["return_cases"], reply.sent_at)
                answers = {"ALLOWED": "can still be returned", "NOT_DELIVERED": "cannot open a return",
                    "MERCHANT_NOT_ON_PLAN": "cannot take", "CATEGORY_EXCLUDED": "goods in",
                    "ALREADY_OPEN": "Return RET-", "WINDOW_CLOSED": "can no longer accept a return"}
                assert answers[d.reason] in paragraph, context
                if d.reason in ("ALLOWED", "WINDOW_CLOSED"):
                    expected_dates.update((date, format_day(delivery_date), format_day(d.last_day)))
                    allowed_numbers.update((str(d.day_number), "30"))
                    if d.day_number == 0:
                        expected_dates.discard(date)
                        expected_dates.add(format_day(delivery_date))
                        assert "so the 30 days have only just started." in paragraph and "day 0" not in paragraph, context
                    else:
                        assert f"day {d.day_number} of 30" in paragraph, context
                    assert f"It was delivered on {format_day(delivery_date)}" in paragraph, context
                    tense = "is" if d.allowed else "was"
                    assert f"The last day for a return {tense} {format_day(d.last_day)}" in paragraph, context
                    if not d.allowed:
                        assert "contact the merchant" in paragraph, context
                elif d.reason == "NOT_DELIVERED":
                    expected_dates.add(date)
                    assert "no delivery scan as of" in paragraph and ("once the parcel has arrived" in paragraph or "Once it is delivered" in paragraph), context
                elif d.reason == "MERCHANT_NOT_ON_PLAN":
                    assert "not on the Bayline Returns plan" in paragraph and "merchant" in paragraph, context
                elif d.reason == "CATEGORY_EXCLUDED":
                    assert "Perishable goods, batteries and hazardous goods cannot be returned." in paragraph, context
                else:
                    case = next(r for r in sample.tables["return_cases"] if r.tracking_number == s.tracking_number
                                and r.opened_at <= reply.sent_at and r.status != "refused")
                    expected_dates.add(format_day(local_date(case.opened_at, s.destination_tz)))
                    allowed_numbers.add(case.id[4:])
                    status = "open" if case.decided_at is None or case.decided_at > reply.sent_at else case.status
                    if status == "open":
                        assert "only one open return at a time" in paragraph and "collection" in paragraph, context
                    elif status == "approved":
                        assert "has been approved" in paragraph and "Please quote the return number" in paragraph, context
                    else:
                        assert "parcel has come back to us" in paragraph and "reply and quote the return number" in paragraph, context
            elif topic == "damage":
                d = check_claim(s, history, "damage", max(100, s.declared_value_piastres), sample.tables["claims"], reply.sent_at)
                answers = {"ELIGIBLE": "within our time limit", "INVALID_AMOUNT": "need the amount you are claiming",
                    "ALREADY_EXISTS": "We already have a damage claim", "NOT_DELIVERED": "cannot take a damage claim",
                    "WINDOW_CLOSED": "can no longer accept a damage claim"}
                assert answers[d.reason] in paragraph, context
                if d.reason in ("ELIGIBLE", "WINDOW_CLOSED"):
                    expected_dates.update((date, format_day(delivery_date)))
                    day = (today - delivery_date).days
                    allowed_numbers.update((str(day), "14"))
                    assert f"The parcel was delivered on {format_day(delivery_date)}" in paragraph, context
                    if d.eligible:
                        cap = liability_cap(s)
                        policy_cap = liability_cap(replace(s, insured=False, declared_value_piastres=10**12))
                        limit_sentence = (f"The shipment was insured, so the most we can pay is its declared value, {format_egp(cap)}."
                            if s.insured else f"The shipment was not insured. The most we can pay is its declared value, {format_egp(s.declared_value_piastres)}."
                            if s.declared_value_piastres < policy_cap else f"The shipment was not insured, so the most we can pay is {format_egp(cap)}.")
                        assert limit_sentence in paragraph, context
                        assert ("was insured" if s.insured else "was not insured") in paragraph, context
                        if day == 0:
                            expected_dates.discard(date)
                            expected_dates.add(format_day(delivery_date))
                            assert "so the 14 days allowed have only just started." in paragraph and "day 0" not in paragraph, context
                        else:
                            assert f"day {day} of the 14 days allowed" in paragraph, context
                        assert d.payable_piastres <= cap, context
                        assert "photos" in paragraph and ("decision" in paragraph or "decide" in paragraph), context
                        allowed_numbers.update(re.findall(r"\d[\d,]*(?:\.\d+)?", format_egp(cap)))
                    else:
                        assert f"day {day} after delivery" in paragraph and "within 14 calendar days" in paragraph, context
                        assert "photos" not in paragraph.lower() and "most we can pay" not in paragraph, context
                        assert "photos" not in reply.body.lower(), context
                elif d.reason == "NOT_DELIVERED":
                    expected_dates.add(date)
                    allowed_numbers.add("14")
                    assert "no delivery scan as of" in paragraph and "within 14 days of delivery" in paragraph, context
                elif d.reason == "ALREADY_EXISTS":
                    assert "one damage claim for each shipment" in paragraph, context
                    assert "send it again" in paragraph or "claim number from our earlier email" in paragraph, context
                else:
                    assert "must state the value of the damage" in paragraph and "amount in EGP" in paragraph, context
            elif topic == "address_change":
                d = check_address_change(s, history, s.destination_city, sample.tables["address_changes"], reply.sent_at)
                answers = {"ALLOWED": "can still be changed, within", "TOO_LATE": "cannot change the address",
                    "CUSTOMS_HOLD": "while it is held at customs", "ALREADY_CHANGED": "already been changed once",
                    "DIFFERENT_CITY": "to another city"}
                assert answers[d.reason] in paragraph, context
                if d.allowed:
                    assert s.destination_city in paragraph and "not gone out for delivery" in paragraph, context
                    assert "new address" in paragraph or "new street address" in paragraph, context
                else:
                    assert not any(request in paragraph.lower() for request in (
                        "reply with the", "send us the new", "confirm the new address", "full new address")), context
                    if d.reason == "TOO_LATE":
                        assert "this one has passed that point" in paragraph, context
                    elif d.reason == "CUSTOMS_HOLD":
                        assert "once" in paragraph.lower() and "released" in paragraph, context
                    elif d.reason == "ALREADY_CHANGED":
                        assert "An address can be changed once per shipment." in paragraph, context
                    else:
                        assert s.destination_city in paragraph and "only within the same city" in paragraph, context
            elif topic in ("delay", "status_question"):
                d = classify_delay(s, history, reply.sent_at)
                scans = [e for e in history if e.code != "ADDRESS_CHANGED"]
                scan_day = format_day(local_date(scans[-1].occurred_at, s.destination_tz)) if scans else None
                status = current_status(history)
                if status == "delivered":
                    expected_dates.update((format_day(delivery_date), format_day(d.promised)))
                    assert f"was delivered in {s.destination_city} on {format_day(delivery_date)}" in paragraph, context
                    assert f"Its promised date was {format_day(d.promised)}" in paragraph, context
                    assert "next scan" not in paragraph.lower() and "for an update" not in paragraph.lower(), context
                    if not d.late_business_days:
                        assert "arrived on time" in paragraph, context
                    else:
                        days = "business day" if d.late_business_days == 1 else "business days"
                        assert f"arrived {d.late_business_days} {days} late" in paragraph, context
                        allowed_numbers.add(str(d.late_business_days))
                elif status == "customs_hold":
                    hold = [e for e in history if e.code == "CUSTOMS_HOLD"][-1]
                    expected_dates.update((format_day(local_date(hold.occurred_at, s.destination_tz)), format_day(d.promised)))
                    assert "is held at customs" in paragraph and "cannot give you a new date" in paragraph, context
                    assert f"It has been there since {format_day(local_date(hold.occurred_at, s.destination_tz))}" in paragraph, context
                elif d.delay_class == "not_started":
                    expected_dates.add(date)
                    assert "not been picked up from the merchant yet" in paragraph and "cannot give a delivery date yet" in paragraph, context
                elif d.delay_class == "returned":
                    expected_dates.add(scan_day)
                    assert "on its way back to the sender" in paragraph and "contact the merchant about a new delivery" in paragraph, context
                elif d.delay_class == "lost_suspected":
                    expected_dates.add(scan_day)
                    allowed_numbers.add("7")
                    assert "may be lost" in paragraph and "no tracking scan for 7 days" in paragraph, context
                    assert "search for it" in paragraph, context
                elif status in ("out_for_delivery", "delivery_failed"):
                    expected_dates.update((format_day(d.promised), scan_day))
                    if status == "out_for_delivery":
                        assert paragraph.startswith(f"Your parcel {s.tracking_number} went out for delivery in {s.destination_city} on {scan_day}."), context
                        assert "Please make sure that someone can receive it." in paragraph, context
                        if d.late_business_days:
                            allowed_numbers.add(str(d.late_business_days))
                            days = "business day" if d.late_business_days == 1 else "business days"
                            assert f"so it is {d.late_business_days} {days} late. We are sorry for the delay." in paragraph, context
                    else:
                        assert paragraph.startswith(f"We tried to deliver your parcel {s.tracking_number} in {s.destination_city} on {scan_day}, and the delivery did not succeed."), context
                        assert f"send us a corrected address in {s.destination_city}" in paragraph, context
                    tense = "is" if d.promised >= today else "was"
                    assert f"Its promised date {tense} {format_day(d.promised)}" in paragraph, context
                else:
                    expected_dates.update((format_day(d.promised), scan_day))
                    if d.delay_class == "on_time":
                        assert "is on schedule" in paragraph, context
                    elif d.delay_class == "at_risk":
                        assert "may arrive after its promised date" in paragraph and "check tracking again after" in paragraph, context
                    else:
                        allowed_numbers.add(str(d.late_business_days))
                        days = "business day" if d.late_business_days == 1 else "business days"
                        assert f"{d.late_business_days} {days} late" in paragraph, context
                        if d.delay_class == "late":
                            expected_dates.add(date)
                            assert "asked the delivery team to check it" in paragraph, context
                        else:
                            assert "asked the delivery team to find it" in paragraph, context
                if status != "delivered" and d.delay_class != "not_started":
                    assert scans[-1].location in paragraph, context
                if d.promised and status != "delivered" and (status == "customs_hold" or d.delay_class == "on_time"):
                    tense = "is" if d.promised >= today else "was"
                    assert f"Its promised date {tense} {format_day(d.promised)}" in paragraph, context
            else:
                claims = [c for c in sample.tables["claims"] if c.tracking_number == s.tracking_number and c.opened_at <= reply.sent_at]
                if not claims:
                    assert paragraph == (f"We have no claim on record for {s.tracking_number}. "
                        "If you sent one, please reply with the date you sent it. To open a claim now, reply and tell us what happened to the parcel."), context
                elif len(claims) > 1:
                    assert paragraph == (f"We need your claim number to check the claim for {s.tracking_number}. "
                        "This shipment has more than one claim, so the tracking number alone is not enough. "
                        "Please reply with the claim number from our earlier email. It starts with CLM."), context
                else:
                    claim = claims[0]
                    opened_day = format_day(local_date(claim.opened_at, s.destination_tz))
                    expected_dates.add(opened_day)
                    allowed_numbers.add(claim.id[4:])
                    status = "open" if claim.decided_at is None or claim.decided_at > reply.sent_at else claim.status
                    details = {
                        "open": "It is still with the claims team. You do not need to do anything. The claims team will write to you with the decision.",
                        "approved": "Our records show it as approved. The claims team will write to you about the next step.",
                        "paid": "Our records show it as paid. If anything about it is unclear, reply and we will check.",
                        "refused": "It was refused. If you think the decision is wrong, reply and tell us why, and we will pass it to the claims team.",
                    }
                    if status == "refused":
                        from bayline.sample.texts import _refused_claim_reason
                        reason = _refused_claim_reason(claim, s, events[s.tracking_number])
                        details["refused"] = reason + " If you think the decision is wrong, reply and tell us why, and we will pass it to the claims team."
                        if claim.kind == "delay" and claim.decision_code == "NOT_LATE_ENOUGH":
                            expected_dates.update((format_day(delivery_date), format_day(classify_delay(s, history, claim.opened_at).promised)))
                        if claim.decision_code == "WINDOW_CLOSED":
                            allowed_numbers.add("14")
                        if claim.kind == "loss" and claim.decision_code == "NOT_LATE_ENOUGH":
                            allowed_numbers.add("10")
                        if claim.decision_code == "INVALID_AMOUNT":
                            allowed_numbers.add("0")
                    assert paragraph == f"Your claim {claim.id} for {s.tracking_number} was opened on {opened_day}. " + details[status], context
            assert set(re.findall(day_pattern, paragraph)) == expected_dates, context
            without_dates = re.sub(day_pattern, "", paragraph).replace(s.tracking_number, "")
            assert set(re.findall(r"\d[\d,]*(?:\.\d+)?", without_dates)) <= allowed_numbers, context


@pytest.mark.parametrize("variant", range(4))
@pytest.mark.parametrize("has_number", [True, False])
def test_general_questions_receive_the_matching_answer(sample, variant, has_number):
    from bayline.sample.texts import render_message, render_reply

    s = sample.tables["shipments"][0]
    question = render_message("other", s.tracking_number, variant)
    assert f"? {s.tracking_number}" not in question
    assert f". {s.tracking_number}" not in question
    response = render_reply("other", None, customer_name="Nadia Farouk", shipment=s,
        events=[], at=AS_OF, variant=variant, has_number=has_number)
    phrases = ("We are closed on Friday", "through the contact form", "record that travels with a parcel", "Each line in a parcel record")
    assert phrases[variant] in response
    assert all(phrase not in response for i, phrase in enumerate(phrases) if i != variant)
    assert "valid tracking number" not in response


@pytest.mark.parametrize("variant", range(4))
@pytest.mark.parametrize("include_damage_question", [False, True])
def test_closed_damage_claim_does_not_ask_for_photos_with_excluded_return(sample, variant, include_damage_question):
    from bayline.sample.texts import render_reply

    shipments, customers, events = maps(sample)
    s = shipments[ANCHOR_NUMBERS[6]]
    at = parse_utc("2026-11-05T10:00:00Z")
    returned = check_return(s, events[s.tracking_number], customers[s.merchant_id], [], at)
    damaged = check_claim(s, events[s.tracking_number], "damage", 50000, [], at)
    assert returned.reason == "CATEGORY_EXCLUDED" and damaged.reason == "WINDOW_CLOSED"
    reply = render_reply("return", returned, customer_name="Salma Youssef", shipment=s,
        events=events[s.tracking_number], at=at, variant=variant,
        secondary=[("damage", damaged)] if include_damage_question else [])
    assert "photos" not in reply.lower()
    assert "Please contact the merchant if there is a problem with the item." in reply
    paragraphs = reply.split("\n\n")
    assert len(paragraphs) == 4
    assert "cannot be returned" in paragraphs[1]
    if include_damage_question:
        assert "We can no longer accept a damage claim" in paragraphs[2]
    else:
        assert "damage claim" not in reply
        assert paragraphs[2] == "Please contact the merchant if there is a problem with the item."


@pytest.mark.parametrize("variant", range(4))
@pytest.mark.parametrize("index,reason", [(9, "TOO_LATE"), (12, "CUSTOMS_HOLD")])
def test_refused_address_reply_uses_the_decisions_next_step(sample, variant, index, reason):
    from bayline.sample.texts import render_reply

    shipments, _, events = maps(sample)
    s = shipments[ANCHOR_NUMBERS[index]]
    decision = check_address_change(s, events[s.tracking_number], s.destination_city, [], AS_OF)
    assert decision.reason == reason
    reply = render_reply("address_change", decision, customer_name="Nadia Farouk", shipment=s,
        events=events[s.tracking_number], at=AS_OF, variant=variant)
    assert not any(request in reply.lower() for request in (
        "reply with the new address", "send us the new", "confirm the new address", "full new address"))
    if reason == "CUSTOMS_HOLD":
        assert "released" in reply
    else:
        assert "this one has passed that point" in reply
