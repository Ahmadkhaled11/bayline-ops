import json
from pathlib import Path

import pytest

from bayline.llm import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ModelError,
    RecordingClient,
    ReplayClient,
    ReplayMissError,
    request_key,
)

FIXTURES = Path(__file__).with_name("fixtures") / "llm_replies"


@pytest.mark.parametrize("message,key,text,finish,input_tokens,output_tokens", [
    ("Hello.", "a21a178a76a941db", "Hello from the saved response.", "stop", 12, 5),
    ("A second message.", "049d3b01bc3d2457", "The second saved response.", "length", 15, 6),
])
def test_fixtures(message, key, text, finish, input_tokens, output_tokens):
    request = ChatRequest((ChatMessage("user", message),))
    assert request_key(request) == key
    assert ReplayClient(FIXTURES).complete(request) == ChatResponse(text, "recorded-model-name", finish, input_tokens, output_tokens)


def test_miss_and_malformed_file(tmp_path):
    request = ChatRequest((ChatMessage("user", "Changed message."),))
    with pytest.raises(ReplayMissError) as error:
        ReplayClient(tmp_path).complete(request)
    assert request_key(request) in str(error.value)
    assert str(tmp_path / (request_key(request) + ".json")) in str(error.value)
    path = tmp_path / (request_key(request) + ".json")
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ModelError, match="Invalid saved response"):
        ReplayClient(tmp_path).complete(request)


def test_recording_roundtrip_and_no_overwrite(tmp_path):
    calls = []
    expected = ChatResponse("Saved text.", "test-model", "stop")

    class Inner:
        def complete(self, request):
            calls.append(request)
            return expected

    request = ChatRequest((ChatMessage("user", "Record this."),))
    client = RecordingClient(Inner(), tmp_path)
    assert client.complete(request) == ReplayClient(tmp_path).complete(request) == expected
    path = tmp_path / (request_key(request) + ".json")
    before = path.read_bytes()
    with pytest.raises(ModelError, match="overwrite"):
        client.complete(request)
    assert len(calls) == 1 and path.read_bytes() == before
    assert json.loads(before)["request"]["model"] == ""


def test_recording_failure_leaves_no_file(tmp_path):
    class Inner:
        def complete(self, request):
            raise ModelError("Failed")

    request = ChatRequest((ChatMessage("user", "Hello."),))
    with pytest.raises(ModelError):
        RecordingClient(Inner(), tmp_path).complete(request)
    assert list(tmp_path.iterdir()) == []


def test_key_includes_each_request_field():
    from dataclasses import replace

    request = ChatRequest((ChatMessage("user", "Hello."),))
    for changed in (replace(request, model="explicit"), replace(request, temperature=0.5),
        replace(request, max_tokens=8), replace(request, messages=(ChatMessage("system", "Hello."),))):
        assert request_key(changed) != request_key(request)
