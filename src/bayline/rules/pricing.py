"""Fees in whole piastres."""

from math import ceil, isfinite

RATES = {
    "domestic": {"express": (75, 12), "standard": (45, 8), "economy": (35, 6)},
    "international": {"express": (650, 60), "standard": (420, 40), "economy": (300, 30)},
}


def shipping_fee(lane, service, weight_kg, insured, declared_value_piastres) -> int:
    if lane not in RATES or service not in RATES[lane]:
        raise ValueError("Unknown lane or service")
    if (not isfinite(weight_kg) or weight_kg <= 0 or not isinstance(declared_value_piastres, int)
            or declared_value_piastres < 0):
        raise ValueError("Weight must be positive and declared value nonnegative")
    base, extra = RATES[lane][service]
    fee = (base + extra * max(0, max(1, ceil(weight_kg)) - 5)) * 100
    if insured:
        fee += max(2000, (declared_value_piastres + 99) // 100)
    return fee
