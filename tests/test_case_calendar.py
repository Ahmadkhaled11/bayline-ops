from collections import defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from bayline.business_days import HOLIDAYS_2026, add_business_days
from bayline.rules.claims import check_claim
from bayline.rules.delays import classify_delay
from bayline.rules.returns import check_return
from bayline.sample.anchors import ANCHOR_NUMBERS
from bayline.sample.catalog import MERCHANT_PRODUCTS, PRODUCTS
from bayline.sample.generate import AS_OF

CAIRO = ZoneInfo("Africa/Cairo")


def _histories(sample):
    shipments = {row.tracking_number: row for row in sample.tables["shipments"]}
    customers = {row.id: row for row in sample.tables["customers"]}
    events = defaultdict(list)
    for event in sample.tables["tracking_events"]:
        events[event.tracking_number].append(event)
    return shipments, customers, events


def _cases(sample):
    return sample.tables["return_cases"] + sample.tables["claims"]


def _business_deadline(opened, days):
    local = opened.astimezone(CAIRO)
    return datetime.combine(add_business_days(local.date(), days), local.time(), CAIRO)


def test_case_requests_have_distinct_seconds_and_follow_delivery(sample):
    _, _, events = _histories(sample)
    cases = _cases(sample)
    opening_seconds = [row.opened_at.replace(microsecond=0) for row in cases]
    assert len(opening_seconds) == len(set(opening_seconds))
    for row in cases:
        delivered = [e.occurred_at for e in events[row.tracking_number] if e.code == "DELIVERED"]
        if delivered:
            gap = row.opened_at - delivered[-1]
            assert gap > timedelta(0), row.id


def test_decisions_use_the_desk_calendar_and_follow_requests(sample):
    for row in _cases(sample):
        if row.decided_at is None:
            assert row.status == "open", row.id
            continue
        if row.status == "refused":
            assert row.decided_at == row.opened_at, row.id
            assert row.decided_by in ("hany.nassar", "dina.fawzy", "omar.elbanna"), row.id
            continue
        local = row.decided_at.astimezone(CAIRO)
        assert local.weekday() not in (4, 5), row.id
        assert local.date() not in HOLIDAYS_2026, row.id
        assert time(8) <= local.time() < time(20), row.id
        assert row.opened_at < row.decided_at <= AS_OF, row.id
        assert row.decided_at <= _business_deadline(row.opened_at, 3), row.id


def test_approved_damage_claims_allow_at_least_one_business_day(sample):
    claims = [row for row in sample.tables["claims"]
              if row.kind == "damage" and row.status == "approved"]
    assert claims
    for row in claims:
        assert row.decided_at is not None
        assert row.decided_at >= _business_deadline(row.opened_at, 1), row.id


def test_loss_claims_open_on_distinct_days_after_the_loss_threshold(sample):
    shipments, _, events = _histories(sample)
    claims = [row for row in sample.tables["claims"] if row.kind == "loss"]
    assert len(claims) == 6
    assert len({row.opened_at.astimezone(CAIRO).date() for row in claims}) == 6
    for row in claims:
        history = events[row.tracking_number]
        scans = [e for e in history if e.code != "ADDRESS_CHANGED"]
        assert max(e.occurred_at for e in scans) + timedelta(days=7) <= row.opened_at < AS_OF
        result = classify_delay(shipments[row.tracking_number], history, row.opened_at)
        assert result.delay_class == "lost_suspected", row.id


def test_stored_answers_remain_correct_at_opening_and_decision(sample):
    shipments, customers, events = _histories(sample)
    for row in sample.tables["return_cases"]:
        shipment = shipments[row.tracking_number]
        for at in {row.opened_at, row.decided_at} - {None}:
            prior = [other for other in sample.tables["return_cases"]
                     if other.id != row.id and other.opened_at <= at]
            answer = check_return(shipment, events[row.tracking_number],
                                  customers[shipment.merchant_id], prior, at)
            assert (answer.reason, answer.allowed) == (row.decision_code, row.status != "refused"), (row.id, at)
    for row in sample.tables["claims"]:
        shipment = shipments[row.tracking_number]
        for at in {row.opened_at, row.decided_at} - {None}:
            prior = [other for other in sample.tables["claims"]
                     if other.id != row.id and other.opened_at <= at]
            answer = check_claim(shipment, events[row.tracking_number], row.kind,
                                 row.claimed_piastres, prior, at)
            assert (answer.reason, answer.eligible, answer.payable_piastres) == (
                row.decision_code, row.status != "refused", row.payable_piastres), (row.id, at)


def test_case_numbers_follow_request_time(sample):
    for table in ("return_cases", "claims"):
        rows = sorted(sample.tables[table], key=lambda row: row.id)
        assert [row.opened_at for row in rows] == sorted(row.opened_at for row in rows)


def test_customer_numbers_follow_join_time_and_accounts_exist_at_booking(sample):
    customers = sorted(sample.tables["customers"], key=lambda row: row.id)
    joined = [row.created_at for row in customers]
    assert joined == sorted(joined)
    assert all(AS_OF - timedelta(days=730) <= at <= AS_OF for at in joined)
    first_shipments = {}
    for shipment in sample.tables["shipments"]:
        for customer_id in (shipment.merchant_id, shipment.recipient_id):
            first_shipments[customer_id] = min(first_shipments.get(customer_id, AS_OF), shipment.created_at)
    for customer in customers:
        if customer.id in first_shipments:
            assert customer.created_at <= first_shipments[customer.id], customer.id


def test_goods_belong_to_the_merchant_and_meet_product_limits(sample):
    fixed = dict(zip(ANCHOR_NUMBERS, (
        "jacket", "dress", "smart watch", "phone", "laptop charger", "tablet", "power bank",
        "coffee table", "wireless headphones", "cotton scarf", "linen trousers", "cotton sweater",
        "laptop", "two shirts", "dress"), strict=True))
    for shipment in sample.tables["shipments"]:
        if shipment.tracking_number in fixed:
            assert shipment.goods_description == fixed[shipment.tracking_number]
        else:
            merchant = next(c for c in sample.tables["customers"] if c.id == shipment.merchant_id)
            assert shipment.goods_description in MERCHANT_PRODUCTS[merchant.name]
            product = next(p for p in PRODUCTS if p.description == shipment.goods_description)
            assert shipment.goods_category == product.category
            assert 1 <= shipment.pieces <= product.max_pieces
            assert round(product.piece_kg[0] * shipment.pieces, 1) <= shipment.weight_kg <= round(product.piece_kg[1] * shipment.pieces, 1)
            assert shipment.weight_kg == round(shipment.weight_kg, 1)
            per_piece_value = shipment.declared_value_piastres // (100 * shipment.pieces)
            assert shipment.declared_value_piastres == per_piece_value * 100 * shipment.pieces
            assert product.piece_egp[0] <= per_piece_value <= product.piece_egp[1]


def test_refused_cross_city_address_requests_name_a_different_city(sample):
    shipments, _, _ = _histories(sample)
    changes = [row for row in sample.tables["address_changes"] if row.decision_code == "DIFFERENT_CITY"]
    assert len(changes) == 6
    assert all(row.status == "refused" and row.new_city != shipments[row.tracking_number].destination_city
               for row in changes)
