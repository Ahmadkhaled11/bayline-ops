"""An address change stays within the destination city."""

from ..models import AddressDecision, AddressReason
from ..status import current_status


def check_address_change(shipment, events, new_city, existing_changes, at) -> AddressDecision:
    status = current_status(events, at)
    if status in ("out_for_delivery", "delivered", "returning", "returned_to_sender"):
        reason = AddressReason.TOO_LATE
    elif status == "customs_hold":
        reason = AddressReason.CUSTOMS_HOLD
    elif any(c.tracking_number == shipment.tracking_number
             and c.requested_at <= at
             and c.status == "applied" for c in existing_changes):
        reason = AddressReason.ALREADY_CHANGED
    elif new_city.strip().casefold() != shipment.destination_city.strip().casefold():
        reason = AddressReason.DIFFERENT_CITY
    else:
        reason = AddressReason.ALLOWED
    return AddressDecision(reason == AddressReason.ALLOWED, reason)
