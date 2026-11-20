# Data model

All timestamps are UTC text in `YYYY-MM-DDTHH:MM:SSZ` form. Python records use aware datetimes. Money fields ending in `_piastres` store whole piastres. Enums are stored as text with CHECK constraints. Foreign keys are enabled on each connection.

## Enum values

Types below are defined in `bayline.models`. Their stored values are case-sensitive. Boolean fields use 0 or 1 in SQLite. `datetime` means an aware Python `datetime.datetime`.

| Type | Allowed values |
| --- | --- |
| `Team` | `customer_platform`, `customer_service` |
| `CustomerKind` | `merchant`, `recipient` |
| `Country` | `EG`, `AE`, `SA`, `JO` |
| `Service` | `express`, `standard`, `economy` |
| `Lane` | `domestic`, `international` |
| `GoodsCategory` | `general`, `clothing`, `electronics`, `documents`, `furniture`, `cosmetics`, `perishable`, `battery`, `hazardous` |
| `EventCode` | `CREATED`, `PICKED_UP`, `ARRIVED_HUB`, `DEPARTED_HUB`, `CUSTOMS_CLEARED`, `OUT_FOR_DELIVERY`, `DELIVERY_FAILED`, `DELIVERED`, `CUSTOMS_HOLD`, `RETURN_TO_SENDER`, `ADDRESS_CHANGED`, `RETURNED` |
| `ShipmentStatus` | `created`, `picked_up`, `in_transit`, `customs_hold`, `out_for_delivery`, `delivery_failed`, `delivered`, `returning`, `returned_to_sender` |
| `ReturnCause` | `damaged`, `wrong_item`, `not_wanted`, `late`, `other` |
| `ReturnStatus` | `open`, `approved`, `refused`, `received` |
| `ReturnReason` | `NOT_DELIVERED`, `MERCHANT_NOT_ON_PLAN`, `CATEGORY_EXCLUDED`, `ALREADY_OPEN`, `WINDOW_CLOSED`, `ALLOWED` |
| `ClaimKind` | `damage`, `loss`, `delay` |
| `ClaimStatus` | `open`, `approved`, `refused`, `paid` |
| `ClaimReason` | `INVALID_AMOUNT`, `ALREADY_EXISTS`, `NOT_DELIVERED`, `WINDOW_CLOSED`, `ELIGIBLE`, `DELIVERED`, `NOT_LATE_ENOUGH`, `SERVICE_NOT_COVERED` |
| `AddressStatus` | `applied`, `refused` |
| `AddressReason` | `TOO_LATE`, `CUSTOMS_HOLD`, `ALREADY_CHANGED`, `DIFFERENT_CITY`, `ALLOWED` |
| `Channel` | `email`, `web_form`, `chat` |
| `MessageStatus` | `new`, `answered`, `closed` |
| `Origin` | `generated`, `authored` |
| `Topic` | `status_question`, `delay`, `return`, `damage`, `address_change`, `claim_followup`, `billing`, `other` |
| `Missing` | `tracking_number`, `new_address`, `photos`, `amount`, `description_of_problem` |
| `Escalation` | `none`, `legal_threat`, `abusive`, `safety` |
| `DocumentKind` | `waybill`, `commercial_invoice` |
| `Layout` | `a`, `b`, `c` |
| `DelayClass` | `not_started`, `returned`, `on_time`, `late`, `very_late`, `lost_suspected`, `at_risk` |

The label arrays `topics` and `missing` contain values from `Topic` and `Missing`. Tracking-number arrays contain text. Optional values use `None` in Python and NULL in SQLite.

## `meta`

| Field | Python type |
| --- | --- |
| `key` | `str` |
| `value` | `str` |

## `staff`

| Field | Python type |
| --- | --- |
| `id` | `str` |
| `name` | `str` |
| `role` | `str` |
| `team` | `Team` |

## `customers`

| Field | Python type |
| --- | --- |
| `id` | `str` |
| `kind` | `CustomerKind` |
| `name` | `str` |
| `email` | `str` |
| `phone` | `str` |
| `city` | `str` |
| `country` | `Country` |
| `returns_plan` | `bool` |
| `created_at` | `datetime` |

## `shipments`

