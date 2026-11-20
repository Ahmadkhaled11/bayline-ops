"""Only named environment settings configure model clients."""

import math
import os
from pathlib import Path

from ..config import ROOT
from .live import LiveClient
from .recording import RecordingClient
from .replay import ReplayClient
from .types import ModelConfigError


def client_from_env(env=os.environ):
    mode = env.get("BAYLINE_LLM_MODE") or "replay"
    replay_dir = Path(env.get("BAYLINE_LLM_REPLAY_DIR") or ROOT / "data/llm_replies")
    if mode == "replay":
        return ReplayClient(replay_dir)
    if mode not in ("live", "record"):
        raise ModelConfigError("BAYLINE_LLM_MODE must be replay, live or record")
    values = []
    for name in ("BAYLINE_LLM_BASE_URL", "BAYLINE_LLM_API_KEY", "BAYLINE_LLM_MODEL"):
        if not env.get(name):
            raise ModelConfigError(f"Missing {name}")
        values.append(env[name])
    try:
        timeout = float(env.get("BAYLINE_LLM_TIMEOUT_SECONDS") or "30")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Invalid timeout")
    except ValueError:
        raise ModelConfigError("BAYLINE_LLM_TIMEOUT_SECONDS must be a positive finite number") from None
    live = LiveClient(*values, timeout)
    return RecordingClient(live, replay_dir) if mode == "record" else live
