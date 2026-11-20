"""Messages start from known facts. Documents render stored values."""

from dataclasses import replace

from ..money import format_egp
from ..rules.claims import check_claim, liability_cap
from ..rules.delays import classify_delay
from ..status import current_status, events_at
from ..timeutil import format_day, local_date

TEMPLATES = {
    "status_question": ("Where is parcel {tn}?", "Please check the status of {tn}.", "Can you tell me where {tn} is now?", "I need the latest scan for {tn}."),
    "delay": ("Why is {tn} late?", "Please check the delivery date for {tn}.", "The expected date for {tn} has passed.", "When should I expect {tn}?"),
    "return": ("I want to return {tn}.", "Can I send {tn} back?", "Please check whether {tn} can be returned.", "I no longer need the items in {tn}. Can I return them?"),
    "damage": ("The goods in {tn} arrived damaged.", "Please check a damage claim for {tn}.", "The item inside {tn} was broken when it arrived.", "I need help with damage to {tn}."),
    "address_change": ("Can I change the delivery address for {tn}?", "Please update the address on {tn}.", "I need a different address for {tn} in the same city.", "Please check if the address on {tn} can still be changed."),
    "claim_followup": ("Please check my claim for {tn}.", "Is there an update on the claim for {tn}?", "I am following up on {tn} and its claim.", "Please tell me the progress of the claim for {tn}."),
    "other": ("What are your desk hours? I am writing about {tn}.", "How do I contact the desk? I am writing about {tn}.", "Please explain what a waybill means. I am writing about {tn}.", "I need help reading my parcel record. I am writing about {tn}."),
}


def render_message(topic, tn, variant):
    return TEMPLATES[topic][variant % 4].format(tn=tn)


