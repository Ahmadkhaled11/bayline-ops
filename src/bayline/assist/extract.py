"""Request a first extraction from the model, and read its reply into checked fields."""

import json
import re
from dataclasses import dataclass

from bayline import tracking_numbers
from bayline.llm import ChatMessage, ChatRequest
from bayline.models import Topic

PROMPT = (
    'Return one JSON object only, with no code fences, with "primary_topic", "topics" '
    'and "tracking_numbers". '
    'Topics: status_question, delay, return, damage, address_change, claim_followup, '
    'billing, other. Return tracking numbers as a plain list of strings exactly as '
    'written in the message.'
)

TOPICS = {topic.value for topic in Topic}


class ParseError(ValueError):
    """The model's reply could not be read into an extraction."""


@dataclass(frozen=True)
class Extraction:
    primary_topic: str
    topics: tuple[str, ...]
    tracking_numbers: tuple[str, ...]
    invalid_tracking_mentions: tuple[str, ...]


def build_request(message) -> ChatRequest:
    """Build a request for one customer message."""
    return ChatRequest((ChatMessage("system", PROMPT), ChatMessage("user", message.body)))


def extract_raw(client, message) -> str:
    """Return the model's reply without interpreting it."""
    return client.complete(build_request(message)).text


def _json_text(raw: str) -> str:
    """Take the JSON object out of code fences and any text around it."""
    if not raw or not raw.strip():
        raise ParseError("The reply is empty")
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    text = fenced.group(1) if fenced else raw
    start, end = text.find("{"), text.rfind("}")
    if start == -1:
        raise ParseError("The reply has no JSON object")
    if end < start:
        raise ParseError("The reply stops before the JSON object ends")
    return text[start:end + 1]


def _topic(value) -> str:
    if not isinstance(value, str) or value not in TOPICS:
        raise ParseError(f"Unknown topic: {value!r}")
    return value


def parse_extraction(raw: str) -> Extraction:
    """Read the model's reply. Every tracking number is checked here, never trusted from the model."""
    try:
        data = json.loads(_json_text(raw))
    except json.JSONDecodeError as error:
        raise ParseError(f"The reply is not valid JSON: {error.msg}") from error
    if not isinstance(data, dict):
        raise ParseError("The reply is not a JSON object")
    primary = _topic(data.get("primary_topic"))
    topics = data.get("topics", [])
    if not isinstance(topics, list):
        raise ParseError("topics is not a list")
    all_topics = {_topic(topic) for topic in topics} | {primary}
    mentions = data.get("tracking_numbers", [])
    if not isinstance(mentions, list) or not all(isinstance(m, str) for m in mentions):
        raise ParseError("tracking_numbers is not a list of strings")
    valid, invalid = set(), set()
    for mention in mentions:
        number = tracking_numbers.normalise(mention)
        if tracking_numbers.is_valid(number):
            valid.add(number)
        else:
            invalid.add(mention)
    return Extraction(primary, tuple(sorted(all_topics)), tuple(sorted(valid)), tuple(sorted(invalid)))


def extract(client, message) -> Extraction:
    """Ask the model about one message and return the checked fields."""
    return parse_extraction(extract_raw(client, message))
