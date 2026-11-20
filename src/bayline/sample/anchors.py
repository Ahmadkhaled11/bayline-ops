"""Fixed customer cases used in desk documentation."""

import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..geography import CITIES
from ..models import Claim, Customer, EventCode, ReturnCase, Shipment, TrackingEvent
from ..rules.claims import check_claim
from ..rules.pricing import shipping_fee
from ..timeutil import parse_utc
from .names import ANCHOR_FIRST_NAMES, ANCHOR_LAST_NAMES, STREETS, customer_phone

ANCHOR_NUMBERS = (
    "BYL260411871", "BYL260415328", "BYL260439062", "BYL260442157", "BYL260444716",
    "BYL260448907", "BYL260451265", "BYL260453097", "BYL260455803", "BYL260459136",
    "BYL260462072", "BYL260464888", "BYL260467527", "BYL260470315", "BYL260473640",
)
# Merchant, category, service, destination, pickup, final scan, final code, declared EGP.
ANCHOR_ROWS = (
    (1, "clothing", "standard", "Cairo", "2026-09-21T07:00:00Z", "2026-09-24T11:10:00Z", "DELIVERED", 1200),
    (1, "clothing", "standard", "Giza", "2026-09-20T07:00:00Z", "2026-09-23T13:00:00Z", "DELIVERED", 1200),
    (2, "electronics", "standard", "Dubai", "2026-09-23T07:00:00Z", "2026-10-01T10:00:00Z", "DELIVERED", 2500),
    (2, "electronics", "express", "Cairo", "2026-10-05T07:00:00Z", "2026-10-07T12:00:00Z", "DELIVERED", 2500),
    (2, "electronics", "express", "Alexandria", "2026-10-11T06:00:00Z", "2026-10-13T09:00:00Z", "DELIVERED", 2500),
    (2, "electronics", "express", "Tanta", "2026-10-15T14:30:00Z", "2026-10-19T10:00:00Z", "DELIVERED", 2500),
    (2, "battery", "standard", "Mansoura", "2026-10-15T07:00:00Z", "2026-10-20T08:00:00Z", "DELIVERED", 900),
    (3, "furniture", "economy", "Cairo", "2026-10-11T07:00:00Z", "2026-10-18T11:00:00Z", "DELIVERED", 2500),
    (2, "electronics", "standard", "Port Said", "2026-10-07T07:00:00Z", "2026-10-12T13:00:00Z", "DELIVERED", 8500),
    (1, "clothing", "standard", "Cairo", "2026-10-28T07:00:00Z", "2026-11-02T06:30:00Z", "OUT_FOR_DELIVERY", 1200),
    (1, "clothing", "standard", "Cairo", "2026-10-29T07:00:00Z", "2026-10-30T09:00:00Z", "ARRIVED_HUB", 1200),
    (1, "clothing", "standard", "Cairo", "2026-10-29T08:00:00Z", "2026-10-30T09:00:00Z", "ARRIVED_HUB", 1200),
    (2, "electronics", "standard", "Riyadh", "2026-10-20T08:00:00Z", "2026-10-27T08:00:00Z", "CUSTOMS_HOLD", 2500),
    (1, "clothing", "standard", "Mansoura", "2026-10-12T06:00:00Z", "2026-10-14T05:00:00Z", "DEPARTED_HUB", 1200),
    (1, "clothing", "standard", "Cairo", "2026-10-15T07:00:00Z", "2026-10-20T10:00:00Z", "DELIVERED", 1200),
)


def anchor_customers(rng=None, used_phones=None):
    rng = rng if rng is not None else random.Random(20261101)
    used_phones = used_phones if used_phones is not None else set()
    domains = ("com", "net", "com", "org", "com", "net", "com", "org", "com", "net", "com", "org", "com", "net", "com")
    customers = []
    phones = [customer_phone(CITIES[row[3]].country, rng, used_phones) for row in ANCHOR_ROWS]
    joined = parse_utc("2026-01-01T00:00:00Z").date()
    for i, row in enumerate(ANCHOR_ROWS):
        joined += timedelta(days=rng.randint(3, 7))
        joined_at = datetime.combine(joined, time(rng.randint(8, 21), rng.randrange(60), rng.randrange(60)),
                                     ZoneInfo("Africa/Cairo")).astimezone(ZoneInfo("UTC"))
        customers.append(Customer(f"CUS-{101+i:05}", "recipient", f"{ANCHOR_FIRST_NAMES[i]} {ANCHOR_LAST_NAMES[i]}",
        f"{ANCHOR_FIRST_NAMES[i].lower()}.{ANCHOR_LAST_NAMES[i].lower()}@example.{domains[i]}",
        phones[i], row[3], CITIES[row[3]].country, False,
        joined_at))
    return customers