RETURN_STEPS = {
    "ALLOWED": (
        "Please reply with your order reference and the address for collection, and we will open the return.",
        "To go ahead, reply to this email with your merchant's order reference.",
        "Please keep the original packaging and reply with your order reference so that we can open the return.",
        "If you would like to go ahead, reply with your order reference by {last_day}."),
    "WINDOW_CLOSED": (
        "Please contact the merchant, who may have their own arrangement.",
        "If the item is faulty or is not what you ordered, please contact the merchant."),
    "NOT_DELIVERED": (
        "Please write to us again once the parcel has arrived.",
        "Once it is delivered, reply to this email and we will check again."),
    "MERCHANT_NOT_ON_PLAN": (
        "Please contact the merchant about their own returns process.",
        "The merchant handles returns for this order, so please write to them with your order reference."),
    "CATEGORY_EXCLUDED": (
        "Please contact the merchant if there is a problem with the item.",
        "If the item arrived damaged, reply with photos and we will check a damage claim instead."),
    "ALREADY_OPEN": (
        "You do not need to do anything else. We will write to you about the collection.",
        "Please quote the return number from our earlier email if you write to us about it."),
}
DAMAGE_STEPS = {
    "ELIGIBLE": (
        "Please send photos of the item and its packaging. We will write to you with the decision on your claim.",
        "Please reply with photos of the damage and your order receipt. The claims team will then decide.",
        "Please keep the item and all the packaging, and send us photos. We will write to you with the decision.",
        "To finish the claim we need photos and proof of the item's value. The decision follows once we have them."),
    "WINDOW_CLOSED": (
        "Please contact the merchant, who may be able to help with the item.",
        "We are sorry that we cannot take this claim. The merchant may be able to help."),
    "ALREADY_EXISTS": (
        "You do not need to send it again. Please quote the claim number from our earlier email if you write to us about it.",),
    "NOT_DELIVERED": (
        "If the parcel arrives damaged, write to us within 14 days of delivery and include photos.",),
    "INVALID_AMOUNT": ("Please reply with the amount in EGP and your order receipt.",),
}
ADDRESS_STEPS = {
    "ALLOWED": (
        "Please reply with the full new address: street, building and flat number.",
        "Send us the new street address and flat number, and we will update the delivery.",
        "Please confirm the new address in {city}, with the building and flat number.",
        "Reply with the new address and a phone number for the driver."),
    "TOO_LATE": ("Please reply if there is anything else we can check for you.", ""),
    "CUSTOMS_HOLD": (
        "Please write to us again once tracking shows that the parcel has been released.",
        "We cannot say how long the customs check will take. Once the parcel is released, reply and we will check again."),
    "ALREADY_CHANGED": ("Please reply if there is anything else we can check for you.", ""),
    "DIFFERENT_CITY": ("If a different address in {city} would work, reply with it and we will check.",),
}
TRACKING_STEPS = {
    "delivered_on_time": (
        "If it has not reached you, reply and we will check with the delivery team.",
        "If anything about the delivery is wrong, reply and tell us what happened.", ""),
    "delivered_late": ("If it has not reached you, reply and we will check with the delivery team.", ""),
    "customs_hold": (
        "We will write to you when it is released.",
        "You do not need to do anything. Tracking will show when it is released."),
    "not_started": (
        "Please ask the merchant when they plan to hand it over.",
        "Tracking will show a promised date after the pick-up."),
    "returned": ("Please contact the merchant about a new delivery.",),
    "out_for_delivery": ("Please make sure that someone can receive it.",),
    "delivery_failed": ("Please reply and tell us when someone can receive it, or send us a corrected address in {city}. We will then agree the next attempt with you.",),
    "on_time": (
        "You do not need to do anything. Tracking will show when it is out for delivery.",
        "Please make sure that someone can receive it on the day."),
    "at_risk": ("Please check tracking again after {promised}, and reply if there is no new scan.",),
    "late": ("We are sorry for the delay. We have asked the delivery team to check it.",),
    "very_late": ("We are sorry for the delay. We have asked the delivery team to find it, and we will write to you with what they say.",),
    "lost_suspected": ("We have asked the delivery team to search for it. Please keep your order receipt in case a loss claim is needed.",),
}
OTHER_ANSWERS = (
    "Our desk is open Sunday to Thursday, 08:00 to 20:00 Cairo time. We are closed on Friday, Saturday and public holidays.",
    "You can reach the desk by replying to this email, or through the contact form. We answer Sunday to Thursday, 08:00 to 20:00 Cairo time.",
    "A waybill is the record that travels with a parcel. It shows the tracking number, the sender, the recipient and the delivery address.",
    "Each line in a parcel record is one scan: where the parcel was, and when. The newest line is its latest position. If one line is unclear, reply and tell us which one.",
)
TRACKING_REQUESTS = (
    "Please send us the tracking number for your parcel so that we can check it. It is BYL followed by 9 digits, and it is in the merchant's email.",
    "We need the tracking number to look up your parcel. It is BYL followed by 9 digits. Please reply with it.",
    "Please copy the tracking number from the merchant's email and reply with it. It is BYL followed by 9 digits.",
    "We can check this once we have the tracking number. It is BYL followed by 9 digits, and the merchant's email shows it.",
)


def _tracking_situation(decision, history):
    status = current_status(history)
    if status == "delivered":
        return "delivered_on_time" if not decision.late_business_days else "delivered_late"
    if status == "customs_hold":
        return "customs_hold"
    if decision.delay_class in ("returned", "lost_suspected"):
        return decision.delay_class
    if status in ("out_for_delivery", "delivery_failed"):
        return status
    return decision.delay_class


