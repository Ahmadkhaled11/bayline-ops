"""Transit estimates use the desk calendar and local dates."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..business_days import add_business_days, business_days_after, is_business_day
from ..models import DelayClass, DelayResult, Shipment, TrackingEvent
from ..status import current_status, events_at
from ..timeutil import local_date

TRANSIT_DAYS = {
    "domestic": {"express": 1, "standard": 3, "economy": 5},
    "international": {"express": 3, "standard": 6, "economy": 10},
}


def promised_date(shipment: Shipment, picked_up_at: datetime):
    pickup = picked_up_at.astimezone(ZoneInfo("Africa/Cairo"))
    start = pickup.date()
    if not is_business_day(start) or pickup.time() >= time(16):
        start = add_business_days(start, 1)
    return add_business_days(start, TRANSIT_DAYS[shipment.lane][shipment.service])


def classify_delay(shipment: Shipment, events: list[TrackingEvent], at: datetime) -> DelayResult:
    history = events_at(events, at)
    pickups = [e for e in history if e.code == "PICKED_UP"]
    if not pickups:
        return DelayResult(DelayClass.NOT_STARTED, None, 0)
    promised = promised_date(shipment, pickups[0].occurred_at)
    status = current_status(history)
    if status in ("returning", "returned_to_sender"):
        return DelayResult(DelayClass.RETURNED, promised, 0)
    delivered = [e for e in history if e.code == "DELIVERED"]
    judged_at = delivered[-1].occurred_at if delivered else at
    day = local_date(judged_at, shipment.destination_tz)
    late = business_days_after(promised, day)
    scans = [event for event in history if event.code != "ADDRESS_CHANGED"]
    if not delivered and status != "customs_hold" and at - scans[-1].occurred_at >= timedelta(days=7):
        return DelayResult(DelayClass.LOST_SUSPECTED, promised, late)
    if late:
        return DelayResult(DelayClass.LATE if late <= 2 else DelayClass.VERY_LATE, promised, late)
    risk = not delivered and ((day == promised and status != "out_for_delivery")
                              or status in ("customs_hold", "delivery_failed"))
    return DelayResult(DelayClass.AT_RISK if risk else DelayClass.ON_TIME, promised, late)
