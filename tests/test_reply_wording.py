"""Replies give the known answer once, at the time they were sent."""

from dataclasses import replace
from datetime import timedelta

import pytest

from bayline.models import Claim
from bayline.rules.address import check_address_change
from bayline.rules.claims import check_claim
from bayline.rules.delays import classify_delay
from bayline.rules.returns import check_return
from bayline.sample.generate import AS_OF
from bayline.sample.texts import TRACKING_REQUESTS, render_reply
from bayline.timeutil import format_day, local_date, parse_utc
from tests.helpers import MERCHANT, history, shipment


def test_replies_to_return_or_damage_questions_do_not_suggest_non_delivery(sample):
    labels = {label.message_id: label for label in sample.tables["message_labels"]}
    for reply in sample.tables["replies"]:
        if set(labels[reply.message_id].topics) & {"return", "damage"}:
            assert "has not reached you" not in reply.body, reply.id


@pytest.mark.parametrize("topic", ["return", "damage"])
@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("tracking_first", [False, True])
def test_delivered_tracking_answer_has_no_next_step_with_return_or_damage(topic, late, tracking_first):
    parcel = shipment()
    scans = history(("PICKED_UP", "2026-10-25T07:00:00Z"),
                    ("DELIVERED", "2026-11-01T07:00:00Z"))
    delay = replace(classify_delay(parcel, scans, AS_OF), late_business_days=1 if late else 0)
    decision = (check_return(parcel, scans, MERCHANT, [], AS_OF) if topic == "return"
                else check_claim(parcel, scans, "damage", 100, [], AS_OF))
    questions = [("delay", delay), (topic, decision)]
    if not tracking_first:
        questions.reverse()
    for variant in range(4):
        body = render_reply(*questions[0], customer_name="Nadia Farouk", shipment=parcel,
                            events=scans, at=AS_OF, variant=variant, secondary=questions[1:])
        paragraph = next(p for p in body.split("\n\n") if "Its promised date was" in p)
        assert paragraph.endswith("We are sorry for the delay." if late else "so it arrived on time.")


def test_tracking_request_variants_use_the_complete_wording():
    assert TRACKING_REQUESTS == (
        "Please send us the tracking number for your parcel so that we can check it. It is BYL followed by 9 digits, and it is in the merchant's email.",
        "We need the tracking number to look up your parcel. It is BYL followed by 9 digits. Please reply with it.",
        "Please copy the tracking number from the merchant's email and reply with it. It is BYL followed by 9 digits.",
        "We can check this once we have the tracking number. It is BYL followed by 9 digits, and the merchant's email shows it.",
    )


def test_every_reply_has_distinct_paragraphs_and_opening_sentences(sample):
    for reply in sample.tables["replies"]:
        paragraphs = reply.body.split("\n\n")
        first_sentences = [paragraph.partition(".")[0] for paragraph in paragraphs]
        assert len(paragraphs) == len(set(paragraphs)), reply.id
        assert len(first_sentences) == len(set(first_sentences)), reply.id


@pytest.mark.parametrize("variant", range(4))
@pytest.mark.parametrize("invalid_number", [None, "byl260411872"])
def test_number_request_is_complete_once_for_two_questions(variant, invalid_number):
    body = render_reply("return", None, customer_name="Nadia Farouk", shipment=shipment(),
        events=[], at=AS_OF, variant=variant, has_number=False,
        invalid_number=invalid_number, secondary=[("damage", None)])
    request = (f"The number you sent, {invalid_number}, is not a valid Bayline tracking number. "
               "One of the digits may be wrong. Please copy the number again from the merchant's email and reply with it."
               if invalid_number else TRACKING_REQUESTS[variant])
    assert body == ("Hello Nadia,\n\n" + request
                    + "\n\nBayline Cargo Customer Service")


@pytest.mark.parametrize("primary", ["other", "return"])
def test_question_without_number_still_gets_its_own_answer(primary):
    secondary = "return" if primary == "other" else "other"
    body = render_reply(primary, None, customer_name="Nadia Farouk", shipment=shipment(),
        events=[], at=AS_OF, has_number=False, secondary=[(secondary, None)])
    assert body.count("BYL followed by 9 digits") == 1
    assert len(body.split("\n\n")) == 4
    assert ("Our desk is open" in body if primary == "other" else "You can reach the desk" in body)