def reply_facts(topic, decision, shipment, events, at, variant=0):
    """Translate the check and its supporting dates into customer language."""
    tn = shipment.tracking_number
    today = local_date(at, shipment.destination_tz)
    date = format_day(today)
    history = events_at(events, at)
    delivered = [e for e in history if e.code == "DELIVERED"]
    delivery_day = format_day(local_date(delivered[-1].occurred_at, shipment.destination_tz)) if delivered else None
    if topic == "return":
        answer = {
            "ALLOWED": f"Your parcel {tn} can still be returned.",
            "WINDOW_CLOSED": f"We can no longer accept a return for {tn}.",
            "NOT_DELIVERED": f"We cannot open a return for {tn} yet, because it has not been delivered.",
            "MERCHANT_NOT_ON_PLAN": f"We cannot take {tn} back through Bayline Returns.",
            "CATEGORY_EXCLUDED": f"The goods in {tn} cannot be returned through Bayline Returns.",
            "ALREADY_OPEN": f"A return is already open for {tn}.",
        }[decision.reason]
        if decision.reason in ("ALLOWED", "WINDOW_CLOSED"):
            tense = "is" if decision.allowed else "was"
            reason = (f"It was delivered on {delivery_day}, and {date} is day {decision.day_number} of 30. "
                      f"The last day for a return {tense} {format_day(decision.last_day)}.")
            if decision.allowed and decision.day_number == 0:
                reason = (f"It was delivered on {delivery_day}, so the 30 days have only just started. "
                          f"The last day for a return is {format_day(decision.last_day)}.")
        else:
            reason = {
                "NOT_DELIVERED": f"Our records show no delivery scan as of {date}.",
                "MERCHANT_NOT_ON_PLAN": "The merchant who sent it is not on the Bayline Returns plan.",
                "CATEGORY_EXCLUDED": "Perishable goods, batteries and hazardous goods cannot be returned.",
                "ALREADY_OPEN": "A shipment can have only one open return at a time.",
            }[decision.reason]
    elif topic == "damage":
        answer = {
            "ELIGIBLE": f"Your damage claim for {tn} is within our time limit.",
            "WINDOW_CLOSED": f"We can no longer accept a damage claim for {tn}.",
            "ALREADY_EXISTS": f"We already have a damage claim for {tn}.",
            "NOT_DELIVERED": f"We cannot take a damage claim for {tn} yet, because it has not been delivered.",
            "INVALID_AMOUNT": f"We need the amount you are claiming for {tn}.",
        }[decision.reason]
        if decision.reason in ("ELIGIBLE", "WINDOW_CLOSED"):
            day = (today - local_date(delivered[-1].occurred_at, shipment.destination_tz)).days
            if decision.eligible:
                reason = (f"The parcel was delivered on {delivery_day}, and {date} is day {day} of the 14 days allowed. ")
                if day == 0:
                    reason = (f"The parcel was delivered on {delivery_day}, so the 14 days allowed have only just started. ")
                reason += (f"The shipment was insured, so the most we can pay is its declared value, {format_egp(liability_cap(shipment))}."
                           if shipment.insured else
                           f"The shipment was not insured. The most we can pay is its declared value, {format_egp(shipment.declared_value_piastres)}."
                           if shipment.declared_value_piastres < liability_cap(replace(shipment, declared_value_piastres=10**12)) else
                           f"The shipment was not insured, so the most we can pay is {format_egp(liability_cap(shipment))}.")
            else:
                reason = (f"The parcel was delivered on {delivery_day}, and {date} is day {day} after delivery. "
                          "Damage claims must be made within 14 calendar days.")
        else:
            reason = {
                "ALREADY_EXISTS": "We keep one damage claim for each shipment.",
                "NOT_DELIVERED": f"Our records show no delivery scan as of {date}.",
                "INVALID_AMOUNT": "A claim must state the value of the damage.",
            }[decision.reason]
    elif topic == "address_change":
        answer = {
            "ALLOWED": f"The delivery address for {tn} can still be changed, within {shipment.destination_city}.",
            "TOO_LATE": f"We cannot change the address for {tn} any more.",
            "CUSTOMS_HOLD": f"We cannot change the address for {tn} while it is held at customs.",
            "ALREADY_CHANGED": f"The address for {tn} has already been changed once, so we cannot change it again.",
            "DIFFERENT_CITY": f"We cannot move the delivery for {tn} to another city.",
        }[decision.reason]
        reason = {
            "ALLOWED": "The parcel has not gone out for delivery, and its address has not been changed before.",
            "TOO_LATE": "An address can be changed only before the shipment is out for delivery, and this one has passed that point.",
            "CUSTOMS_HOLD": "Address changes are not possible while a shipment is held at customs.",
            "ALREADY_CHANGED": "An address can be changed once per shipment.",
            "DIFFERENT_CITY": f"An address can be changed only within the same city, and this parcel is going to {shipment.destination_city}.",
        }[decision.reason]
    elif topic in ("delay", "status_question"):
        situation = _tracking_situation(decision, history)
        promised = format_day(decision.promised) if decision.promised else None
        tense = "is" if decision.promised and decision.promised >= today else "was"
        scans = [e for e in history if e.code != "ADDRESS_CHANGED"]
        latest = scans[-1] if scans else None
        scan_day = format_day(local_date(latest.occurred_at, shipment.destination_tz)) if latest else None
        scan = f"The last scan was at {latest.location} on {scan_day}." if latest else ""
        days = f"{decision.late_business_days} business day" + ("" if decision.late_business_days == 1 else "s")
        if situation.startswith("delivered_"):
            answer = f"Your parcel {tn} was delivered in {shipment.destination_city} on {delivery_day}."
            reason = (f"Its promised date was {promised}, so it arrived on time." if situation == "delivered_on_time"
                      else f"Its promised date was {promised}, so it arrived {days} late. We are sorry for the delay.")
        elif situation == "customs_hold":
            hold = [e for e in history if e.code == "CUSTOMS_HOLD"][-1]
            answer = f"Your parcel {tn} is held at customs in {shipment.destination_city}."
            reason = (f"It has been there since {format_day(local_date(hold.occurred_at, shipment.destination_tz))}. "
                      f"Its promised date {tense} {promised}. Customs checks are outside our control, so we cannot give you a new date.")
        elif situation == "not_started":
            answer = f"Your parcel {tn} has not been picked up from the merchant yet."
            reason = f"There is no pick-up scan as of {date}, so we cannot give a delivery date yet."
        elif situation == "returned":
            answer = f"Your parcel {tn} is on its way back to the sender, or has already reached them."
            reason = scan
        elif situation == "out_for_delivery":
            answer = f"Your parcel {tn} went out for delivery in {shipment.destination_city} on {scan_day}."
            reason = (f"Its promised date was {promised}, so it is {days} late. We are sorry for the delay."
                      if decision.late_business_days else f"Its promised date {tense} {promised}.")
        elif situation == "delivery_failed":
            answer = (f"We tried to deliver your parcel {tn} in {shipment.destination_city} on {scan_day}, "
                      "and the delivery did not succeed.")
            reason = f"Its promised date {tense} {promised}."
        elif situation == "on_time":
            answer = f"Your parcel {tn} is on schedule."
            reason = f"Its promised date {tense} {promised}. {scan}"
        elif situation == "at_risk":
            answer = f"Your parcel {tn} may arrive after its promised date, {promised}."
            reason = scan
        elif situation == "late":
            answer = f"Your parcel {tn} is late."
            reason = f"Its promised date was {promised}, and as of {date} it is {days} late. {scan}"
        elif situation == "very_late":
            answer = f"Your parcel {tn} is {days} late."
            reason = f"Its promised date was {promised}. {scan}"
        else:
            answer = f"Your parcel {tn} may be lost."
            reason = (f"It has had no tracking scan since {scan_day}, at {latest.location}. "
                      "A shipment with no tracking scan for 7 days is treated as possibly lost.")
    else:
        answer, reason = OTHER_ANSWERS[variant % 4], ""
    return answer, reason


