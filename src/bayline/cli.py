"""The operations desk command line."""

import argparse
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from wsgiref.simple_server import make_server

from . import policies, services
from . import repository as repo
from .config import database_path
from .db import connect
from .models import ClaimKind, ReturnCause
from .money import egp_to_piastres, format_egp
from .sample.load import checksum, seed_database
from .timeutil import format_day, parse_utc, to_utc_text
from .web import create_app


def parser():
    root = argparse.ArgumentParser(prog="bayline")
    commands = root.add_subparsers(dest="command", required=True)
    names = ("seed", "checksum", "stats", "shipment", "customer", "return-check", "claim-check",
        "address-check", "open-return", "open-claim", "change-address", "messages", "message",
        "reply", "policies", "policy", "serve", "llm-check")
    for name in names:
        command = commands.add_parser(name)
        command.add_argument("--db", type=Path, default=None)
        command.add_argument("--json", action="store_true")
        if name in ("stats", "shipment", "return-check", "claim-check", "address-check", "open-return", "open-claim", "change-address", "reply"):
            command.add_argument("--at")
        if name in ("shipment", "return-check", "claim-check", "address-check", "open-return", "open-claim", "change-address"):
            command.add_argument("tn")
        if name in ("customer", "message", "reply"):
            command.add_argument("id")
        if name == "policy":
            command.add_argument("slug")
        if name == "seed":
            command.add_argument("--force", action="store_true")
            command.add_argument("--seed", type=int, default=20261101)
        if name in ("claim-check", "open-claim"):
            command.add_argument("--kind", choices=list(ClaimKind), required=True)
            command.add_argument("--amount", required=True)
        if name in ("address-check", "change-address"):
            command.add_argument("--city", required=True)
        if name in ("open-return", "open-claim", "change-address", "reply"):
            command.add_argument("--by", required=True)
        if name == "open-return":
            command.add_argument("--reason", choices=list(ReturnCause), required=True)
        if name == "change-address":
            command.add_argument("--line", required=True)
        if name == "reply":
            command.add_argument("--body", required=True)
        if name == "messages":
            command.add_argument("--status", choices=("new", "answered", "closed"))
            command.add_argument("--limit", type=int, default=20)
        if name == "message":
            command.add_argument("--labels", action="store_true")
        if name == "serve":
            command.add_argument("--port", type=int, default=8080)
        if name == "llm-check":
            command.add_argument("--ping", action="store_true")
    return root


def _print(value, machine=False, text=None):
    if machine or text is None:
        print(json.dumps(value, default=repo.json_value, ensure_ascii=False, indent=2))
    else:
        print(text)


def _decision_text(decision):
    text = str(decision.reason)
    if hasattr(decision, "last_day") and decision.last_day is not None:
        return f"{text}: day {decision.day_number} of 30, last day {format_day(decision.last_day)}"
    if getattr(decision, "eligible", False):
        return f"{text}: payable {format_egp(decision.payable_piastres)}"
    return text


def _shipment_text(result):
    promised = format_day(result["promised_date"]) if result["promised_date"] else "not started"
    piece_word = "piece" if result["pieces"] == 1 else "pieces"
    day_word = "day" if result["late_business_days"] == 1 else "days"
    lines = [f"Shipment {result['tracking_number']}",
             f"{result['origin_city']} to {result['destination_city']}",
             f"Recipient: {result['recipient_id']} | Merchant: {result['merchant_id']}",
             f"Address: {result['address_line']}",
             f"Goods: {result['goods_description']} ({result['pieces']} {piece_word}, {result['weight_kg']} kg)",
             f"Category: {result['goods_category']}",
             f"Service: {result['service']} | Lane: {result['lane']} | Status: {result['status']}",
             f"Destination: {result['destination_country']} | Time zone: {result['destination_tz']}",
             f"Created: {to_utc_text(result['created_at'])}",
             f"Declared value: {format_egp(result['declared_value_piastres'])} | Insured: {'yes' if result['insured'] else 'no'}",
             f"Promised date: {promised}",
             f"Delay: {result['delay_class']} ({result['late_business_days']} business {day_word} late)",
             f"Fee: {format_egp(result['shipping_fee_piastres'])}", "Tracking history:"]
    lines.extend(f"  {to_utc_text(e.occurred_at)} {e.code}: {e.location}"
                 + (f" - {e.detail}" if e.detail else "") for e in result["events"])
    return "\n".join(lines)


def _stats_text(result):
    headings = {"shipments_by_status": "Shipments by status",
                "shipments_by_delay": "Shipments by delay",
                "messages_by_status": "Messages by status",
                "messages_by_topic": "Messages by topic"}
    return "\n".join(f"{headings[key]}:\n" + "\n".join(
        f"  {name.replace('_', ' ')}: {count}" for name, count in counts.items())
        for key, counts in result.items())


