"""Return checks count calendar days after delivery."""

from datetime import timedelta

from ..models import ReturnDecision, ReturnReason
from ..status import events_at


def check_return(shipment, events, merchant, existing_returns, requested_at) -> ReturnDecision:
    delivered = [e for e in events_at(events, requested_at) if e.code == "DELIVERED"]
    day = None
    last = None
    if delivered:
        delivery_date = delivered[-1].occurred_at.date()
        day = (requested_at.date() - delivery_date).days
        last = delivery_date + timedelta(days=30)
    if day is None or day < 0:
        reason = ReturnReason.NOT_DELIVERED
    elif not merchant.returns_plan:
        reason = ReturnReason.MERCHANT_NOT_ON_PLAN
    elif shipment.goods_category in ("perishable", "battery", "hazardous"):
        reason = ReturnReason.CATEGORY_EXCLUDED
    elif any(r.tracking_number == shipment.tracking_number
             and r.opened_at <= requested_at
             and r.status in ("open", "approved", "received") for r in existing_returns):
        reason = ReturnReason.ALREADY_OPEN
    elif day > 30:
        reason = ReturnReason.WINDOW_CLOSED
    else:
        reason = ReturnReason.ALLOWED
    return ReturnDecision(reason == ReturnReason.ALLOWED, reason, day, last)