def _existing_return(shipment, returns, at):
    case = next(r for r in returns if r.tracking_number == shipment.tracking_number
                and r.opened_at <= at and r.status in ("open", "approved", "received"))
    status = "open" if case.decided_at is None or case.decided_at > at else case.status
    fields = {"number": case.id, "tn": shipment.tracking_number,
              "opened": format_day(local_date(case.opened_at, shipment.destination_tz))}
    answer, next_step = {
        "open": ("Return {number} is already open for {tn}. It was opened on {opened}. A shipment can have only one open return at a time.",
                 "You do not need to do anything else. We will write to you about the collection."),
        "approved": ("Return {number} for {tn} was opened on {opened} and has been approved. We keep one return for each shipment.",
                     "Please quote the return number if you write to us about it."),
        "received": ("Return {number} for {tn} was opened on {opened}. Our records show that the parcel has come back to us. We keep one return for each shipment.",
                     "If you have a question about it, reply and quote the return number."),
    }[status]
    return answer.format(**fields), next_step


def _refused_claim_reason(claim, shipment, events):
    reason = claim.decision_code
    if reason == "ALREADY_EXISTS":
        return "It was refused because the shipment already had a claim of the same kind."
    if reason == "INVALID_AMOUNT" and claim.kind in ("damage", "loss"):
        return "It was refused because it did not state an amount above 0 EGP."
    if reason == "WINDOW_CLOSED" and claim.kind in ("delay", "damage"):
        return "It was refused because it was made more than 14 days after delivery."
    if reason == "NOT_DELIVERED" and claim.kind in ("delay", "damage"):
        return "It was refused because the parcel had not been delivered when the claim was made."
    if claim.kind == "loss":
        return {
            "DELIVERED": "It was refused because our records show the parcel as delivered.",
            "NOT_LATE_ENOUGH": "It was refused because the parcel was not yet late enough for a loss claim. A loss claim can be made 10 business days after the promised date.",
        }[reason]
    if claim.kind == "delay" and reason == "SERVICE_NOT_COVERED":
        return ("It was refused because delay claims cover Express shipments only, "
                f"and this shipment was sent by {shipment.service.title()}.")
    if claim.kind == "delay" and reason == "NOT_LATE_ENOUGH":
        delivered = next(e for e in events_at(events, claim.opened_at) if e.code == "DELIVERED")
        day = format_day(local_date(delivered.occurred_at, shipment.destination_tz))
        promised = format_day(classify_delay(shipment, events, claim.opened_at).promised)
        return (f"It was refused because the parcel was not late. It was delivered on {day}, "
                f"and the promised date was {promised}.")
    raise ValueError("No wording for this claim decision")


