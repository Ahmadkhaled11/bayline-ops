"""Paths are resolved here. No configuration file is loaded."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def database_path() -> Path:
    return Path(os.environ.get("BAYLINE_DB") or "var/bayline.db")


def docs_path() -> Path:
    return Path(os.environ.get("BAYLINE_DOCS_DIR") or ROOT / "docs")
