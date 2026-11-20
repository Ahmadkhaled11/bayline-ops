"""Tracking events are ordered by time, then by id."""

from datetime import datetime

from .models import EventCode, ShipmentStatus, TrackingEvent

EVENT_STATUS = {
    EventCode.CREATED: ShipmentStatus.CREATED,
    EventCode.PICKED_UP: ShipmentStatus.PICKED_UP,
    EventCode.ARRIVED_HUB: ShipmentStatus.IN_TRANSIT,
    EventCode.DEPARTED_HUB: ShipmentStatus.IN_TRANSIT,
    EventCode.CUSTOMS_CLEARED: ShipmentStatus.IN_TRANSIT,
    EventCode.OUT_FOR_DELIVERY: ShipmentStatus.OUT_FOR_DELIVERY,
    EventCode.DELIVERY_FAILED: ShipmentStatus.DELIVERY_FAILED,
    EventCode.DELIVERED: ShipmentStatus.DELIVERED,
    EventCode.CUSTOMS_HOLD: ShipmentStatus.CUSTOMS_HOLD,
    EventCode.RETURN_TO_SENDER: ShipmentStatus.RETURNING,
    EventCode.RETURNED: ShipmentStatus.RETURNED_TO_SENDER,
    EventCode.ADDRESS_CHANGED: None,
}


def events_at(events: list[TrackingEvent], at: datetime) -> list[TrackingEvent]:
    return sorted((e for e in events if e.occurred_at <= at), key=lambda e: (e.occurred_at, e.id))


def current_status(events: list[TrackingEvent], at: datetime | None = None) -> ShipmentStatus:
    ordered = sorted(events, key=lambda e: (e.occurred_at, e.id))
    status = ShipmentStatus.CREATED
    for event in ordered:
        if at is None or event.occurred_at <= at:
            status = EVENT_STATUS[event.code] or status
    return status
