"""Read-only JSON over WSGI. No network is needed to test a route."""

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from urllib.parse import parse_qs, unquote

from . import policies, services
from . import repository as repo
from .db import connect
from .money import egp_to_piastres
from .timeutil import parse_utc, to_utc_text


def _route(connection, path, query, docs_dir):
    parts = [unquote(p) for p in path.strip("/").split("/")]
    at = parse_utc(query["at"]) if "at" in query else repo.snapshot_time(connection)
    if parts == ["health"]:
        return {"status": "ok", "as_of": to_utc_text(repo.snapshot_time(connection))}
    if parts[0] == "shipments" and len(parts) >= 2:
        s = repo.get_shipment(connection, parts[1])
        events = repo.get_events(connection, s.tracking_number, at)
        if len(parts) == 2:
            return repo.shipment_summary(connection, s.tracking_number, at)
        if parts[2:] == ["events"]:
            return {"events": events}
        if parts[2:] == ["checks", "return"]:
            return services.check_return(connection, s.tracking_number, at)
        if parts[2:] == ["checks", "claim"]:
            return services.check_claim(connection, s.tracking_number, query["kind"], egp_to_piastres(query["amount"]), at)
        if parts[2:] == ["checks", "address"]:
            return services.check_address_change(connection, s.tracking_number, query["city"], at)
    if parts[0] == "customers" and len(parts) == 2:
        c = repo.get_customer(connection, parts[1])
        return {**asdict(c), "shipments": [s.tracking_number for s in repo.customer_shipments(connection, c.id)]}
    if parts == ["messages"]:
        return {"messages": repo.list_messages(connection, query.get("status"), int(query.get("limit", "20")))}
    if parts[0] == "messages" and len(parts) == 2:
        m = repo.get_message(connection, parts[1])
        return {**asdict(m), "replies": repo.get_replies(connection, m.id)}
    if parts == ["policies"]:
        return {"documents": policies.list_documents(docs_dir)}
    if parts[0] == "policies" and len(parts) == 2:
        return {"slug": parts[1], "markdown": policies.get_document(parts[1], docs_dir)}
    raise repo.NotFoundError("Route not found")


def create_app(db_path, docs_dir=None):
    db_path = Path(db_path)

    def app(environ, start_response):
        code, status = 200, "OK"
        try:
            if environ.get("REQUEST_METHOD") != "GET":
                code, status = 405, "Method Not Allowed"
                result = {"error": "method_not_allowed", "detail": "Only GET is supported"}
            else:
                if not db_path.is_file():
                    raise ValueError("Database is missing")
                values = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
                if any(len(v) != 1 for v in values.values()):
                    raise ValueError("Query parameters must appear once")
                query = {k: v[0] for k, v in values.items()}
                with connect(db_path) as connection:
                    connection.execute("PRAGMA query_only = ON")
                    result = _route(connection, environ.get("PATH_INFO", ""), query, docs_dir)
        except repo.NotFoundError as exc:
            code, status = 404, "Not Found"
            result = {"error": "not_found", "detail": str(exc)}
        except KeyError as exc:
            code, status = 400, "Bad Request"
            result = {"error": "bad_request", "detail": f"Missing parameter: {exc.args[0]}"}
        except ValueError as exc:
            code, status = 400, "Bad Request"
            result = {"error": "bad_request", "detail": str(exc)}
        except sqlite3.DatabaseError:
            code, status = 400, "Bad Request"
            result = {"error": "bad_request", "detail": "The database could not be read"}
        body = json.dumps(result, default=repo.json_value, ensure_ascii=False).encode("utf-8")
        headers = [("Content-Type", "application/json"), ("Content-Length", str(len(body)))]
        if code == 405:
            headers.append(("Allow", "GET"))
        start_response(f"{code} {status}", headers)
        return [body]

    return app
