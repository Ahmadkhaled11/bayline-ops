"""Load a snapshot atomically and hash a canonical, portable dump."""

import hashlib
import json
from pathlib import Path

from ..db import connect, create_schema, insert_record, transaction
from ..models import TABLE_MODELS
from .generate import generate


def load(connection, data):
    create_schema(connection)
    with transaction(connection):
        for table, records in data.tables.items():
            for record in records:
                insert_record(connection, table, record)


def seed_database(path: Path, seed=20261101, force=False, authored_path=None):
    path = Path(path)
    if path.exists() and not force:
        raise FileExistsError("Database exists; use --force to replace it")
    data = generate(seed, authored_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".building")
    if staging.exists():
        raise FileExistsError("An unfinished database build exists")
    conn = connect(staging)
    try:
        load(conn, data)
        conn.close()
        staging.replace(path)
    except BaseException:
        conn.close()
        staging.unlink(missing_ok=True)
        raise
    return {table: len(records) for table, records in data.tables.items()}


def canonical_dump(connection):
    for table in sorted(TABLE_MODELS):
        keys = [r["name"] for r in connection.execute(f"PRAGMA table_info({table})") if r["pk"]]
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY {','.join(keys)}"):
            yield json.dumps({"table": table, "row": dict(row)}, sort_keys=True,
                             separators=(",", ":"), ensure_ascii=False) + "\n"


def checksum(connection):
    digest = hashlib.sha256()
    for line in canonical_dump(connection):
        digest.update(line.encode("utf-8"))
    return digest.hexdigest()