| Field | Python type |
| --- | --- |
| `tracking_number` | `str` |
| `merchant_id` | `str` |
| `recipient_id` | `str` |
| `service` | `Service` |
| `lane` | `Lane` |
| `origin_city` | `str` |
| `destination_city` | `str` |
| `destination_country` | `Country` |
| `destination_tz` | `str` |
| `address_line` | `str` |
| `goods_category` | `GoodsCategory` |
| `goods_description` | `str` |
| `pieces` | `int` |
| `weight_kg` | `float` |
| `declared_value_piastres` | `int` |
| `insured` | `bool` |
| `shipping_fee_piastres` | `int` |
| `created_at` | `datetime` |

## `tracking_events`

| Field | Python type |
| --- | --- |
| `id` | `int` |
| `tracking_number` | `str` |
| `occurred_at` | `datetime` |
| `code` | `EventCode` |
| `location` | `str` |
| `detail` | `str` |

## `return_cases`

| Field | Python type |
| --- | --- |
| `id` | `str` |
| `tracking_number` | `str` |
| `opened_at` | `datetime` |
| `reason` | `ReturnCause` |
| `status` | `ReturnStatus` |
| `decision_code` | `ReturnReason` |
| `decided_at` | `datetime | None` |
| `decided_by` | `str | None` |
| `note` | `str` |

## `claims`

| Field | Python type |
| --- | --- |
| `id` | `str` |
| `tracking_number` | `str` |
| `kind` | `ClaimKind` |
| `opened_at` | `datetime` |
| `claimed_piastres` | `int` |
| `status` | `ClaimStatus` |
| `decision_code` | `ClaimReason` |
| `payable_piastres` | `int` |
| `decided_at` | `datetime | None` |
| `decided_by` | `str | None` |
| `note` | `str` |

## `address_changes`

| Field | Python type |
| --- | --- |
| `id` | `str` |
| `tracking_number` | `str` |
| `requested_at` | `datetime` |
| `new_city` | `str` |
| `new_address_line` | `str` |
| `status` | `AddressStatus` |
| `decision_code` | `AddressReason` |
| `decided_by` | `str` |

## `messages`

| Field | Python type |
| --- | --- |
| `id` | `str` |
| `received_at` | `datetime` |
| `channel` | `Channel` |
| `from_name` | `str` |
| `from_email` | `str` |
| `customer_id` | `str | None` |
| `subject` | `str` |
| `body` | `str` |
| `status` | `MessageStatus` |
| `assigned_to` | `str | None` |
| `origin` | `Origin` |

## `message_labels`

| Field | Python type |
| --- | --- |
| `message_id` | `str` |
| `primary_topic` | `Topic` |
| `topics` | `tuple[str, ...]` |
| `tracking_numbers` | `tuple[str, ...]` |
| `invalid_tracking_mentions` | `tuple[str, ...]` |
| `missing` | `tuple[str, ...]` |
| `contains_instructions` | `bool` |
| `escalation` | `Escalation` |
| `labelled_by` | `str` |

## `replies`

| Field | Python type |
| --- | --- |
| `id` | `str` |
| `message_id` | `str` |
| `sent_at` | `datetime` |
| `author` | `str` |
| `body` | `str` |

## `documents`

| Field | Python type |
| --- | --- |
| `id` | `str` |
| `kind` | `DocumentKind` |
| `tracking_number` | `str` |
| `issued_at` | `datetime` |
| `layout` | `Layout` |
| `body` | `str` |

## Relationships and constraints

Shipments link a merchant and recipient to tracking events, returns, claims, address changes and documents. Messages link to a customer only when the sender email matches, ignoring case. Labels and replies belong to a message. Staff ids identify assignees, reply authors and decision makers.

Merchants use CUS-00001 through CUS-00020. Recipients start at CUS-00101 and never have a returns plan. Customer emails are unique and lowercase. Every shipment starts in Alexandria or Cairo. Pieces range from 1 to 10. Weight has one decimal place and cannot exceed 30 kg per piece. Declared value is nonnegative. The shipping fee is calculated by the pricing rule.

Labels store sorted JSON arrays without duplicates. Missing optional links and decision times are NULL. Refused claims pay zero. Documents are plain-text waybills or commercial invoices in layout a, b or c. A shipment without events has created status. ADDRESS_CHANGED does not change its status.

The snapshot metadata contains as_of 2026-11-02T07:00:00Z, seed 20261101 and generator_version 3. Scenarios stay in generator memory and are not database fields. See schema.sql for every enum value and constraint.
