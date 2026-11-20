"""Validate externally maintained messages before changing the database."""

import json
from pathlib import Path

from ..models import Channel, Escalation, Missing, Topic
from ..timeutil import parse_utc
from ..tracking_numbers import is_valid, normalise
from .anchors import ANCHOR_NUMBERS

LABEL_FIELDS = {"primary_topic", "topics", "tracking_numbers", "invalid_tracking_mentions",
                "missing", "contains_instructions", "escalation", "labelled_by"}
MESSAGE_FIELDS = {"id", "received_at", "channel", "from_name", "from_email", "subject", "body", "status", "labels"}


def validate_labels(labels, body, known_numbers):
    if set(labels) != LABEL_FIELDS:
        raise ValueError("Unexpected or missing label field")
    for key in ("topics", "tracking_numbers", "invalid_tracking_mentions", "missing"):
        values = labels[key]
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError(f"{key} must be a list of strings")
        if values != sorted(set(values)):
            raise ValueError(f"{key} must be sorted without duplicates")
    Topic(labels["primary_topic"])
    if labels["primary_topic"] not in labels["topics"]:
        raise ValueError("Primary topic must appear in topics")
    for topic in labels["topics"]:
        Topic(topic)
    for missing in labels["missing"]:
        Missing(missing)
    Escalation(labels["escalation"])
    if labels["contains_instructions"] not in (0, 1) or labels["labelled_by"] != "mira.saad":
        raise ValueError("Invalid instruction flag or label author")
    for tn in labels["tracking_numbers"]:
        if not is_valid(tn) or tn not in known_numbers or tn not in normalise(body):
            raise ValueError("Tracking label must be valid, issued and present in the body")
    for mention in labels["invalid_tracking_mentions"]:
        if mention not in body or (is_valid(normalise(mention)) and normalise(mention) in known_numbers):
            raise ValueError("Invalid tracking mention must be present and invalid or unissued")
    if "tracking_number" in labels["missing"] and labels["tracking_numbers"]:
        raise ValueError("A missing tracking number cannot also be supplied")


def load_authored(path: Path, shipments, events, customers, as_of):
    rows = []
    known = {s.tracking_number: s for s in shipments}
    anchor_emails = {c.email for c in customers if c.id in {f"CUS-{i:05}" for i in range(101, 116)}}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ValueError(f"Authored messages: line 1: cannot read {path.name}") from exc
    for line_no, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
            if set(row) != MESSAGE_FIELDS or row["id"] != f"M-{1000+line_no:05}":
                raise ValueError("Unexpected fields or message id")
            for key in ("from_name", "from_email", "subject", "body"):
                if not isinstance(row[key], str):
                    raise ValueError(f"{key} must be text")
            if not 20 <= len(row["body"].split()) <= 250:
                raise ValueError("Body must contain 20 to 250 words")
            Channel(row["channel"])
            if row["status"] != "new":
                raise ValueError("Authored messages must be new")
            email = row["from_email"].lower()
            if email not in anchor_emails and email.rsplit("@", 1)[-1] not in ("example.com", "example.net", "example.org", "bayline.example"):
                raise ValueError("Sender must use a reserved email domain")
            at = parse_utc(row["received_at"])
            if not parse_utc("2026-09-01T00:00:00Z") <= at <= as_of:
                raise ValueError("Message time is outside the snapshot")
            validate_labels(row["labels"], row["body"], known)
            for tn in row["labels"]["tracking_numbers"]:
                if tn not in ANCHOR_NUMBERS or at < known[tn].created_at:
                    raise ValueError("Only existing fixed shipments may be referenced")
                if set(row["labels"]["topics"]) & {"return", "damage"}:
                    if not any(e.tracking_number == tn and e.code == "DELIVERED" and e.occurred_at <= at for e in events):
                        raise ValueError("Return and damage messages must follow delivery")
            if any(m not in ("BYL260411872", "BYL260480009") for m in row["labels"]["invalid_tracking_mentions"]):
                raise ValueError("Unexpected invalid tracking mention")
            rows.append(row)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"Authored messages: line {line_no}: {exc}") from exc
    if len(rows) != 40:
        raise ValueError(f"Authored messages: line {len(lines)+1}: expected 40 rows")
    mentioned = {tn for r in rows for tn in r["labels"]["tracking_numbers"]}
    if not set(ANCHOR_NUMBERS) <= mentioned:
        raise ValueError(f"Authored messages: line {len(lines)}: every fixed shipment must appear")
    return rows


def load_messages(path=None):
    """Read authored messages without their labels."""
    from ..config import ROOT
    from ..models import Message

    path = Path(path) if path is not None else ROOT / "data/authored/messages.jsonl"
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines())
    return [Message(row["id"], parse_utc(row["received_at"]), row["channel"],
        row["from_name"], row["from_email"], None, row["subject"], row["body"],
        row["status"], None, "authored") for row in rows]
