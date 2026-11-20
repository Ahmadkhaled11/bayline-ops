"""Build a stable snapshot of the parcel queue and its handling history."""

import random
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..business_days import add_business_days, is_business_day
from ..config import ROOT
from ..geography import CITIES
from ..models import (
    AddressChange,
    Claim,
    Customer,
    Document,
    EventCode,
    Message,
    MessageLabel,
    Meta,
    Reply,
    ReturnCase,
    Shipment,
    Staff,
    TrackingEvent,
)
from ..money import format_egp
from ..rules.address import check_address_change
from ..rules.claims import check_claim
from ..rules.delays import classify_delay, promised_date
from ..rules.pricing import shipping_fee
from ..rules.returns import check_return
from ..timeutil import parse_utc
from ..tracking_numbers import make_tracking_number
from .anchors import anchor_claims, anchor_customers, anchor_shipments
from .authored import load_authored, validate_labels
from .catalog import MERCHANT_PRODUCTS, PRODUCTS
from .names import FIRST_NAMES, LAST_NAMES, MERCHANTS, STAFF, STREETS, customer_phone
from .texts import render_document, render_message, render_reply

AS_OF = parse_utc("2026-11-02T07:00:00Z")
SCENARIOS = {
    "delivered_on_time": (230, "on_time"), "delivered_late": (45, "late"),
    "delivered_very_late": (15, "very_late"), "in_transit_on_time": (35, "on_time"),
    "in_transit_late": (12, "late"), "out_for_delivery": (6, "on_time"),
    "customs_hold": (8, "at_risk"), "delivery_failed": (10, "at_risk"),
    "returned": (8, "returned"), "lost_suspected": (6, "lost_suspected"),
    "not_picked_up": (10, "not_started"),
}
VALUE_RANGES = {"general": (10000, 200000), "clothing": (15000, 150000),
    "electronics": (100000, 900000), "documents": (0, 10000), "perishable": (5000, 50000),
    "furniture": (100000, 800000), "battery": (10000, 100000), "cosmetics": (10000, 100000),
    "hazardous": (5000, 100000)}



@dataclass(frozen=True)
class SampleData:
    tables: dict[str, list]
    scenarios: dict[str, str]


def _local(day, hour, tz, minute=0, second=0):
    return datetime.combine(day, time(hour, minute, second), ZoneInfo(tz)).astimezone(ZoneInfo("UTC"))


def _pickup_time(day, rng, after_cutoff=None):
    hours = (16, 17, 18) if after_cutoff else tuple(range(8, 16))
    if after_cutoff is None:
        hours = tuple(range(8, 19))
    return _local(day, rng.choice(hours), "Africa/Cairo", rng.randrange(60), rng.randrange(60))


def _pickup_for(s, target, rng):
    candidates = []
    for delta in range(35):
        day = parse_utc("2026-10-29T00:00:00Z").date() - timedelta(days=delta)
        if not is_business_day(day):
            continue
        for after_cutoff in (False, True):
            pickup = _pickup_time(day, rng, after_cutoff)
            if promised_date(s, pickup) == target:
                candidates.append(pickup)
    if not candidates:
        raise ValueError("No pickup date meets the scenario")
    return rng.choice(candidates)


def _destination_arrival(departed: datetime, round_start: datetime, final: datetime,
                         hours: int, minutes: int) -> datetime:
    """Return when a domestic parcel reaches its destination hub.

    It is on the road for at least two hours after it leaves the origin hub,
    and it is at the destination hub before the delivery round starts.
    """
    arrival = final - timedelta(hours=hours, minutes=minutes)
    if arrival >= round_start:
        arrival = round_start - timedelta(hours=hours - 9, minutes=minutes)
    if arrival < departed + timedelta(hours=2):
        arrival = departed + timedelta(hours=hours - 8, minutes=minutes)
    if arrival >= round_start:
        arrival = departed + (round_start - departed) / 2
    return arrival


