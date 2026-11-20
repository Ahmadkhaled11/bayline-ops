"""Request a first extraction from the model."""

from bayline.llm import ChatMessage, ChatRequest

PROMPT = (
    'Return one JSON object only, with no code fences, with "primary_topic", "topics" '
    'and "tracking_numbers". '
    'Topics: status_question, delay, return, damage, address_change, claim_followup, '
    'billing, other. Return tracking numbers as a plain list of strings exactly as '
    'written in the message.'
)


def build_request(message) -> ChatRequest:
    """Build a request for one customer message."""
    return ChatRequest((ChatMessage("system", PROMPT), ChatMessage("user", message.body)))


def extract_raw(client, message) -> str:
    """Return the model's reply without interpreting it."""
    return client.complete(build_request(message)).text
