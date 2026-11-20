"""The client contract is independent of any provider."""

from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class ChatRequest:
    messages: tuple[ChatMessage, ...]
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int = 512


@dataclass(frozen=True)
class ChatResponse:
    text: str
    model: str
    finish_reason: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LanguageModelClient(Protocol):
    def complete(self, request: ChatRequest) -> ChatResponse: ...


class ModelError(Exception):
    """A client could not return a usable response."""


class ModelConfigError(ModelError):
    pass


class ReplayMissError(ModelError):
    def __init__(self, key, path):
        self.key, self.path = key, path
        super().__init__(f"No saved response for {key}: expected {path}")


class ModelHTTPError(ModelError):
    def __init__(self, status_code, body, api_key=""):
        safe = body.replace(api_key, "[redacted]") if api_key else body
        self.status_code, self.body = status_code, safe[:300]
        super().__init__(f"Model HTTP {status_code}: {self.body}")


class ModelUnavailableError(ModelError):
    pass
