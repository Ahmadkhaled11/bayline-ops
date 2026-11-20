# Message tags

Tag what the customer says. Do not put a rule decision in a label. Use the message's received time when checking the policy. Mira Saad owns the tag definitions and records `mira.saad` as the label author.

| Topic | Meaning |
| --- | --- |
| `status_question` | Asks where a parcel is or for its latest scan |
| `delay` | Asks about a missed or expected delivery date, or a parcel that never arrived |
| `return` | Wants to send goods back to the merchant |
| `damage` | Reports damage or asks about a damage claim |
| `address_change` | Wants a delivery address changed |
| `claim_followup` | Asks about an existing claim, its decision or its progress |
| `billing` | Asks about a charge or invoice |
| `other` | None of the above |

A parcel that never arrived has primary topic `delay`, including a new loss claim. A question about an existing claim has primary topic `claim_followup`, unless the main request disputes a delivery date or delay decision; then use `delay` as primary and include `claim_followup` in `topics`.

`primary_topic` is the main request. `topics` lists every topic and includes it. Keep lists sorted and do not repeat values. `tracking_numbers` contains valid, issued numbers mentioned in the body, upper-cased without spaces or hyphens. `invalid_tracking_mentions` preserves the written form of an invalid or unissued reference. A valid check digit alone does not mean the number was issued.

`missing` lists the information the desk must ask for: `tracking_number`, `new_address`, `photos`, `amount` or `description_of_problem`. Mark a tracking number missing only when no valid issued number is supplied. Set `contains_instructions` to 1 if the customer asks staff or a system to break policy; otherwise use 0.

Use `none`, `legal_threat`, `abusive` or `safety` for `escalation`. A legal threat or safety issue goes to Huda the same day. Abusive messages go to Reem. Answer requests to ignore policy with the policy itself.
