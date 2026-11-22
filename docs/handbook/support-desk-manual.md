# Support desk manual

Owner: Huda Al-Mansoori. Day-to-day questions: ask Reem Adel, the shift lead on duty.

This is how the desk works on a normal day. The rules are in `docs/policies`. When this manual and a policy disagree, the policy wins, and someone should fix this file.

## Hours

The desk is staffed Sunday to Thursday, 08:00 to 20:00 Cairo time. Friday and Saturday are not business days, and neither are the public holidays in the service levels policy.

Messages arrive at any time, including at night and over the weekend. Sunday morning is always the heaviest: expect the whole weekend's inbox to be waiting.

## Message statuses

Every message has one of three statuses:

- `new`: nobody has replied yet. This is your queue.
- `answered`: we have sent at least one reply. The customer may still write back.
- `closed`: nothing more to do. Close a message when the question is settled, not just because you replied.

Recording a reply with the tool marks the message as answered for you.

## First reply

Every message gets a first reply within one business day. A message that arrives on Thursday evening must be answered by the end of Sunday. A message that arrives on Friday or Saturday also counts from Sunday.

The first reply does not have to solve everything. If you need a tracking number, photos or an amount from the customer, ask for it in the first reply instead of waiting.

## A normal shift

1. List the new messages and work through them oldest first.
2. Open one, read it to the end (the second problem is often in the last line), and look up the shipment.
3. Run the check that matches the request: return, claim or address change.
4. Reply in the house style (see `reply-style-guide.md`).
5. If the message needs a decision above you, follow `escalation-guide.md` instead.

## Using the tool

Everything below runs from the repository folder. The database is a snapshot, so every check uses the snapshot time unless you give `--at`.

List new messages:

```
python -m bayline messages --status new --limit 20
```

Read one message, with its replies:

```
python -m bayline message M-01001
```

Look up a shipment. This shows the status, the promised date, the delay class, the fee and every tracking event in order:

```
python -m bayline shipment BYL260442157
```

For that one you will see a promised date of Wednesday 7 October 2026 and `on_time`. The customer thought it was late because Tuesday 6 October was a holiday. That comes up a lot.

Look up a customer by id or by email. Customers often write from the email we have on file, even when they forget the tracking number:

```
python -m bayline customer tarek.sorour@example.com
```

### Checking a rule at the right time

Always check a request at the time the customer sent it, not the time you are reading it. Use the message's received time with `--at`.

A record cannot be dated before the shipment's latest scan or case. The check commands still answer for any time, so the decision you give the customer is always the one for the time they wrote.

If the tool refuses to record at that time, it names the time of the shipment's latest record. Record at that time or later. If the decision at the later time is different from the check at the customer's time, do not record it. Ask Reem Adel first.

Example: Tarek Sorour asked to return a jacket late on Saturday 24 October 2026, outside desk hours. Checked at the time he wrote:

```
python -m bayline return-check BYL260411871 --at 2026-10-24T19:40:00Z
```

The answer is `ALLOWED: day 30 of 30, last day Saturday 24 October 2026`. If you checked it at the time you read it, on Sunday morning (`--at 2026-10-25T06:00:00Z`), it would say the window had closed, and you would refuse a return that arrived in time.

Damage claim, with the amount the customer asked for in EGP:

```
python -m bayline claim-check BYL260455803 --kind damage --amount 8500 --at 2026-10-26T07:00:00Z
```

That gives `ELIGIBLE: payable 3,000 EGP`. The headphones were declared at 8,500 EGP but not insured, so the cap applies.

Address change:

```
python -m bayline address-check BYL260459136 --city Cairo --at 2026-11-02T06:45:00Z
```

That one says `TOO_LATE`: the parcel was already out for delivery.

### Recording what you did

When the check says yes and the customer has given everything we need, record it. These write to the database, so check the tracking number twice:

```
python -m bayline open-return BYL260411871 --reason not_wanted --by hany.nassar --at 2026-10-24T19:40:00Z
python -m bayline open-claim BYL260455803 --kind damage --amount 8500 --by dina.fawzy --at 2026-10-26T07:00:00Z
python -m bayline change-address BYL260462072 --city Cairo --line "Building 12, Street 9, Flat 4" --by omar.elbanna --at 2026-10-31T12:00:00Z
```

If the rule refuses, the tool still writes the case as refused and exits with code 1. That is on purpose: we keep a record of refusals too.

Then send the reply and record it:

```
python -m bayline reply M-01001 --by hany.nassar --body "..."
```

The policies themselves are in the tool as well, if you want to quote the exact wording:

```
python -m bayline policies
python -m bayline policy returns-policy
```

## Tracking numbers

A tracking number is `BYL` and 9 digits. The last digit is a check digit, so a single wrong digit is caught. If the tool says a number is invalid, it is almost always a typing mistake: ask the customer to copy it from the merchant's email. Customers also write numbers with spaces or dashes, or in lower case. The tool tidies those up, so `byl 2604-11871` finds `BYL260411871`.

If a number is valid but not found, do not guess which shipment they meant. Ask.

## Possibly lost shipments

A shipment with no tracking scan for 7 days is treated as possibly lost. The tool shows it as `lost_suspected`. Shipments held at customs are the exception; they can sit for a while without a scan.

When you see one, check the last event and where it was. Tell the customer what we know and that we are looking into it. The customer can make a loss claim; the claims policy has the conditions.

## Money

Agents never promise money before a claim decision. Not "you will get your money back", not "we will refund the fee". You can explain the policy and what the limits are. You can say a claim has been opened. The amount is confirmed only in the decision.

Refunds for goods after a return are handled case by case. Ask Reem before you say anything about them.

## Small things that save time

- Read the whole message before you look anything up. Many customers ask two things.
- Pasted threads: the newest text is usually at the top, but not always.
- When in doubt about a policy question, open the policy. Do not answer from memory.