def _events(s, scenario, rng):
    if scenario == "not_picked_up":
        created = _pickup_time(parse_utc("2026-10-29T00:00:00Z").date()
                               - timedelta(days=rng.randrange(4)), rng)
        return created, [("CREATED", created, CITIES[s.origin_city].hub)]
    if scenario.startswith("delivered"):
        days = [parse_utc("2026-08-02T00:00:00Z").date() + timedelta(days=i)
                for i in range(89)]
        working_days = [day for day in days if is_business_day(day)]
        late = (0 if scenario == "delivered_on_time" else rng.randint(1, 2)
                if scenario == "delivered_late" else rng.randint(3, 5))
        while True:
            pickup = _pickup_time(rng.choice(working_days), rng)
            promised = promised_date(s, pickup)
            delivery_day = add_business_days(promised, late) if late else promised
            if delivery_day < AS_OF.date():
                break
        final = _local(delivery_day, rng.randint(12, 20), s.destination_tz,
                       rng.randrange(60), rng.randrange(60))
    elif scenario == "in_transit_on_time":
        candidates = []
        for delta in range(12):
            day = parse_utc("2026-10-29T00:00:00Z").date() - timedelta(days=delta)
            if is_business_day(day):
                for after_cutoff in (False, True):
                    candidate = _pickup_time(day, rng, after_cutoff)
                    if promised_date(s, candidate) > AS_OF.date():
                        candidates.append(candidate)
        pickup = rng.choice(candidates)
    elif scenario in ("in_transit_late", "out_for_delivery", "customs_hold", "delivery_failed"):
        target = parse_utc("2026-10-29T00:00:00Z").date() if scenario == "in_transit_late" else AS_OF.date()
        if scenario == "customs_hold":
            target = AS_OF.date() + timedelta(days=1)
        pickup = _pickup_for(s, target, rng)
    else:
        pickup = _pickup_time(parse_utc("2026-10-12T00:00:00Z").date(), rng)
    created = pickup - timedelta(hours=rng.randint(2, 18), minutes=rng.randrange(60))
    origin = CITIES[s.origin_city].hub
    arrived = pickup + timedelta(minutes=rng.randint(60, 200), seconds=rng.randrange(60))
    departed = arrived + timedelta(minutes=rng.randint(70, 240), seconds=rng.randrange(60))
    scans = [("CREATED", created, origin), ("PICKED_UP", pickup, origin),
             ("ARRIVED_HUB", arrived, origin), ("DEPARTED_HUB", departed, origin)]
    if s.lane == "international":
        scans.append(("DEPARTED_HUB", departed + timedelta(hours=rng.randint(8, 26),
                       minutes=rng.randrange(60)), "Cairo Airport Export Desk"))
    if scenario.startswith("delivered"):
        hub_draw = None
        if s.lane == "international":
            scans.append(("CUSTOMS_CLEARED", final - timedelta(hours=rng.randint(22, 30),
                          minutes=rng.randrange(60)), f"{s.destination_city} customs"))
        else:
            hub_draw = (rng.randint(10, 16), rng.randrange(60))
        round_start = _local(delivery_day, rng.randint(7, 10), s.destination_tz,
                             rng.randrange(60), rng.randrange(60))
        if hub_draw is not None:
            scans.append(("ARRIVED_HUB", _destination_arrival(departed, round_start, final, *hub_draw),
                          CITIES[s.destination_city].hub))
        scans += [("OUT_FOR_DELIVERY", round_start, s.destination_city),
                  ("DELIVERED", final, s.destination_city)]
    elif scenario == "lost_suspected":
        scans.append(("DEPARTED_HUB", _pickup_time(parse_utc("2026-10-14T00:00:00Z").date(), rng),
                      "Cairo Airport Export Desk" if s.lane == "international" else origin))
    elif scenario == "returned":
        scans += [("RETURN_TO_SENDER", _local(parse_utc("2026-10-20T00:00:00Z").date(),
                    rng.randint(9, 18), s.destination_tz, rng.randrange(60), rng.randrange(60)), s.destination_city),
                  ("RETURNED", _pickup_time(parse_utc("2026-10-21T00:00:00Z").date(), rng), origin)]
    else:
        code = {"in_transit_on_time": "ARRIVED_HUB", "in_transit_late": "ARRIVED_HUB",
                "out_for_delivery": "OUT_FOR_DELIVERY", "customs_hold": "CUSTOMS_HOLD",
                "delivery_failed": "DELIVERY_FAILED"}[scenario]
        if scenario == "out_for_delivery":
            last = parse_utc("2026-11-02T05:00:00Z") + timedelta(seconds=rng.randrange(7200))
        else:
            last = _local(parse_utc("2026-11-01T00:00:00Z").date(), rng.randint(10, 19),
                          s.destination_tz, rng.randrange(60), rng.randrange(60))
        if scenario == "delivery_failed":
            scans.append(("OUT_FOR_DELIVERY", last - timedelta(hours=rng.randint(1, 3)), s.destination_city))
        location = (f"{s.destination_city} customs" if scenario == "customs_hold" else
                    s.destination_city if code in ("OUT_FOR_DELIVERY", "DELIVERY_FAILED") else
                    s.destination_city + " partner depot" if s.lane == "international" else
                    CITIES[s.destination_city].hub)
        scans.append((code, last, location))
    return created, sorted(scans, key=lambda item: item[1])


def _customer_hour_weight(hour):
    """Relative chance of a customer action in a Cairo hour."""
    return 0.25 if hour < 6 else 0.5 if hour < 8 else 1.0