@pytest.mark.parametrize("primary,secondary", [("delay", "status_question"), ("status_question", "delay")])
def test_delay_and_status_share_one_answer_and_next_step(primary, secondary):
    parcel = shipment()
    decision = classify_delay(parcel, [], AS_OF)
    body = render_reply(primary, decision, customer_name="Nadia Farouk", shipment=parcel,
        events=[], at=AS_OF, secondary=[(secondary, decision)])
    assert body == (f"Hello Nadia,\n\nYour parcel {parcel.tracking_number} has not been picked up from the merchant yet. "
        "There is no pick-up scan as of Monday 2 November 2026, so we cannot give a delivery date yet. "
        "Please ask the merchant when they plan to hand it over.\n\nBayline Cargo Customer Service")


def test_status_does_not_say_no_action_when_the_address_needs_details():
    parcel = shipment()
    scans = history(("PICKED_UP", "2026-10-29T07:00:00Z"))
    delay = classify_delay(parcel, scans, AS_OF)
    address = check_address_change(parcel, scans, parcel.destination_city, [], AS_OF)
    assert delay.delay_class == "on_time" and address.allowed
    body = render_reply("status_question", delay, customer_name="Nadia Farouk", shipment=parcel,
        events=scans, at=AS_OF, secondary=[("address_change", address)])
    assert "You do not need to do anything." not in body
    assert "Please make sure that someone can receive it on the day." in body
    assert "Send us the new street address and flat number" in body


@pytest.mark.parametrize("status,detail,next_step", [
    ("open", "It is still with the claims team.", "You do not need to do anything. The claims team will write to you with the decision."),
    ("approved", "Our records show it as approved.", "The claims team will write to you about the next step."),
    ("paid", "Our records show it as paid.", "If anything about it is unclear, reply and we will check."),
    ("refused", "It was refused because it was made more than 14 days after delivery.", "If you think the decision is wrong, reply and tell us why, and we will pass it to the claims team."),
])
def test_one_claim_followup_uses_its_record(status, detail, next_step):
    parcel = shipment()
    claim = Claim("CLM-00001", parcel.tracking_number, "damage", AS_OF - timedelta(days=3),
        100, status, "WINDOW_CLOSED" if status == "refused" else "ELIGIBLE", 0 if status == "refused" else 100, None if status == "open" else AS_OF,
        None if status == "open" else "reem.adel", "")
    body = render_reply("claim_followup", None, customer_name="Nadia Farouk", shipment=parcel,
        events=[], at=AS_OF, claims=[claim])
    assert body == (f"Hello Nadia,\n\nYour claim CLM-00001 for {parcel.tracking_number} was opened on Friday 30 October 2026. "
        + detail + "\n\n" + next_step + "\n\nBayline Cargo Customer Service")


def test_claim_followup_observes_opening_and_decision_boundaries():
    parcel = shipment()
    claim = Claim("CLM-00001", parcel.tracking_number, "damage", AS_OF, 100,
        "refused", "WINDOW_CLOSED", 0, AS_OF + timedelta(hours=2), "reem.adel", "")
    def reply(at, claims):
        return render_reply("claim_followup", None, customer_name="Nadia Farouk", shipment=parcel,
                            events=[], at=at, claims=claims)
    before = reply(AS_OF - timedelta(seconds=1), [claim])
    assert before == (f"Hello Nadia,\n\nWe have no claim on record for {parcel.tracking_number}.\n\n"
        "If you sent one, please reply with the date you sent it. To open a claim now, reply and tell us what happened to the parcel."
        "\n\nBayline Cargo Customer Service")
    assert "It is still with the claims team." in reply(AS_OF, [claim])
    assert "It was refused because it was made more than 14 days after delivery." in reply(claim.decided_at, [claim])
    assert "It is still with the claims team." in reply(claim.decided_at - timedelta(seconds=1), [claim])
    second = replace(claim, id="CLM-00002", opened_at=AS_OF + timedelta(hours=1))
    assert "more than one claim" not in reply(AS_OF, [claim, second])
    assert "This shipment has more than one claim" in reply(second.opened_at, [claim, second])
    unrelated = replace(second, tracking_number="BYL260415328", opened_at=AS_OF)
    assert "more than one claim" not in reply(AS_OF, [claim, unrelated])


