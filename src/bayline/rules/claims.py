"""Liability and claim windows."""

from ..models import ClaimDecision, ClaimKind, ClaimReason
from ..status import events_at
from ..timeutil import local_date
from .delays import classify_delay


def liability_cap(shipment):
    """Return the insured or uninsured limit in piastres."""
    cap = shipment.declared_value_piastres
    if not shipment.insured:
        cap = min(cap, 300000)
    return cap


def check_claim(shipment, events, kind, claimed_piastres, existing_claims, at) -> ClaimDecision:
    kind = ClaimKind(kind)
    cap = liability_cap(shipment)
    delivered = [e for e in events_at(events, at) if e.code == "DELIVERED"]
    day = (local_date(at, shipment.destination_tz)
           - local_date(delivered[-1].occurred_at, shipment.destination_tz)).days if delivered else None
    delay = classify_delay(shipment, events, at)
    payable = 0
    reason = ClaimReason.ELIGIBLE
    if kind in (ClaimKind.DAMAGE, ClaimKind.LOSS) and claimed_piastres <= 0:
        reason = ClaimReason.INVALID_AMOUNT
    elif any(c.tracking_number == shipment.tracking_number and c.kind == kind
             and c.opened_at <= at and c.status in ("open", "approved", "paid")
             for c in existing_claims):
        reason = ClaimReason.ALREADY_EXISTS
    elif kind == ClaimKind.DAMAGE:
        if day is None:
            reason = ClaimReason.NOT_DELIVERED
        elif day > 14:
            reason = ClaimReason.WINDOW_CLOSED
        else:
            payable = min(claimed_piastres, cap)
    elif kind == ClaimKind.LOSS:
        if delivered:
            reason = ClaimReason.DELIVERED
        elif delay.delay_class != "lost_suspected" and delay.late_business_days < 10:
            reason = ClaimReason.NOT_LATE_ENOUGH
        else:
            payable = min(claimed_piastres, cap) + shipment.shipping_fee_piastres
    else:
        if shipment.service != "express":
            reason = ClaimReason.SERVICE_NOT_COVERED
        elif day is None:
            reason = ClaimReason.NOT_DELIVERED
        elif delay.late_business_days == 0:
            reason = ClaimReason.NOT_LATE_ENOUGH
        elif day > 14:
            reason = ClaimReason.WINDOW_CLOSED
        else:
            payable = shipment.shipping_fee_piastres
    return ClaimDecision(reason == ClaimReason.ELIGIBLE, reason, payable)
