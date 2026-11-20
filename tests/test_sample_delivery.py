"""Parcel replies and shipment choices follow the available tracking history."""

import pytest

from bayline.rules.delays import classify_delay
from bayline.sample.generate import AS_OF, _message_weight
from bayline.sample.texts import render_reply
from bayline.status import current_status, events_at
from bayline.timeutil import format_day, local_date, parse_utc
from tests.helpers import history, shipment


@pytest.mark.parametrize('pickup,service,at,promised,tense', [
    ('2026-10-25T07:00:00Z', 'standard', '2026-10-28T09:00:00Z', 'Wednesday 28 October 2026', 'is'),
    ('2026-10-28T07:00:00Z', 'express', '2026-10-30T09:00:00Z', 'Thursday 29 October 2026', 'was'),
])
@pytest.mark.parametrize('secondary', [False, True])
def test_out_for_delivery_without_business_day_delay(pickup, service, at, promised, tense, secondary):
    parcel = shipment(service=service)
    scans = history(('PICKED_UP', pickup), ('OUT_FOR_DELIVERY', at))
    sent = parse_utc(at)
    decision = classify_delay(parcel, scans, sent)
    assert decision.late_business_days == 0
    day = format_day(local_date(sent, parcel.destination_tz))
    answer = (f'Your parcel {parcel.tracking_number} went out for delivery in Cairo on {day}. '
              f'Its promised date {tense} {promised}.')
    step = 'Please make sure that someone can receive it.'
    body = render_reply('status_question', decision, customer_name='Nadia Farouk', shipment=parcel,
                        events=scans, at=sent, secondary=[('other', None)] if secondary else ())
    assert body.split('\n\n')[1] == answer + (' ' + step if secondary else '')
    if not secondary:
        assert body.split('\n\n')[2] == step


@pytest.mark.parametrize('at,day,days', [
    ('2026-10-29T09:00:00Z', 'Thursday 29 October 2026', '1 business day'),
    ('2026-11-01T09:00:00Z', 'Sunday 1 November 2026', '2 business days'),
])
def test_out_for_delivery_with_business_day_delay(at, day, days):
    parcel = shipment()
    scans = history(('PICKED_UP', '2026-10-25T07:00:00Z'), ('OUT_FOR_DELIVERY', at))
    sent = parse_utc(at)
    decision = classify_delay(parcel, scans, sent)
    body = render_reply('delay', decision, customer_name='Nadia Farouk', shipment=parcel,
                        events=scans, at=sent)
    assert body == (f'Hello Nadia,\n\nYour parcel {parcel.tracking_number} went out for delivery in Cairo on {day}. '
                    f'Its promised date was Wednesday 28 October 2026, so it is {days} late. We are sorry for the delay.'
                    '\n\nPlease make sure that someone can receive it.\n\nBayline Cargo Customer Service')


@pytest.mark.parametrize('at,day,tense', [
    ('2026-10-28T09:00:00Z', 'Wednesday 28 October 2026', 'is'),
    ('2026-10-29T09:00:00Z', 'Thursday 29 October 2026', 'was'),
])
def test_failed_delivery_names_the_attempt_and_next_step(at, day, tense):
    parcel = shipment()
    scans = history(('PICKED_UP', '2026-10-25T07:00:00Z'), ('DELIVERY_FAILED', at))
    sent = parse_utc(at)
    decision = classify_delay(parcel, scans, sent)
    body = render_reply('status_question', decision, customer_name='Nadia Farouk', shipment=parcel,
                        events=scans, at=sent)
    assert body == (f'Hello Nadia,\n\nWe tried to deliver your parcel {parcel.tracking_number} in Cairo on {day}, '
                    f'and the delivery did not succeed. Its promised date {tense} Wednesday 28 October 2026.'
                    '\n\nPlease reply and tell us when someone can receive it, or send us a corrected address in Cairo. '
                    'We will then agree the next attempt with you.\n\nBayline Cargo Customer Service')


def test_possibly_lost_takes_precedence_over_out_for_delivery():
    parcel = shipment()
    scans = history(('PICKED_UP', '2026-10-18T07:00:00Z'), ('OUT_FOR_DELIVERY', '2026-10-20T07:00:00Z'))
    decision = classify_delay(parcel, scans, AS_OF)
    assert decision.delay_class == 'lost_suspected'
    body = render_reply('status_question', decision, customer_name='Nadia Farouk', shipment=parcel,
                        events=scans, at=AS_OF)
    assert 'Your parcel BYL260411871 may be lost.' in body
    assert 'We have asked the delivery team to search for it.' in body
    assert 'went out for delivery' not in body


def test_sample_out_for_delivery_status_paragraphs_name_the_scan(sample):
    labels = {row.message_id: row for row in sample.tables['message_labels']}
    parcels = {row.tracking_number: row for row in sample.tables['shipments']}
    checked = []
    for reply in sample.tables['replies']:
        label = labels[reply.message_id]
        if not label.tracking_numbers or not set(label.topics) & {'status_question', 'delay'}:
            continue
        parcel = parcels[label.tracking_numbers[0]]
        scans = events_at([row for row in sample.tables['tracking_events']
                           if row.tracking_number == parcel.tracking_number], reply.sent_at)
        if current_status(scans) == 'out_for_delivery':
            assert any(p.startswith(f'Your parcel {parcel.tracking_number} went out for delivery in')
                       for p in reply.body.split('\n\n')), reply.id
            checked.append(reply.id)
    assert checked


@pytest.mark.parametrize('delivered,expected', [
    ('2026-09-10T08:00:00Z', 30 * 86400 - 3600),
    ('2026-08-04T08:00:00Z', 2 * 86400 + 11 * 3600),
    ('2026-08-01T08:00:00Z', 0),
    ('2026-10-30T08:00:00Z', 2 * 86400 + 22 * 3600),
])
def test_shipment_weight_is_its_window_seconds_inside_the_message_period(delivered, expected):
    assert _message_weight(['damage'], shipment(), parse_utc(delivered)) == expected


def test_shipment_weight_is_zero_without_a_delivery_for_a_damage_question():
    assert _message_weight(['damage'], shipment(), None) == 0