def _customer_time(earliest, latest, rng):
    """Draw one weighted second, including partial hours at either boundary."""
    earliest = earliest.astimezone(ZoneInfo("UTC"))
    latest = latest.astimezone(ZoneInfo("UTC"))
    if earliest > latest:
        raise ValueError("No customer time remains in the window")
    intervals = []
    start = earliest
    while start <= latest:
        end = min(start.replace(minute=0, second=0) + timedelta(hours=1),
                  latest + timedelta(seconds=1))
        weight = int(4 * _customer_hour_weight(start.astimezone(ZoneInfo("Africa/Cairo")).hour))
        size = int((end - start).total_seconds()) * weight
        intervals.append((start, weight, size))
        start = end
    draw = rng.randrange(sum(size for _, _, size in intervals))
    for start, weight, size in intervals:
        if draw < size:
            return start + timedelta(seconds=draw // weight)
        draw -= size
    raise AssertionError("Customer time draw exceeded the window")


def _reply_time(received, rng):
    local = received.astimezone(ZoneInfo("Africa/Cairo"))
    business_day = is_business_day(local.date())
    if business_day and time(8) <= local.time() < time(20):
        sent = received + timedelta(seconds=rng.randint(8 * 60, 45 * 60))
        if sent < _local(local.date(), 20, "Africa/Cairo"):
            return sent
    day = local.date() if business_day and local.time() < time(8) else add_business_days(local.date(), 1)
    return _local(day, 8, "Africa/Cairo", 5) + timedelta(seconds=rng.randint(0, 145 * 60))


def _topic_window(topic, shipment, delivered, claim=None):
    """Inclusive arrival bounds for a customer's primary question."""
    lower = shipment.created_at + timedelta(hours=1)
    upper = AS_OF
    if topic in ("status_question", "delay", "address_change"):
        if delivered is not None:
            upper = (delivered - timedelta(seconds=1) if topic == "address_change" else
                     delivered + timedelta(days=3 if topic == "status_question" else 7))
    elif topic == "claim_followup" and claim is not None:
        lower = claim.opened_at + timedelta(seconds=1)
        upper = claim.opened_at + timedelta(days=21)
    elif topic in ("return", "damage", "claim_followup"):
        if delivered is None:
            return None
        lower = delivered + timedelta(hours=1)
        upper = delivered + timedelta(days=45 if topic == "return" else 30)
    elif topic == "other":
        lower = (delivered or shipment.created_at) + timedelta(hours=1)
    lower = max(lower, _local(datetime(2026, 9, 1).date(), 0, "Africa/Cairo"))
    upper = min(upper, AS_OF)
    return (lower, upper) if lower <= upper else None


def _message_window(topics, shipment, delivered, claim=None):
    # A post-delivery question supplies the longer shared window.
    for topic in ("return", "damage"):
        if topic in topics:
            return _topic_window(topic, shipment, delivered, claim)
    windows = [_topic_window(topic, shipment, delivered, claim) for topic in topics]
    if any(window is None for window in windows):
        return None
    lower = max(start for start, _ in windows)
    upper = min(end for _, end in windows)
    return (lower, upper) if lower <= upper else None


def _message_weight(topics, shipment, delivered, claim=None):
    """Seconds of the shipment's question window inside the message period."""
    window = _message_window(topics, shipment, delivered, claim)
    return max(0, (window[1] - window[0]).total_seconds()) if window else 0


def _message_decision(topic, shipment, events, merchant, tables, at):
    if topic == "return":
        result = check_return(shipment, events, merchant, tables["return_cases"], at)
        existing = tuple((r.id, "open" if r.decided_at is None or r.decided_at > at else r.status)
                         for r in tables["return_cases"]
                         if r.tracking_number == shipment.tracking_number and r.opened_at <= at
                         and r.status != "refused")
        return result.allowed, result.reason, existing
    if topic == "damage":
        return check_claim(shipment, events, "damage", max(100, shipment.declared_value_piastres), tables["claims"], at)
    if topic == "address_change":
        return check_address_change(shipment, events, shipment.destination_city, tables["address_changes"], at)
    if topic in ("delay", "status_question"):
        return classify_delay(shipment, events, at)
    if topic == "claim_followup":
        return tuple((c.id, "open" if c.decided_at is None or c.decided_at > at else c.status)
                     for c in tables["claims"]
                     if c.tracking_number == shipment.tracking_number and c.opened_at <= at)
    return None


def _decision_time(opened, rng, damage=False):
    """Choose a later desk second within three business days of the request."""
    local = opened.astimezone(ZoneInfo("Africa/Cairo"))
    deadline = datetime.combine(add_business_days(local.date(), 3), local.time(), local.tzinfo)
    earliest = opened + timedelta(seconds=1)
    if damage:
        earliest = datetime.combine(add_business_days(local.date(), 1), local.time(), local.tzinfo)
    intervals = []
    for offset in range((deadline.date() - local.date()).days + 1):
        day = local.date() + timedelta(days=offset)
        if not is_business_day(day):
            continue
        start = max(_local(day, 8, "Africa/Cairo"), earliest)
        end = min(_local(day, 20, "Africa/Cairo") - timedelta(seconds=1), deadline, AS_OF)
        if start <= end:
            intervals.append((start, end))
    if not intervals:
        return None
    start, end = rng.choice(intervals)
    return start + timedelta(seconds=rng.randrange(int((end - start).total_seconds()) + 1))


def _case_times(earliest, latest, rng, occupied, *, decided=True, damage=False, check):
    """Choose request and decision times within the recorded policy window."""
    for _ in range(10000):
        opened = _customer_time(earliest, latest, rng)
        if opened in occupied or not check(opened):
            continue
        decision = _decision_time(opened, rng, damage) if decided else None
        if decided and (decision is None or not check(decision)):
            continue
        occupied.add(opened)
        return opened, decision
    raise ValueError("No request time meets the case decision and desk calendar")


def generate(seed=20261101, authored_path: Path | None = None) -> SampleData:
    from dataclasses import replace

    rng = random.Random(seed)
    tables = {name: [] for name in ("meta", "staff", "customers", "shipments", "tracking_events",
        "return_cases", "claims", "address_changes", "messages", "message_labels", "replies", "documents")}
    tables["meta"] = [Meta("as_of", "2026-11-02T07:00:00Z"), Meta("seed", str(seed)), Meta("generator_version", "3")]
    tables["staff"] = [Staff(*row) for row in STAFF]
    customers = tables["customers"]
    used_phones = set()
    merchant_phones = [customer_phone("EG", rng, used_phones) for _ in MERCHANTS]
    fixed_customers = anchor_customers(rng, used_phones)
    merchant_joined = parse_utc("2024-11-01T00:00:00Z").date()
    for i, name in enumerate(MERCHANTS, 1):
        city = "Cairo" if i % 2 == 0 else "Alexandria"
        email = name.lower().replace(" ", ".") + "@example.com"
        merchant_joined += timedelta(days=rng.randint(3, 30))
        joined_at = _local(merchant_joined, rng.randint(8, 21), "Africa/Cairo", rng.randrange(60), rng.randrange(60))
        customers.append(Customer(f"CUS-{i:05}", "merchant", name, email,
            merchant_phones[i - 1], city, "EG", i <= 15 and i != 3, joined_at))
    customers.extend(fixed_customers)
    cities = tuple(CITIES)
    name_pairs = rng.sample(range(len(FIRST_NAMES) * len(LAST_NAMES)), 265)
    for offset, i in enumerate(range(116, 381)):
        city = cities[(i - 116) % len(cities)]
        geo = CITIES[city]
        pair = name_pairs[offset]
        name = f"{FIRST_NAMES[pair // len(LAST_NAMES)]} {LAST_NAMES[pair % len(LAST_NAMES)]}"
        email = name.lower().replace(" ", ".") + "@" + rng.choice(("example.com", "example.net", "example.org"))
        customers.append(Customer(f"CUS-{i:05}", "recipient", name, email,
            customer_phone(geo.country, rng, used_phones), city, geo.country, False, parse_utc("2026-08-01T00:00:00Z")))
    customer_map = {c.id: c for c in customers}
    recipient_pools = {city: [c for c in customers if c.kind == "recipient"
                            and int(c.id[4:]) >= 116 and c.city == city] for city in cities}
    for pool in recipient_pools.values():
        rng.shuffle(pool)
    recipient_counts = {city: 0 for city in cities}
    anchors, anchor_events, anchor_returns = anchor_shipments()
    tables["shipments"].extend(anchors)
    tables["tracking_events"].extend(anchor_events)
    tables["return_cases"].extend(anchor_returns)
    tables["claims"].extend(anchor_claims(anchors, anchor_events))
    destinations = [cities[i % 6] for i in range(308)] + ["Dubai"] * 31 + ["Riyadh"] * 27 + ["Amman"] * 19
    services = ["standard"] * 231 + ["express"] * 96 + ["economy"] * 58
    insurance = [True] * 58 + [False] * 327
    for choices in (destinations, services, insurance):
        rng.shuffle(choices)
    available = list(range(385))
    assignment = {}
    # Reserve the constrained scenarios before distributing delivered records.
    for scenario, count, eligible in (
        ("in_transit_on_time", 35, lambda i: services[i] != "express" or CITIES[destinations[i]].lane == "international"),
        ("customs_hold", 8, lambda i: CITIES[destinations[i]].lane == "international"),
    ):
        chosen = [i for i in available if eligible(i)][:count]
        for i in chosen:
            assignment[i] = scenario
            available.remove(i)
    remainder = [scenario for scenario, (count, _) in SCENARIOS.items()
                 if scenario not in ("in_transit_on_time", "customs_hold") for _ in range(count)]
    rng.shuffle(remainder)
    assignment.update(zip(available, remainder, strict=True))
    scenarios = {}
    categories = tuple(VALUE_RANGES)
    for i in range(385):
        city = destinations[i]
        geo = CITIES[city]
        category = rng.choices(categories, weights=(30, 25, 15, 8, 7, 5, 5, 3, 2), k=1)[0]
        merchants = [c for c in customers[:20] if any(
            p.category == category and p.description in MERCHANT_PRODUCTS[c.name] for p in PRODUCTS)]
        merchant = rng.choice(merchants)
        product = rng.choice([p for p in PRODUCTS if p.category == category
                              and p.description in MERCHANT_PRODUCTS[merchant.name]])
        pieces = rng.choices(range(1, product.max_pieces + 1), weights=(6, 3, 1)[:product.max_pieces], k=1)[0]
        weight = sum(rng.randint(round(product.piece_kg[0] * 10), round(product.piece_kg[1] * 10))
                     for _ in range(pieces)) / 10
        value = rng.randint(*product.piece_egp) * pieces * 100
        tn = make_tracking_number(10001 + i)
        pool = recipient_pools[city]
        recipient = pool[recipient_counts[city] % len(pool)]
        recipient_counts[city] += 1
        s = Shipment(tn, merchant.id, recipient.id, services[i], geo.lane, merchant.city,
            city, geo.country, geo.time_zone, f"{rng.randint(2, 180)} {rng.choice(STREETS)}, Flat {rng.randint(1, 18)}", category, product.description,
            pieces, weight, value, insurance[i], shipping_fee(geo.lane, services[i], weight, insurance[i], value), AS_OF)
        scenario = assignment[i]
        created, scans = _events(s, scenario, rng)
        s = replace(s, created_at=created)
        tables["shipments"].append(s)
        for code, when, location in scans:
            tables["tracking_events"].append(TrackingEvent(len(tables["tracking_events"]) + 1, tn, when, EventCode(code), location, ""))
        scenarios[tn] = scenario
    generated = tables["shipments"][15:]
    ordered = sorted(generated, key=lambda s: (s.created_at, s.tracking_number))
    numbers = {s.tracking_number: make_tracking_number(10001 + i)
               for i, s in enumerate(ordered)}
    generated = [replace(s, tracking_number=numbers[s.tracking_number]) for s in generated]
    tables["shipments"][15:] = generated
    tables["tracking_events"] = [replace(e, tracking_number=numbers.get(e.tracking_number, e.tracking_number))
                                 for e in tables["tracking_events"]]
    scenarios = {numbers[number]: scenario for number, scenario in scenarios.items()}
    by_tn = {s.tracking_number: s for s in tables["shipments"]}
    events = {tn: [] for tn in by_tn}
    for e in tables["tracking_events"]:
        events[e.tracking_number].append(e)
    delivered = [s for s in generated if any(e.code == "DELIVERED" for e in events[s.tracking_number])]
    delivery = {s.tracking_number: next(e.occurred_at for e in events[s.tracking_number] if e.code == "DELIVERED") for s in delivered}
    allowed, refused = [], []
    for s in delivered:
        at = delivery[s.tracking_number] + timedelta(days=2)
        if at > AS_OF:
            continue
        d = check_return(s, events[s.tracking_number], customer_map[s.merchant_id], [], at)
        (allowed if d.allowed else refused).append((s, at, d))
    occupied = {row.opened_at for name in ("return_cases", "claims") for row in tables[name]}
    fixed_return_time = anchor_returns[0].opened_at
    # Keep the case number quoted in customer correspondence in time order.
    before = [row for row in allowed if row[1] < fixed_return_time][:35]
    before_numbers = {row[0].tracking_number for row in before}
    after = [row for row in allowed if row[0].tracking_number not in before_numbers
             and delivery[row[0].tracking_number] + timedelta(days=30) > fixed_return_time][:9]
    refused_before = [row for row in refused if row[1] < fixed_return_time][:15]
    if (len(before), len(after), len(refused_before)) != (35, 9, 15):
        raise ValueError("Not enough return requests within the policy windows")
    return_inputs = [(row, status, False) for row, status in zip(
        before, ["approved"] * 30 + ["received"] * 5, strict=True)]
    return_inputs += [(row, "open", True) for row in after]
    return_inputs += [(row, "refused", False) for row in refused_before]
    for (s, _baseline, d), status, after_fixed in return_inputs:
        lower = delivery[s.tracking_number] + timedelta(seconds=1)
        upper = min(AS_OF, lower + timedelta(days=30))
        if after_fixed:
            lower = max(lower, fixed_return_time + timedelta(seconds=1))
        else:
            upper = min(upper, fixed_return_time - timedelta(seconds=1))
        at, decided_at = _case_times(lower, upper, rng, occupied,
            decided=status not in ("open", "refused"),
            check=lambda at, s=s, d=d: check_return(s, events[s.tracking_number],
                customer_map[s.merchant_id], [], at).reason == d.reason)
        author = None if status == "open" else rng.choice(
            ("karim.nassar", "dina.fawzy", "omar.elbanna")) if status == "refused" else "reem.adel"
        tables["return_cases"].append(ReturnCase(f"RET-{len(tables['return_cases'])+1:05}", s.tracking_number,
            at, "other" if status == "refused" else "not_wanted", status, d.reason,
            at if status == "refused" else decided_at, author, "Return checked against the policy."))
    fixed_claim_time = tables["claims"][0].opened_at
    early_delivered = [s for s in delivered if delivery[s.tracking_number] + timedelta(days=3) < fixed_claim_time]
    later_delivered = [s for s in delivered if fixed_claim_time < delivery[s.tracking_number]
                       and delivery[s.tracking_number] + timedelta(days=2) <= AS_OF]
    damage_inputs = [(s, "damage", delivery[s.tracking_number] + timedelta(days=2), before)
                     for pool, before in ((early_delivered, True), (later_delivered, False)) for s in pool[:7]]
    damage_numbers = {s.tracking_number for s, _, _, _ in damage_inputs}
    claim_inputs = damage_inputs + [(s, "loss", AS_OF, False) for s in generated
                                    if scenarios[s.tracking_number] == "lost_suspected"]
    for pool, before, approved_count, refused_count in (
        (early_delivered, True, 1, 7), (later_delivered, False, 1, 1),
    ):
        eligible, ineligible = [], []
        for s in pool:
            if s.service != "express":
                continue
            at = delivery[s.tracking_number] + timedelta(days=2)
            d = check_claim(s, events[s.tracking_number], "delay", 0, [], at)
            (eligible if d.eligible else ineligible).append((s, "delay", at, before))
        if not before:
            ineligible.sort(key=lambda row: row[0].tracking_number in damage_numbers)
        if len(eligible) < approved_count or len(ineligible) < refused_count:
            raise ValueError("Not enough Express claims within the policy windows")
        claim_inputs += eligible[:approved_count] + ineligible[:refused_count]
    if len(damage_inputs) != 14 or len(claim_inputs) != 30:
        raise ValueError("Not enough claims within the policy windows")
    for s, kind, at, before_fixed in claim_inputs:
        amount = 0 if kind == "delay" else max(100, s.declared_value_piastres)
        d = check_claim(s, events[s.tracking_number], kind, amount, [], at)
        if kind == "loss":
            lower = max(e.occurred_at for e in events[s.tracking_number]) + timedelta(days=7)
            upper = AS_OF - timedelta(seconds=1)
        else:
            lower = delivery[s.tracking_number] + timedelta(seconds=1)
            upper = min(AS_OF - timedelta(seconds=1), lower + timedelta(days=14))
        if before_fixed:
            upper = min(upper, fixed_claim_time - timedelta(seconds=1))
        else:
            lower = max(lower, fixed_claim_time + timedelta(seconds=1))
        at, decided_at = _case_times(lower, upper, rng, occupied, decided=d.eligible,
            damage=kind == "damage" and d.eligible,
            check=lambda when, s=s, kind=kind, amount=amount, d=d: check_claim(s, events[s.tracking_number], kind, amount, [], when) == d
            and (kind != "loss" or when.astimezone(ZoneInfo("Africa/Cairo")).date() not in {
                c.opened_at.astimezone(ZoneInfo("Africa/Cairo")).date()
                for c in tables["claims"] if c.kind == "loss"}))
        author = "reem.adel" if d.eligible else rng.choice(("karim.nassar", "dina.fawzy", "omar.elbanna"))
        tables["claims"].append(Claim(f"CLM-{len(tables['claims'])+1:05}", s.tracking_number, kind, at,
            amount, "approved" if d.eligible else "refused", d.reason, d.payable_piastres,
            decided_at if d.eligible else at, author, "Claim checked against the policy."))
    change_candidates = generated.copy()
    rng.shuffle(change_candidates)
    change_days = set()
    for s in change_candidates:
        pickup = next((e for e in events[s.tracking_number] if e.code == "PICKED_UP"), None)
        if pickup is None:
            continue
        at = pickup.occurred_at + timedelta(minutes=rng.randint(20, 50))
        day = at.astimezone(ZoneInfo("Africa/Cairo")).date()
        if day in change_days or at >= AS_OF:
            continue
        if not check_address_change(s, events[s.tracking_number], s.destination_city, [], at).allowed:
            continue
        i = len(tables["address_changes"])
        city = s.destination_city if i < 6 else rng.choice([city for city in cities if city != s.destination_city])
        d = check_address_change(s, events[s.tracking_number], city, [], at)
        line = f"{rng.randint(2, 180)} {STREETS[i]}, Flat {rng.randint(1, 18)}"
        author = rng.choice(("reem.adel", "karim.nassar", "dina.fawzy", "omar.elbanna"))
        tables["address_changes"].append(AddressChange(f"ADR-{i+1:05}", s.tracking_number, at,
            city, line, "applied" if d.allowed else "refused", d.reason, author))
        change_days.add(day)
        if d.allowed:
            e = TrackingEvent(len(tables["tracking_events"])+1, s.tracking_number, at,
                EventCode.ADDRESS_CHANGED, city, f"Address updated to {line}.")
            tables["tracking_events"].append(e)
            events[s.tracking_number].append(e)
            updated = replace(s, address_line=line)
            tables["shipments"][tables["shipments"].index(s)] = updated
            by_tn[s.tracking_number] = updated
        if len(tables["address_changes"]) == 12:
            break
    tables["tracking_events"].sort(key=lambda event: (event.occurred_at, event.id))
    for history in events.values():
        history.sort(key=lambda event: (event.occurred_at, event.id))
    for name, prefix in (("return_cases", "RET-"), ("claims", "CLM-")):
        tables[name] = [replace(row, id=f"{prefix}{i:05}") for i, row in enumerate(
            sorted(tables[name], key=lambda row: (row.opened_at, row.id)), 1)]
    topics = [topic for topic, count in (("status_question", 50), ("delay", 40), ("return", 40),
        ("damage", 30), ("address_change", 20), ("claim_followup", 10), ("other", 10)) for _ in range(count)]
    rng.shuffle(topics)
    positions = list(range(len(topics)))
    # Each feature has its own seeded draw; overlaps are intentional.
    missing_numbers = set(rng.sample(positions, 25))
    invalid_numbers = set(rng.sample([i for i in positions if i not in missing_numbers], 8))
    second_topics = set(rng.sample(positions, 30))
    outsiders = set(rng.sample(positions, 15))
    lower_case = set(rng.sample(positions, 20))
    no_punctuation = set(rng.sample(positions, 20))
    signatures = set(rng.sample(positions, 60))
    from_phone = set(rng.sample(positions, 20))
    quoted_replies = set(rng.sample(positions, 20))
    message_statuses = ["answered"] * 70 + ["closed"] * 70 + ["new"] * 60
    rng.shuffle(message_statuses)
    no_claim_enquiry = False
    refused_claim_enquiry = False
    received_return_enquiry = False
    for i, topic in enumerate(topics):
        topic_set = [topic]
        if i in second_topics:
            compatible = {
                "status_question": ("delay", "return", "damage", "address_change"),
                "delay": ("status_question", "return", "damage", "address_change"),
                "address_change": ("status_question", "delay"),
                "return": ("damage", "delay", "status_question"),
                "damage": ("return", "delay", "status_question"),
                "claim_followup": ("other",),
                "other": ("status_question", "delay"),
            }
            topic_set.append(rng.choice(compatible[topic]))
        status = message_statuses[i]
        numbered_answer = i not in missing_numbers | invalid_numbers and status != "new"
        pick_received = topic == "return" and not received_return_enquiry and numbered_answer
        pick_no_claim = topic == "claim_followup" and not no_claim_enquiry and numbered_answer
        pick_refused = (topic == "claim_followup" and not pick_no_claim
                        and not refused_claim_enquiry and numbered_answer)
        pool = delivered if set(topic_set) & {"return", "damage"} else generated
        if pick_received:
            received_numbers = {r.tracking_number for r in tables["return_cases"] if r.status == "received"}
            pool = [parcel for parcel in pool if parcel.tracking_number in received_numbers]
        if pick_no_claim:
            pool = [parcel for parcel in delivered if not any(
                c.tracking_number == parcel.tracking_number for c in tables["claims"])]
        if pick_refused:
            pool = [parcel for parcel in pool if len(cases := [c for c in tables["claims"]
                    if c.tracking_number == parcel.tracking_number]) == 1 and cases[0].status == "refused"]
        special_pick = pick_received or pick_no_claim or pick_refused
        if not special_pick:
            candidates, weights = [], []
            for parcel in pool:
                cases = ([c for c in tables["claims"] if c.tracking_number == parcel.tracking_number]
                         if topic == "claim_followup" else [None])
                for case in cases:
                    weight = _message_weight(topic_set, parcel, delivery.get(parcel.tracking_number), case)
                    if weight:
                        candidates.append((parcel, case))
                        # Multiple claims must not multiply a shipment's chance.
                        weights.append(weight / len(cases))
            if not candidates:
                raise ValueError("No shipment and arrival meet the message window and desk decision")
        for _ in range(200):
            if special_pick:
                s = rng.choice(pool)
                claims = [c for c in tables["claims"] if c.tracking_number == s.tracking_number]
                if topic == "claim_followup" and not pick_no_claim and not claims:
                    continue
                claim = rng.choice(claims) if topic == "claim_followup" and claims else None
            else:
                s, claim = rng.choices(candidates, weights=weights, k=1)[0]
            window = _message_window(topic_set, s, delivery.get(s.tracking_number), claim)
            if window is None:
                continue
            earliest, latest = window
            if pick_received:
                earliest = max(earliest, max(r.decided_at for r in tables["return_cases"]
                    if r.tracking_number == s.tracking_number and r.status == "received") + timedelta(seconds=1))
            if earliest > latest:
                continue
            for _ in range(200):
                at = _customer_time(earliest, latest, rng)
                if status == "new":
                    break
                sent_at = _reply_time(at, rng)
                if sent_at > AS_OF:
                    continue
                if all(_message_decision(t, s, events[s.tracking_number], customer_map[s.merchant_id], tables, at)
                       == _message_decision(t, s, events[s.tracking_number], customer_map[s.merchant_id], tables, sent_at)
                       for t in topic_set):
                    break
            else:
                continue
            no_claim_enquiry |= pick_no_claim
            refused_claim_enquiry |= pick_refused
            received_return_enquiry |= pick_received
            break
        else:
            raise ValueError("No shipment and arrival meet the message window and desk decision")
        customer = customer_map[s.recipient_id]
        number = s.tracking_number
        missing, invalid, numbers = [], [], [number]
        if i in missing_numbers:
            number, numbers, missing = "my parcel", [], ["tracking_number"]
        elif i in invalid_numbers:
            number = number[:-1] + str((int(number[-1]) + 1) % 10)
            numbers, invalid = [], [number]
        variant = rng.randrange(4)
        body = " ".join(render_message(t, number, (variant + n) % 4) for n, t in enumerate(topic_set))
        if "damage" in topic_set:
            body += f" I am claiming {format_egp(max(100, s.declared_value_piastres))}. I can send photos on request."
            missing.append("photos")
        if "address_change" in topic_set:
            missing.append("new_address")
        if i in signatures:
            body += f"\nRegards,\n{customer.name}"
        if i in from_phone:
            body += "\nSent from my phone"
        if i in quoted_replies:
            body += "\nEarlier desk reply: We have received your message."
        if i in lower_case:
            body = body.lower()
        if i in no_punctuation:
            body = body.translate(str.maketrans("", "", ".,?!:;"))
        if invalid:
            invalid = [number.lower() if i in lower_case else number]
        email = f"contact{i}@example.org" if i in outsiders else customer.email
        staff = rng.choice(("karim.nassar", "dina.fawzy", "omar.elbanna"))
        msg = Message(f"M-{i+1:05}", at, rng.choice(("email", "web_form", "chat")), customer.name,
            email, None if i in outsiders else customer.id, topic.replace("_", " "), body, status,
            staff if status != "new" else None, "generated")
        label = MessageLabel(msg.id, topic, tuple(sorted(topic_set)), tuple(numbers), tuple(invalid),
            tuple(sorted(missing)), False, "none", "mira.saad")
        tables["messages"].append(msg)
        tables["message_labels"].append(label)
        if status != "new":
            decisions = {}
            for reply_topic in topic_set:
                decision = None
                if reply_topic == "return":
                    decision = check_return(s, events[s.tracking_number], customer_map[s.merchant_id], tables["return_cases"], sent_at)
                elif reply_topic == "damage":
                    decision = check_claim(s, events[s.tracking_number], "damage", max(100, s.declared_value_piastres), tables["claims"], sent_at)
                elif reply_topic == "address_change":
                    decision = check_address_change(s, events[s.tracking_number], s.destination_city, tables["address_changes"], sent_at)
                elif reply_topic in ("delay", "status_question"):
                    decision = classify_delay(s, events[s.tracking_number], sent_at)
                decisions[reply_topic] = decision
            reply_body = render_reply(topic, decisions[topic], customer_name=customer.name,
                shipment=s, events=events[s.tracking_number], at=sent_at, variant=variant,
                has_number=bool(numbers), secondary=[(t, decisions[t]) for t in topic_set[1:]],
                invalid_number=invalid[0] if invalid else None, claims=tables["claims"], returns=tables["return_cases"])
            tables["replies"].append(Reply(f"REP-{len(tables['replies'])+1:05}", msg.id, sent_at, staff, reply_body))
    authored = load_authored(authored_path or ROOT / "data/authored/messages.jsonl", tables["shipments"],
                            tables["tracking_events"], customers, AS_OF)
    emails = {c.email: c.id for c in customers}
    for row in authored:
        label = row["labels"]
        tables["messages"].append(Message(row["id"], parse_utc(row["received_at"]), row["channel"],
            row["from_name"], row["from_email"], emails.get(row["from_email"].lower()), row["subject"],
            row["body"], row["status"], None, "authored"))
        tables["message_labels"].append(MessageLabel(row["id"], label["primary_topic"],
            tuple(label["topics"]), tuple(label["tracking_numbers"]), tuple(label["invalid_tracking_mentions"]),
            tuple(label["missing"]), bool(label["contains_instructions"]), label["escalation"], label["labelled_by"]))
    first_shipments = {}
    for shipment in tables["shipments"]:
        first_shipments[shipment.recipient_id] = min(
            first_shipments.get(shipment.recipient_id, AS_OF), shipment.created_at)
    joined_times = {}
    oldest = customers[34].created_at + timedelta(seconds=1)
    latest = parse_utc("2026-08-01T00:00:00Z")
    for customer in customers[35:]:
        first = first_shipments.get(customer.id)
        if first is None or rng.randrange(5) == 0:
            joined_times[customer.id] = oldest + timedelta(seconds=rng.randrange(int((latest - oldest).total_seconds()) + 1))
        else:
            joined_times[customer.id] = first
    joining = sorted(customers[35:], key=lambda c: (joined_times[c.id], c.id))
    ids = {customer.id: f"CUS-{116+i:05}" for i, customer in enumerate(joining)}
    tables["customers"] = customers[:35] + [replace(c, id=ids[c.id], created_at=joined_times[c.id]) for c in joining]
    tables["shipments"] = [replace(s, recipient_id=ids.get(s.recipient_id, s.recipient_id))
                          for s in tables["shipments"]]
    tables["messages"] = [replace(m, customer_id=ids.get(m.customer_id, m.customer_id)) for m in tables["messages"]]
    customer_map = {c.id: c for c in tables["customers"]}
    for i, s in enumerate(tables["shipments"][:40] + [s for s in tables["shipments"] if s.lane == "international"][:20]):
        kind = "waybill" if i < 40 else "commercial_invoice"
        layout = ("a", "b", "c")[i%3]
        body = render_document(s, kind, layout, customer_map[s.merchant_id], customer_map[s.recipient_id])
        tables["documents"].append(Document(f"DOC-{i+1:05}", kind, s.tracking_number, s.created_at, layout, body))
    for label, msg in zip(tables["message_labels"], tables["messages"], strict=True):
        values = asdict(label)
        values.pop("message_id")
        for key in ("topics", "tracking_numbers", "invalid_tracking_mentions", "missing"):
            values[key] = list(values[key])
        validate_labels(values, msg.body, by_tn)
    for table, field, prefix in (("address_changes", "requested_at", "ADR-"),
                                 ("replies", "sent_at", "REP-"),
                                 ("tracking_events", "occurred_at", None)):
        rows = sorted(tables[table], key=lambda row: (getattr(row, field), row.id))
        tables[table] = [replace(row, id=f"{prefix}{i:05}" if prefix else i)
                         for i, row in enumerate(rows, 1)]

    generated_messages = sorted((m for m in tables["messages"] if m.origin == "generated"),
                                key=lambda m: (m.received_at, m.id))
    message_ids = {m.id: f"M-{i:05}" for i, m in enumerate(generated_messages, 1)}
    tables["messages"] = [replace(m, id=message_ids.get(m.id, m.id)) for m in tables["messages"]]
    tables["message_labels"] = [replace(label, message_id=message_ids.get(label.message_id, label.message_id))
                                for label in tables["message_labels"]]
    tables["replies"] = [replace(reply, message_id=message_ids[reply.message_id])
                         for reply in tables["replies"]]
    return SampleData(tables, scenarios)
