import json

import pytest

from bayline.llm import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    LiveClient,
    ModelConfigError,
    ModelError,
    ModelHTTPError,
    ModelUnavailableError,
)

REQUEST = ChatRequest((ChatMessage("user", "Hello."),))


def test_exact_request_and_response():
    calls = []

    def transport(url, headers, body_bytes, timeout):
        calls.append(url)
        assert url == "https://provider.example/v1/chat/completions"
        assert headers == {"Authorization": "Bearer test-only-key", "Content-Type": "application/json"}
        assert json.loads(body_bytes) == {"model": "configured-model", "messages": [{"role": "user", "content": "Hello."}], "temperature": 0.0, "max_tokens": 512}
        assert timeout == 12
        return 200, json.dumps({"choices": [{"message": {"content": "Reply."}, "finish_reason": "stop"}],
            "model": "reported-model", "usage": {"prompt_tokens": 3, "completion_tokens": 2}}).encode()

    client = LiveClient("https://provider.example/v1/", "test-only-key", "configured-model", 12, transport)
    assert client.complete(REQUEST) == ChatResponse("Reply.", "reported-model", "stop", 3, 2)
    assert len(calls) == 1 and "test-only-key" not in repr(client)


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_errors_redact_and_truncate(status):
    calls = []

    def transport(*args):
        calls.append(1)
        return status, ("test-only-key " + "x" * 400).encode()

    client = LiveClient("https://provider.example/v1", "test-only-key", "model", 30, transport)
    with pytest.raises(ModelHTTPError) as error:
        client.complete(REQUEST)
    assert error.value.status_code == status
    assert "test-only-key" not in str(error.value)
    assert len(error.value.body) <= 300 and len(calls) == 1


@pytest.mark.parametrize("error_type", [TimeoutError, OSError, RuntimeError])
def test_network_error_never_leaks_key(error_type):
    def transport(*args):
        raise error_type("test-only-key")

    client = LiveClient("https://provider.example/v1", "test-only-key", "model", 30, transport)
    with pytest.raises(ModelUnavailableError) as error:
        client.complete(REQUEST)
    assert "test-only-key" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize("body", [b"{", b"{}", b'{"choices": []}', b'{"choices":[{"message":{"content":null},"finish_reason":"stop"}],"model":"x"}'])
def test_bad_response(body):
    with pytest.raises(ModelError, match="invalid response"):
        LiveClient("https://provider.example/v1", "test-only-key", "model", 30, lambda *a: (200, body)).complete(REQUEST)


def test_explicit_model_and_absent_usage():
    def transport(url, headers, body, timeout):
        assert json.loads(body)["model"] == "override"
        return 200, b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}],"model":"override"}'

    response = LiveClient("http://provider.example/v1", "test-only-key", "default", 30, transport).complete(
        ChatRequest(REQUEST.messages, model="override"))
    assert response.input_tokens is None and response.output_tokens is None


@pytest.mark.parametrize("url", ["", "file:///tmp/x", "https://user:password@provider.example/v1", "https://provider.example/v1?key=x"])
def test_invalid_base(url):
    with pytest.raises(ModelConfigError):
        LiveClient(url, "test-only-key", "model")
