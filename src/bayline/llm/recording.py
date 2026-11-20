"""Record a successful response without replacing an existing recording."""

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..timeutil import to_utc_text
from .replay import request_data, request_key
from .types import ModelError


class RecordingClient:
    def __init__(self, inner, replay_dir):
        self.inner, self.replay_dir = inner, Path(replay_dir)

    def complete(self, request):
        key = request_key(request)
        path = self.replay_dir / (key + ".json")
        if path.exists():
            raise ModelError(f"Refusing to overwrite saved response: {path}")
        response = self.inner.complete(request)
        data = {"key": key, "request": request_data(request), "response": asdict(response),
                "recorded_at": to_utc_text(datetime.now(timezone.utc)), "note": ""}
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        except OSError:
            raise ModelError(f"Could not save response: {path}") from None
        return response