@pytest.mark.parametrize("offset,tense", [(-1, "was"), (0, "is"), (1, "is")])
@pytest.mark.parametrize("customs", [False, True])
def test_promised_date_tense_uses_reply_day(offset, tense, customs):
    parcel = shipment()
    scans = history(("PICKED_UP", "2026-10-25T07:00:00Z"),
                    ("ARRIVED_HUB", "2026-10-26T07:00:00Z"))
    if customs:
        scans += history(("CUSTOMS_HOLD", "2026-10-27T07:00:00Z"))
    at = parse_utc("2026-10-28T08:00:00Z")
    promised = local_date(at, parcel.destination_tz) + timedelta(days=offset)
    decision = replace(classify_delay(parcel, scans, at), promised=promised, delay_class="on_time")
    body = render_reply("delay", decision, customer_name="Nadia Farouk", shipment=parcel,
                        events=scans, at=at)
    assert f"Its promised date {tense} {format_day(promised)}." in body
    assert f"Its promised date {'is' if tense == 'was' else 'was'} " not in body


@pytest.mark.parametrize("insured,value,sentence", [
    (False, 299999, "The shipment was not insured. The most we can pay is its declared value, 2,999.99 EGP."),
    (False, 300000, "The shipment was not insured, so the most we can pay is 3,000 EGP."),
    (False, 850000, "The shipment was not insured, so the most we can pay is 3,000 EGP."),
    (True, 850000, "The shipment was insured, so the most we can pay is its declared value, 8,500 EGP."),
])
def test_damage_limit_sentence_is_exact_at_policy_boundary(insured, value, sentence):
    parcel = shipment(insured=insured, declared_value_piastres=value)
    scans = history(("DELIVERED", "2026-11-01T07:00:00Z"))
    decision = check_claim(parcel, scans, "damage", value, [], AS_OF)
    body = render_reply("damage", decision, customer_name="Nadia Farouk", shipment=parcel,
                        events=scans, at=AS_OF)
    assert sentence in body


@pytest.mark.parametrize("topic,days", [("return", 30), ("damage", 14)])
def test_delivery_day_uses_calendar_wording(topic, days):
    parcel = shipment(destination_city="Dubai")
    scans = history(("DELIVERED", "2026-11-01T20:05:00Z"))
    at = parse_utc("2026-11-02T07:00:00Z")
    decision = (check_return(parcel, scans, MERCHANT, [], at) if topic == "return"
                else check_claim(parcel, scans, "damage", 100, [], at))
    body = render_reply(topic, decision, customer_name="Nadia Farouk", shipment=parcel,
                        events=scans, at=at)
    assert "Monday 2 November 2026" in body and "Sunday 1 November 2026" not in body
    assert f"so the {days} days" in body and "have only just started." in body
    assert "day 0" not in body


@pytest.mark.parametrize("status", ["open", "approved", "paid"])
def test_existing_damage_claim_does_not_claim_it_is_open(status):
    parcel = shipment()
    scans = history(("DELIVERED", "2026-11-01T07:00:00Z"))
    claim = Claim("CLM-00001", parcel.tracking_number, "damage", AS_OF - timedelta(hours=2),
        100, status, "ELIGIBLE", 100, None, None, "")
    decision = check_claim(parcel, scans, "damage", 100, [claim], AS_OF)
    body = render_reply("damage", decision, customer_name="Nadia Farouk", shipment=parcel,
                        events=scans, at=AS_OF, claims=[claim])
    assert body == (f"Hello Nadia,\n\nWe already have a damage claim for {parcel.tracking_number}. "
        "We keep one damage claim for each shipment.\n\nYou do not need to send it again. "
        "Please quote the claim number from our earlier email if you write to us about it."
        "\n\nBayline Cargo Customer Service")


def test_claim_followup_numbers_refer_to_claims_opened_before_arrival(sample):
    import re

    labels = {label.message_id: label for label in sample.tables["message_labels"]}
    messages = {message.id: message for message in sample.tables["messages"]}
    claims = {claim.id: claim for claim in sample.tables["claims"]}
    for reply in sample.tables["replies"]:
        label = labels[reply.message_id]
        if label.primary_topic != "claim_followup" or not label.tracking_numbers:
            continue
        number = label.tracking_numbers[0]
        visible = [claim for claim in claims.values() if claim.tracking_number == number
                   and claim.opened_at <= reply.sent_at]
        references = re.findall(r"CLM-\d{5}", reply.body)
        if len(visible) == 1:
            assert references == [visible[0].id], reply.id
        else:
            assert not references, reply.id
        for reference in references:
            assert claims[reference].tracking_number == number, reply.id
            assert claims[reference].opened_at < messages[reply.message_id].received_at, reply.id