def _run_database(args, connection):
    command = args.command
    at = parse_utc(args.at) if getattr(args, "at", None) else repo.snapshot_time(connection)
    text = None
    exit_code = 0
    if command == "checksum":
        result = checksum(connection)
        text = result
    elif command == "stats":
        result = repo.stats(connection, at)
        text = _stats_text(result)
    elif command == "shipment":
        result = repo.shipment_summary(connection, args.tn, at)
        result["events"] = repo.get_events(connection, result["tracking_number"], at)
        text = _shipment_text(result)
    elif command == "customer":
        c = repo.get_customer(connection, args.id)
        result = {**asdict(c), "shipments": repo.customer_shipments(connection, c.id)}
        text = (f"Customer {c.id}: {c.name}\n{c.kind.title()} | {c.city}, {c.country}\n"
                f"Email: {c.email}\nPhone: {c.phone}\n"
                f"Returns plan: {'yes' if c.returns_plan else 'no'}\nShipments:\n"
                + "\n".join(f"  {s.tracking_number}: {s.origin_city} to {s.destination_city}"
                            for s in result["shipments"]))
    elif command in ("return-check", "claim-check", "address-check"):
        if command == "return-check":
            result = services.check_return(connection, args.tn, at)
        elif command == "claim-check":
            result = services.check_claim(connection, args.tn, args.kind, egp_to_piastres(args.amount), at)
        else:
            result = services.check_address_change(connection, args.tn, args.city, at)
        exit_code = 0 if getattr(result, "allowed", getattr(result, "eligible", False)) else 1
        text = _decision_text(result)
    elif command in ("open-return", "open-claim", "change-address"):
        if command == "open-return":
            case_id, decision = services.open_return(connection, args.tn, args.reason, args.by, at, include_id=True)
        elif command == "open-claim":
            case_id, decision = services.open_claim(connection, args.tn, args.kind, egp_to_piastres(args.amount), args.by, at, include_id=True)
        else:
            case_id, decision = services.record_address_change(connection, args.tn, args.city, args.line, args.by, at, include_id=True)
        exit_code = 0 if getattr(decision, "allowed", getattr(decision, "eligible", False)) else 1
        result = {"id": case_id, **asdict(decision)}
        text = case_id + ": " + _decision_text(decision)
    elif command == "messages":
        result = repo.list_messages(connection, args.status, args.limit)
        text = "\n".join(f"{m.id} {to_utc_text(m.received_at)} {m.status} {m.from_name}: {m.subject}" for m in result)
    elif command == "message":
        m = repo.get_message(connection, args.id)
        result = {**asdict(m), "replies": repo.get_replies(connection, m.id)}
        text = (f"Message {m.id} | {m.status}\nReceived: {to_utc_text(m.received_at)} ({m.channel})\n"
                f"From: {m.from_name} <{m.from_email}>\nSubject: {m.subject}\n"
                f"Assigned to: {m.assigned_to or 'unassigned'}\n\n{m.body}\n\nReplies:")
        if not result["replies"]:
            text += " none"
        for reply in result["replies"]:
            text += f"\n\nReply {reply.id} by {reply.author} at {to_utc_text(reply.sent_at)}:\n{reply.body}"
        if args.labels:
            result["labels"] = repo.get_labels(connection, m.id)
            text += "\n\nLabels:\n" + "\n".join(
                f"  {key.replace('_', ' ')}: {', '.join(value) if isinstance(value, tuple) else value}"
                for key, value in asdict(result["labels"]).items() if key != "message_id")
    elif command == "reply":
        result = {"id": services.record_reply(connection, args.id, args.by, args.body, at)}
        text = result["id"]
    else:
        raise ValueError("Unknown command")
    _print(result, args.json, text)
    return exit_code


def _llm_check(args):
    import os

    from .llm import ChatMessage, ChatRequest, ModelError, client_from_env

    try:
        client = client_from_env()
        mode = os.environ.get("BAYLINE_LLM_MODE") or "replay"
        result = {"mode": mode, "base address": os.environ.get("BAYLINE_LLM_BASE_URL") or "",
                  "model": os.environ.get("BAYLINE_LLM_MODEL") or "",
                  "key set": "yes" if os.environ.get("BAYLINE_LLM_API_KEY") else "no"}
        if args.ping and mode == "live":
            result["response"] = client.complete(ChatRequest((ChatMessage("user", "Hello."),), max_tokens=8)).text
        key = os.environ.get("BAYLINE_LLM_API_KEY")
        if key:
            result = {name: value.replace(key, "[redacted]") for name, value in result.items()}
        _print(result, args.json, "\n".join(f"{key}: {value}" for key, value in result.items()))
        return 0
    except ModelError as exc:
        _print({"error": str(exc)}, args.json, str(exc))
        return 2


def main(argv=None):
    try:
        args = parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        if args.command == "llm-check":
            return _llm_check(args)
        if args.command in ("policies", "policy"):
            result = policies.list_documents() if args.command == "policies" else policies.get_document(args.slug)
            text = "\n".join(f"{d['slug']}: {d['title']}" for d in result) if args.command == "policies" else result
            _print(result, args.json, text)
            return 0
        path = args.db or database_path()
        if args.command == "seed":
            counts = seed_database(path, args.seed, args.force)
            with connect(path) as connection:
                as_of = to_utc_text(repo.snapshot_time(connection))
            result = {"path": str(path), "seed": args.seed, "as_of": as_of, "counts": counts}
            _print(result, args.json, f"{path}\nseed {args.seed}\nas_of {as_of}\n" + "\n".join(f"{k} {v}" for k, v in counts.items()))
            return 0
        if not path.is_file():
            _print({"error": "Database missing or empty"}, args.json, "Database missing or empty")
            return 4
        with connect(path) as connection:
            try:
                repo.snapshot_time(connection)
            except (ValueError, sqlite3.DatabaseError):
                _print({"error": "Database missing or empty"}, args.json, "Database missing or empty")
                return 4
            if args.command != "serve":
                return _run_database(args, connection)
        if not 1 <= args.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        with make_server("127.0.0.1", args.port, create_app(path)) as server:
            _print({"host": "127.0.0.1", "port": args.port}, args.json, f"Serving on http://127.0.0.1:{args.port}")
            server.serve_forever()
        return 0
    except repo.NotFoundError as exc:
        _print({"error": str(exc)}, args.json, str(exc))
        return 3
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        _print({"error": str(exc)}, args.json, str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
