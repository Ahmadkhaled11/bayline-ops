from dataclasses import replace

from bayline.geography import CITIES
from bayline.models import Customer, EventCode, Shipment, TrackingEvent
from bayline.rules.pricing import shipping_fee
from bayline.timeutil import parse_utc

AT = parse_utc("2026-11-02T07:00:00Z")
MERCHANT = Customer("CUS-00001", "merchant", "Nile Loom", "shop@bayline.example", "",
                    "Alexandria", "EG", True, parse_utc("2026-08-01T00:00:00Z"))


def shipment(**changes):
    result = Shipment("BYL260411871", MERCHANT.id, "CUS-00101", "standard", "domestic",
                      "Alexandria", "Cairo", "EG", "Africa/Cairo", "Parcel Lane 1",
                      "clothing", "shirt", 1, 2.0, 120000, False, 4500,
                      parse_utc("2026-08-01T00:00:00Z"))
    if "destination_city" in changes:
        geo = CITIES[changes["destination_city"]]
        changes.update(destination_country=geo.country, destination_tz=geo.time_zone, lane=geo.lane)
    result = replace(result, **changes)
    return replace(result, shipping_fee_piastres=shipping_fee(result.lane, result.service,
                   result.weight_kg, result.insured, result.declared_value_piastres))


def history(*pairs, tn="BYL260411871"):
    return [TrackingEvent(i, tn, parse_utc(time), EventCode(code), "Cairo Hub", "")
            for i, (code, time) in enumerate(pairs, 1)]