def _claim_followup(shipment, claims, at, events):
    tn = shipment.tracking_number
    visible = [c for c in claims if c.tracking_number == tn and c.opened_at <= at]
    if not visible:
        return (f"We have no claim on record for {tn}.",
                "If you sent one, please reply with the date you sent it. To open a claim now, reply and tell us what happened to the parcel.")
    if len(visible) > 1:
        return (f"We need your claim number to check the claim for {tn}. This shipment has more than one claim, so the tracking number alone is not enough.",
                "Please reply with the claim number from our earlier email. It starts with CLM.")
    claim = visible[0]
    status = "open" if claim.decided_at is None or claim.decided_at > at else claim.status
    answer = (f"Your claim {claim.id} for {tn} was opened on "
              f"{format_day(local_date(claim.opened_at, shipment.destination_tz))}. ")
    detail, next_step = {
        "open": ("It is still with the claims team.", "You do not need to do anything. The claims team will write to you with the decision."),
        "approved": ("Our records show it as approved.", "The claims team will write to you about the next step."),
        "paid": ("Our records show it as paid.", "If anything about it is unclear, reply and we will check."),
        "refused": ("It was refused.", "If you think the decision is wrong, reply and tell us why, and we will pass it to the claims team."),
    }[status]
    if status == "refused":
        detail = _refused_claim_reason(claim, shipment, events)
    return answer + detail, next_step


def _reply_parts(topic, decision, shipment, events, at, variant, claims, returns):
    if topic == "claim_followup":
        return _claim_followup(shipment, claims, at, events)
    if topic == "return" and decision.reason == "ALREADY_OPEN":
        return _existing_return(shipment, returns, at)
    answer, reason = reply_facts(topic, decision, shipment, events, at, variant)
    text = " ".join(part for part in (answer, reason) if part)
    fields = {"city": shipment.destination_city}
    if topic == "return":
        choices = RETURN_STEPS[decision.reason]
        fields["last_day"] = format_day(decision.last_day) if decision.last_day else ""
    elif topic == "damage":
        choices = DAMAGE_STEPS[decision.reason]
    elif topic == "address_change":
        choices = ADDRESS_STEPS[decision.reason]
    elif topic in ("delay", "status_question"):
        choices = TRACKING_STEPS[_tracking_situation(decision, events_at(events, at))]
        fields["promised"] = format_day(decision.promised) if decision.promised else ""
    else:
        choices = ("",)
    return text, choices[variant % len(choices)].format(**fields)


