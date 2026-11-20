"""Saved requests remain readable, and transport errors do not expose credentials."""

import json
from dataclasses import dataclass, field, replace
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.request import HTTPHandler, build_opener
from urllib.response import addinfourl

import pytest

from bayline.llm import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    LiveClient,
    ModelHTTPError,
    ModelUnavailableError,
    RecordingClient,
    ReplayClient,
    live,
    request_key,
)
from bayline.llm.replay import request_data


@dataclass(frozen=True)
class ExtendedRequest(ChatRequest):
    response_format: str | None = None
    tools: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExtendedMessage(ChatMessage):
    name: str | None = None
    references: tuple[str, ...] = field(default_factory=tuple)


@pytest.mark.parametrize("message,key", [
    ("Hello.", "a21a178a76a941db"),
    ("A second message.", "049d3b01bc3d2457"),
])
def test_default_optional_fields_keep_saved_reply_keys(message, key):
    request = ExtendedRequest((ChatMessage("user", message),))
    assert request_key(request) == key
    fixtures = Path(__file__).with_name("fixtures") / "llm_replies"
    assert ReplayClient(fixtures).complete(request) == ReplayClient(fixtures).complete(
        ChatRequest(request.messages)
    )
    assert set(request_data(request)) == {"model", "messages", "temperature", "max_tokens"}


def test_nondefault_optional_fields_participate_in_saved_reply_key():
    request = ExtendedRequest((ChatMessage("user", "Hello."),))
    for changed in (replace(request, response_format="json"), replace(request, tools=("lookup",))):
        assert request_key(changed) != request_key(request)
    assert request_data(replace(request, response_format="json"))["response_format"] == "json"
    assert request_data(replace(request, tools=("lookup",)))["tools"] == ["lookup"]


@pytest.mark.parametrize("content,key", [
    ("Hello.", "a21a178a76a941db"),
    ("A second message.", "049d3b01bc3d2457"),
])
def test_message_optional_defaults_keep_saved_keys_and_nondefaults_change_them(content, key):
    message = ExtendedMessage("user", content)
    request = ChatRequest((message,))
    assert request_key(request) == key
    assert request_data(request)["messages"] == [{"role": "user", "content": content}]
    fixtures = Path(__file__).with_name("fixtures") / "llm_replies"
    assert ReplayClient(fixtures).complete(request) == ReplayClient(fixtures).complete(
        ChatRequest((ChatMessage("user", content),)))
    for changed in (replace(message, name="desk"), replace(message, references=("record",)),
                    replace(message, role="assistant"), replace(message, content=content + "!")):
        assert request_key(ChatRequest((changed,))) != key
    data = request_data(ChatRequest((replace(message, references=("record",)),)))
    assert data["messages"][0]["references"] == ["record"]


def test_message_optional_fields_roundtrip_through_recording(tmp_path):
    expected = ChatResponse("Saved text.", "test-model", "stop")

    class Inner:
        def complete(self, request):
            return expected

    request = ChatRequest((ExtendedMessage("user", "Hello.", name="desk"),))
    assert RecordingClient(Inner(), tmp_path).complete(request) == expected
    assert ReplayClient(tmp_path).complete(request) == expected


def test_optional_fields_roundtrip_through_recording_and_replay(tmp_path):
    expected = ChatResponse("Saved text.", "test-model", "stop")

    class Inner:
        def complete(self, request):
            return expected

    request = ExtendedRequest((ChatMessage("user", "Hello."),), tools=("lookup",))
    assert RecordingClient(Inner(), tmp_path).complete(request) == expected
    assert ReplayClient(tmp_path).complete(request) == expected


@pytest.mark.parametrize("status", [301, 302, 303])
def test_live_transport_refuses_redirect_without_contacting_other_host(monkeypatch, status):
    requests = []

    class FakeHTTP(HTTPHandler):
        def http_open(self, request):
            requests.append(request)
            headers = Message()
            headers["Location"] = "http://other.example/collect"
            response = addinfourl(BytesIO(b"Redirect: test-only-key"), headers,
                                  request.full_url, status)
            response.msg = "Redirect"
            return response

    monkeypatch.setattr(live, "build_opener", lambda *handlers: build_opener(FakeHTTP(), *handlers))
    client = LiveClient("http://provider.example/v1", "test-only-key", "model")
    with pytest.raises(ModelHTTPError) as error:
        client.complete(ChatRequest((ChatMessage("user", "Hello."),)))
    assert error.value.status_code == status
    assert "test-only-key" not in str(error.value)
    assert len(requests) == 1
    assert requests[0].full_url == "http://provider.example/v1/chat/completions"
    assert requests[0].get_header("Authorization") == "Bearer test-only-key"
    assert json.loads(requests[0].data)["model"] == "model"


@pytest.mark.parametrize("error_type", [TimeoutError, ConnectionError, OSError, RuntimeError])
def test_unavailable_error_names_cause_class_without_its_message(error_type):
    def transport(*args):
        raise error_type("test-only-key and private response details")

    client = LiveClient("https://provider.example/v1", "test-only-key", "model", transport=transport)
    with pytest.raises(ModelUnavailableError) as error:
        client.complete(ChatRequest((ChatMessage("user", "Hello."),)))
    assert error_type.__name__ in str(error.value)
    assert "test-only-key" not in str(error.value)
    assert "private response" not in str(error.value)
    assert error.value.__suppress_context__