def anchor_shipments():
    shipments, events = [], []
    for i, row in enumerate(ANCHOR_ROWS):
        merchant, category, service, city, pickup_text, final_text, final_code, value = row
        pickup, final = parse_utc(pickup_text), parse_utc(final_text)
        geo = CITIES[city]
        tn = ANCHOR_NUMBERS[i]
        description = ("jacket", "dress", "smart watch", "phone", "laptop charger", "tablet",
                       "power bank", "coffee table", "wireless headphones", "cotton scarf",
                       "linen trousers", "cotton sweater", "laptop", "two shirts", "dress")[i]
        weight = (0.9, 0.4, 0.3, 0.4, 0.5, 0.8, 0.4, 18.5, 0.5, 0.2, 0.5, 0.6, 2.4, 0.5, 0.5)[i]
        s = Shipment(tn, f"CUS-{merchant:05}", f"CUS-{101+i:05}", service, geo.lane,
            "Cairo" if merchant == 2 else "Alexandria", city, geo.country, geo.time_zone,
            f"{i+1} {STREETS[i % len(STREETS)]}", category, description, 1, weight, value * 100, False,
            shipping_fee(geo.lane, service, weight, False, value * 100), pickup - timedelta(hours=2))
        shipments.append(s)
        scans = [("CREATED", s.created_at), ("PICKED_UP", pickup)]
        if final_code != "ARRIVED_HUB":
            scans += [("ARRIVED_HUB", pickup + timedelta(hours=3))]
        if final_code in ("DELIVERED", "OUT_FOR_DELIVERY", "CUSTOMS_HOLD"):
            scans += [("DEPARTED_HUB", pickup + timedelta(hours=5))]
        if s.lane == "international" and final_code == "DELIVERED":
            scans += [("DEPARTED_HUB", pickup + timedelta(days=1))]
            scans += [("CUSTOMS_CLEARED", final - timedelta(days=1))]
        elif s.lane == "international":
            scans += [("DEPARTED_HUB", pickup + timedelta(days=1))]
        if final_code == "DELIVERED":
            scans += [("OUT_FOR_DELIVERY", final.replace(hour=6, minute=0))]
        scans += [(final_code, final)]
        for code, when in scans:
            if code in ("CUSTOMS_HOLD", "CUSTOMS_CLEARED"):
                location = f"{city} customs"
            elif code in ("OUT_FOR_DELIVERY", "DELIVERY_FAILED", "DELIVERED"):
                location = city
            elif code == "DEPARTED_HUB" and s.lane == "international" and when > pickup + timedelta(hours=5):
                location = "Cairo Airport Export Desk"
            elif code == "ARRIVED_HUB" and when == final:
                location = geo.hub
            else:
                location = CITIES[s.origin_city].hub
            events.append(TrackingEvent(len(events) + 1, tn, when, EventCode(code), location, ""))
    case = ReturnCase("RET-00051", ANCHOR_NUMBERS[14], parse_utc("2026-10-22T08:00:00Z"),
                       "not_wanted", "open", "ALLOWED", None, None, "Return requested.")
    return shipments, events, [case]


def anchor_claims(shipments, events):
    shipment = next(s for s in shipments if s.tracking_number == ANCHOR_NUMBERS[3])
    opened = parse_utc("2026-10-08T08:00:00Z")
    history = [event for event in events if event.tracking_number == shipment.tracking_number]
    decision = check_claim(shipment, history, "delay", 0, [], opened)
    if decision.eligible:
        raise ValueError("The recorded delay claim must be refused")
    return [Claim("CLM-00001", shipment.tracking_number, "delay", opened, 0,
                  "refused", decision.reason, decision.payable_piastres,
                  opened, "dina.fawzy",
                  "Customer requested a delay claim after delivery.")]
