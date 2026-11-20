"""SQLite connections and atomic writes."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from .models import TABLE_MODELS
from .timeutil import to_utc_text


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, factory=Connection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(files("bayline").joinpath("schema.sql").read_text(encoding="utf-8"))


def sql_value(value):
    if isinstance(value, datetime):
        return to_utc_text(value)
    if isinstance(value, (tuple, list)):
        return json.dumps(sorted(set(value)), separators=(",", ":"), ensure_ascii=False)
    if isinstance(value, bool):
        return int(value)
    return value


def insert_record(connection, table, record):
    if table not in TABLE_MODELS:
        raise ValueError("Unknown table")
    values = asdict(record)
    columns = ",".join(values)
    placeholders = ",".join("?" for _ in values)
    connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                       tuple(sql_value(v) for v in values.values()))


@contextmanager
def transaction(connection: sqlite3.Connection):
    if connection.in_transaction:
        raise ValueError("A transaction is already active")
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
