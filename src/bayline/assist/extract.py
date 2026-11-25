"""Request a first extraction from the model."""

import json
from dataclasses import dataclass

from bayline.llm import ChatMessage, ChatRequest
from bayline.models import Topic
from bayline.tracking_numbers import is_valid, normalise

PROMPT = (
    'Return one JSON object only, with no code fences, with "primary_topic", "topics" '
    'and "tracking_numbers". '
    'Topics: status_question, delay, return, damage, address_change, claim_followup, '
    'billing, other. Return tracking numbers as a plain list of strings exactly as '
    'written in the message.'
)

TOPICS = {topic.value for topic in Topic}


class ParseError(ValueError):
    """The model's reply could not be read."""


@dataclass(frozen=True)
class Extraction:
    primary_topic: str
    topics: list[str]
    tracking_numbers: list[str]
    invalid_tracking_mentions: list[str]


def build_request(message) -> ChatRequest:
    """Build a request for one customer message."""
    return ChatRequest((ChatMessage("system", PROMPT), ChatMessage("user", message.body)))


def extract_raw(client, message) -> str:
    """Return the model's reply without interpreting it."""
    return client.complete(build_request(message)).text


def _json_object(raw: str) -> dict:
    if not raw or not raw.strip():
        raise ParseError("The reply is empty.")
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end < start:
        raise ParseError("The reply has no complete JSON object (it may be cut short).")
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as error:
        raise ParseError(f"The JSON could not be read: {error.msg}.") from error
    if not isinstance(data, dict):
        raise ParseError("The reply is not a JSON object.")
    return data


def parse_extraction(raw: str) -> Extraction:
    """Read the model's reply into checked fields. Every tracking number is checked here, not by the model."""
    data = _json_object(raw)
    primary = data.get("primary_topic")
    topics = data.get("topics", [])
    numbers = data.get("tracking_numbers", [])
    if not isinstance(topics, list) or not isinstance(numbers, list):
        raise ParseError('"topics" and "tracking_numbers" must be lists.')
    for topic in [primary, *topics]:
        if topic not in TOPICS:
            raise ParseError(f"Unknown topic: {topic!r}.")
    valid, invalid = set(), set()
    for mention in numbers:
        if not isinstance(mention, str):
            raise ParseError(f"A tracking number is not text: {mention!r}.")
        if is_valid(normalise(mention)):
            valid.add(normalise(mention))
        else:
            invalid.add(mention)
    return Extraction(primary, sorted(set(topics) | {primary}), sorted(valid), sorted(invalid))


def extract(client, message) -> Extraction:
    """Ask the model about one message and return the checked fields."""
    return parse_extraction(extract_raw(client, message))
