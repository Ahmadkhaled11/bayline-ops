"""Saved replies are indexed by the request, not by environment settings."""

import hashlib
import json
from dataclasses import MISSING, asdict, fields
from pathlib import Path

from .types import ChatResponse, ModelError, ReplayMissError


def _include_nondefault(record, data):
    values = asdict(record)
    for field in fields(record):
        if field.name in data:
            continue
        default = field.default
        if field.default_factory is not MISSING:
            default = field.default_factory()
        if default is MISSING or getattr(record, field.name) != default:
            # Keep the request comparable with its JSON form after recording.
            data[field.name] = json.loads(json.dumps(values[field.name], ensure_ascii=False))
    return data


def request_data(request):
    messages = [_include_nondefault(m, {"role": m.role, "content": m.content})
                for m in request.messages]
    return _include_nondefault(request, {
        "model": request.model or "", "messages": messages,
        "temperature": request.temperature, "max_tokens": request.max_tokens})


def request_key(request):
    value = json.dumps(request_data(request), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class ReplayClient:
    def __init__(self, replay_dir):
        self.replay_dir = Path(replay_dir)

    def complete(self, request):
        key = request_key(request)
        path = self.replay_dir / (key + ".json")
        if not path.is_file():
            raise ReplayMissError(key, path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["key"] != key or data["request"] != request_data(request):
                raise ValueError("Saved request does not match")
            return ChatResponse(**data["response"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ModelError(f"Invalid saved response: {path}") from exc
