"""One chat-completion request over the standard library HTTP client."""

import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .replay import request_data
from .types import ChatResponse, ModelConfigError, ModelError, ModelHTTPError, ModelUnavailableError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport(url, headers, body_bytes, timeout):
    request = Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as exc:
        with exc:
            return exc.code, exc.read()


class LiveClient:
    def __init__(self, base_url, api_key, model, timeout_seconds=30, transport=None):
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.netloc or parts.username or parts.query or parts.fragment:
            raise ModelConfigError("BAYLINE_LLM_BASE_URL must be an HTTP base address without credentials or query")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._transport = transport or _transport

    def __repr__(self):
        return "LiveClient(api_key=[redacted])"

    def complete(self, request):
        payload = request_data(request)
        payload["model"] = request.model or self.model
        headers = {"Authorization": "Bearer " + self._api_key, "Content-Type": "application/json"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            status, data = self._transport(self.base_url + "/chat/completions", headers, body, self.timeout_seconds)
        except Exception as exc:
            raise ModelUnavailableError(f"Model transport unavailable ({type(exc).__name__})") from None
        text = data.decode("utf-8", errors="replace")
        if not 200 <= status < 300:
            raise ModelHTTPError(status, text, self._api_key)
        try:
            result = json.loads(text)
            choice = result["choices"][0]
            usage = result.get("usage") or {}
            content, finish, model = choice["message"]["content"], choice["finish_reason"], result["model"]
            if not all(isinstance(value, str) for value in (content, finish, model)):
                raise ValueError("Invalid response fields")
            return ChatResponse(content, model, finish, usage.get("prompt_tokens"), usage.get("completion_tokens"))
        except (ValueError, KeyError, IndexError, TypeError):
            raise ModelError("Model returned an invalid response") from None