def render_reply(topic, decision, *, customer_name, shipment, events, at, variant=0,
                 has_number=True, secondary=(), invalid_number=None, claims=(), returns=()):
    greeting = f"Hello {customer_name.split()[0]},\n\n"
    questions = [(topic, decision), *secondary]
    closed_damage = any(t == "damage" and d is not None and d.reason == "WINDOW_CLOSED"
                        for t, d in questions)
    if any(t == "return" and d is not None and d.reason == "CATEGORY_EXCLUDED"
           for t, d in questions):
        damage_window = check_claim(shipment, events, "damage",
                                    max(100, shipment.declared_value_piastres), [], at)
        closed_damage = closed_damage or damage_window.reason == "WINDOW_CLOSED"
    paragraphs = []
    answered = set()
    for n, (reply_topic, reply_decision) in enumerate(questions):
        group = "tracking" if reply_topic in ("delay", "status_question") else reply_topic
        if not has_number and reply_topic != "other":
            if "number" not in answered:
                request = (f"The number you sent, {invalid_number}, is not a valid Bayline tracking number. "
                           "One of the digits may be wrong. Please copy the number again from the merchant's email and reply with it."
                           if invalid_number else TRACKING_REQUESTS[variant % 4])
                paragraphs.append(request)
                answered.add("number")
            continue
        if group in answered:
            continue
        answered.add(group)
        reply_variant = (variant + n) % 4
        if (reply_topic in ("delay", "status_question")
                and _tracking_situation(reply_decision, events_at(events, at)) == "on_time"
                and any(t in ("return", "damage", "address_change") for t, _ in questions)):
            reply_variant = 1
        if closed_damage and reply_topic == "return" and reply_decision.reason == "CATEGORY_EXCLUDED":
            reply_variant = 0
        answer, next_step = _reply_parts(reply_topic, reply_decision, shipment, events, at, reply_variant, claims, returns)
        if (reply_topic in ("delay", "status_question")
                and any(t in ("return", "damage") for t, _ in questions)
                and _tracking_situation(reply_decision, events_at(events, at)).startswith("delivered_")):
            next_step = ""
        separator = " " if len(questions) > 1 else "\n\n"
        paragraphs.append(separator.join(part for part in (answer, next_step) if part))
    return greeting + "\n\n".join(paragraphs) + "\n\nBayline Cargo Customer Service"


def render_document(shipment, kind, layout, merchant, recipient):
    fields = [
        ("Tracking number", shipment.tracking_number), ("Merchant", merchant.name),
        ("Recipient", recipient.name), ("From", shipment.origin_city),
        ("To", shipment.destination_city), ("Address", shipment.address_line),
        ("Service", shipment.service), ("Pieces", str(shipment.pieces)),
        ("Weight kg", str(shipment.weight_kg)), ("Goods", shipment.goods_description),
        ("Declared value", format_egp(shipment.declared_value_piastres)),
        ("Shipping fee", format_egp(shipment.shipping_fee_piastres)),
    ]
    if layout == "b":
        fields = fields[5:] + fields[:5]
    elif layout == "c":
        fields = list(reversed(fields))
    separator = " | " if layout == "b" else ": "
    body = kind.replace("_", " ").title() + "\n" + "\n".join(k + separator + str(v) for k, v in fields)
    if kind == "commercial_invoice":
        first = shipment.declared_value_piastres // 2
        second = shipment.declared_value_piastres - first
        body += f"\nItem 1: {format_egp(first)}\nItem 2: {format_egp(second)}\nTotal: {format_egp(first+second)}"
    return body + "\n"
