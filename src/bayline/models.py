"""Immutable database records and rule results."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Team(StrEnum):
    CUSTOMER_PLATFORM = "customer_platform"
    CUSTOMER_SERVICE = "customer_service"


class CustomerKind(StrEnum):
    MERCHANT = "merchant"
    RECIPIENT = "recipient"


class Country(StrEnum):
    EG = "EG"
    AE = "AE"
    SA = "SA"
    JO = "JO"


class Service(StrEnum):
    EXPRESS = "express"
    STANDARD = "standard"
    ECONOMY = "economy"


class Lane(StrEnum):
    DOMESTIC = "domestic"
    INTERNATIONAL = "international"


class GoodsCategory(StrEnum):
    GENERAL = "general"
    CLOTHING = "clothing"
    ELECTRONICS = "electronics"
    DOCUMENTS = "documents"
    FURNITURE = "furniture"
    COSMETICS = "cosmetics"
    PERISHABLE = "perishable"
    BATTERY = "battery"
    HAZARDOUS = "hazardous"


class EventCode(StrEnum):
    CREATED = "CREATED"
    PICKED_UP = "PICKED_UP"
    ARRIVED_HUB = "ARRIVED_HUB"
    DEPARTED_HUB = "DEPARTED_HUB"
    CUSTOMS_CLEARED = "CUSTOMS_CLEARED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    DELIVERED = "DELIVERED"
    CUSTOMS_HOLD = "CUSTOMS_HOLD"
    RETURN_TO_SENDER = "RETURN_TO_SENDER"
    ADDRESS_CHANGED = "ADDRESS_CHANGED"
    RETURNED = "RETURNED"


class ShipmentStatus(StrEnum):
    CREATED = "created"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    CUSTOMS_HOLD = "customs_hold"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERY_FAILED = "delivery_failed"
    DELIVERED = "delivered"
    RETURNING = "returning"
    RETURNED_TO_SENDER = "returned_to_sender"


class ReturnCause(StrEnum):
    DAMAGED = "damaged"
    WRONG_ITEM = "wrong_item"
    NOT_WANTED = "not_wanted"
    LATE = "late"
    OTHER = "other"


class ReturnStatus(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    REFUSED = "refused"
    RECEIVED = "received"


class ReturnReason(StrEnum):
    NOT_DELIVERED = "NOT_DELIVERED"
    MERCHANT_NOT_ON_PLAN = "MERCHANT_NOT_ON_PLAN"
    CATEGORY_EXCLUDED = "CATEGORY_EXCLUDED"
    ALREADY_OPEN = "ALREADY_OPEN"
    WINDOW_CLOSED = "WINDOW_CLOSED"
    ALLOWED = "ALLOWED"


class ClaimKind(StrEnum):
    DAMAGE = "damage"
    LOSS = "loss"
    DELAY = "delay"


class ClaimStatus(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    REFUSED = "refused"
    PAID = "paid"


class ClaimReason(StrEnum):
    INVALID_AMOUNT = "INVALID_AMOUNT"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    NOT_DELIVERED = "NOT_DELIVERED"
    WINDOW_CLOSED = "WINDOW_CLOSED"
    ELIGIBLE = "ELIGIBLE"
    DELIVERED = "DELIVERED"
    NOT_LATE_ENOUGH = "NOT_LATE_ENOUGH"
    SERVICE_NOT_COVERED = "SERVICE_NOT_COVERED"


class AddressStatus(StrEnum):
    APPLIED = "applied"
    REFUSED = "refused"


class AddressReason(StrEnum):
    TOO_LATE = "TOO_LATE"
    CUSTOMS_HOLD = "CUSTOMS_HOLD"
    ALREADY_CHANGED = "ALREADY_CHANGED"
    DIFFERENT_CITY = "DIFFERENT_CITY"
    ALLOWED = "ALLOWED"


class Channel(StrEnum):
    EMAIL = "email"
    WEB_FORM = "web_form"
    CHAT = "chat"


class MessageStatus(StrEnum):
    NEW = "new"
    ANSWERED = "answered"
    CLOSED = "closed"


class Origin(StrEnum):
    GENERATED = "generated"
    AUTHORED = "authored"


class Topic(StrEnum):
    STATUS_QUESTION = "status_question"
    DELAY = "delay"
    RETURN = "return"
    DAMAGE = "damage"
    ADDRESS_CHANGE = "address_change"
    CLAIM_FOLLOWUP = "claim_followup"
    BILLING = "billing"
    OTHER = "other"


class Missing(StrEnum):
    TRACKING_NUMBER = "tracking_number"
    NEW_ADDRESS = "new_address"
    PHOTOS = "photos"
    AMOUNT = "amount"
    DESCRIPTION_OF_PROBLEM = "description_of_problem"


class Escalation(StrEnum):
    NONE = "none"
    LEGAL_THREAT = "legal_threat"
    ABUSIVE = "abusive"
    SAFETY = "safety"


class DocumentKind(StrEnum):
    WAYBILL = "waybill"
    COMMERCIAL_INVOICE = "commercial_invoice"


class Layout(StrEnum):
    A = "a"
    B = "b"
    C = "c"


class DelayClass(StrEnum):
    NOT_STARTED = "not_started"
    RETURNED = "returned"
    ON_TIME = "on_time"
    LATE = "late"
    VERY_LATE = "very_late"
    LOST_SUSPECTED = "lost_suspected"
    AT_RISK = "at_risk"


@dataclass(frozen=True)
class Meta:
    key: str
    value: str


@dataclass(frozen=True)
class Staff:
    id: str
    name: str
    role: str
    team: Team


@dataclass(frozen=True)
class Customer:
    id: str
    kind: CustomerKind
    name: str
    email: str
    phone: str
    city: str
    country: Country
    returns_plan: bool
    created_at: datetime


@dataclass(frozen=True)
class Shipment:
    tracking_number: str
    merchant_id: str
    recipient_id: str
    service: Service
    lane: Lane
    origin_city: str
    destination_city: str
    destination_country: Country
    destination_tz: str
    address_line: str
    goods_category: GoodsCategory
    goods_description: str
    pieces: int
    weight_kg: float
    declared_value_piastres: int
    insured: bool
    shipping_fee_piastres: int
    created_at: datetime


@dataclass(frozen=True)
class TrackingEvent:
    id: int
    tracking_number: str
    occurred_at: datetime
    code: EventCode
    location: str
    detail: str


@dataclass(frozen=True)
class ReturnCase:
    id: str
    tracking_number: str
    opened_at: datetime
    reason: ReturnCause
    status: ReturnStatus
    decision_code: ReturnReason
    decided_at: datetime | None
    decided_by: str | None
    note: str


@dataclass(frozen=True)
class Claim:
    id: str
    tracking_number: str
    kind: ClaimKind
    opened_at: datetime
    claimed_piastres: int
    status: ClaimStatus
    decision_code: ClaimReason
    payable_piastres: int
    decided_at: datetime | None
    decided_by: str | None
    note: str


@dataclass(frozen=True)
class AddressChange:
    id: str
    tracking_number: str
    requested_at: datetime
    new_city: str
    new_address_line: str
    status: AddressStatus
    decision_code: AddressReason
    decided_by: str


@dataclass(frozen=True)
class Message:
    id: str
    received_at: datetime
    channel: Channel
    from_name: str
    from_email: str
    customer_id: str | None
    subject: str
    body: str
    status: MessageStatus
    assigned_to: str | None
    origin: Origin


@dataclass(frozen=True)
class MessageLabel:
    message_id: str
    primary_topic: Topic
    topics: tuple[str, ...]
    tracking_numbers: tuple[str, ...]
    invalid_tracking_mentions: tuple[str, ...]
    missing: tuple[str, ...]
    contains_instructions: bool
    escalation: Escalation
    labelled_by: str


@dataclass(frozen=True)
class Reply:
    id: str
    message_id: str
    sent_at: datetime
    author: str
    body: str


@dataclass(frozen=True)
class Document:
    id: str
    kind: DocumentKind
    tracking_number: str
    issued_at: datetime
    layout: Layout
    body: str


@dataclass(frozen=True)
class DelayResult:
    delay_class: DelayClass
    promised: date | None
    late_business_days: int


@dataclass(frozen=True)
class ReturnDecision:
    allowed: bool
    reason: ReturnReason
    day_number: int | None
    last_day: date | None


@dataclass(frozen=True)
class ClaimDecision:
    eligible: bool
    reason: ClaimReason
    payable_piastres: int


@dataclass(frozen=True)
class AddressDecision:
    allowed: bool
    reason: AddressReason

TABLE_MODELS = {
    "meta": Meta,
    "staff": Staff,
    "customers": Customer,
    "shipments": Shipment,
    "tracking_events": TrackingEvent,
    "return_cases": ReturnCase,
    "claims": Claim,
    "address_changes": AddressChange,
    "messages": Message,
    "message_labels": MessageLabel,
    "replies": Reply,
    "documents": Document,
}
