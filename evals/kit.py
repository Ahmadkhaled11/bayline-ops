"""Collect saved replies and produce reproducible topic reports."""

import hashlib
import json
import os
import re
from pathlib import Path

from bayline.assist.extract import build_request
from bayline.config import ROOT
from bayline.llm import ModelError, ReplayClient, client_from_env, request_key
from bayline.models import Topic
from bayline.sample.authored import load_messages

NO_ANSWER = "(no answer)"


def relative_folder(folder, root=ROOT):
    try:
        return Path(folder).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        raise ValueError("Replies folder must be inside the repository") from None


def labels():
    path = ROOT / "data/authored/messages.jsonl"
    return {row["id"]: row["labels"]["primary_topic"] for row in
            (json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines())}


def collect(messages, folder, client_factory):
    """Reuse saved replies and request only missing ones."""
    folder = Path(folder)
    replay = ReplayClient(folder)
    client = None
    results = {}
    for message in messages:
        request = build_request(message)
        key = request_key(request)
        try:
            if (folder / (key + ".json")).is_file():
                reply = replay.complete(request)
            else:
                if client is None:
                    client = client_factory()
                if isinstance(client, ReplayClient):
                    raise ValueError(f"Missing reply for {message.id} in {folder}")
                reply = client.complete(request)
            results[message.id] = (key, reply.text)
        except ModelError:
            count = len(list(folder.glob("*.json"))) if folder.exists() else 0
            raise ValueError(f"Model error for {message.id}; {count} replies saved in the folder. "
                             "Running it again keeps them.") from None
        except ValueError as exc:
            count = len(list(folder.glob("*.json"))) if folder.exists() else 0
            raise ValueError(f"{exc}; {count} replies saved in the folder. "
                             "Running it again keeps them.") from None
    return results


def score(messages, expected, replies, parse):
    rows = []
    for message in sorted(messages, key=lambda item: item.id):
        key, text = replies[message.id]
        try:
            predicted = str(parse(text).primary_topic)
        except ValueError:
            predicted = NO_ANSWER
        rows.append((message.id, str(expected[message.id]), predicted, key))
    return rows


def tables(rows):
    topics = [topic.value for topic in Topic if any(row[1] == topic for row in rows)]
    predicted = [topic.value for topic in Topic if any(row[2] == topic for row in rows)]
    predicted += sorted({row[2] for row in rows} - set(predicted) - {NO_ANSWER})
    if any(row[2] == NO_ANSWER for row in rows):
        predicted.append(NO_ANSWER)
    topic_lines = ["| Topic | Right | Of | Accuracy |", "| --- | ---: | ---: | ---: |"]
    for topic in topics:
        relevant = [row for row in rows if row[1] == topic]
        right = sum(row[2] == topic for row in relevant)
        topic_lines.append(f"| {topic} | {right} | {len(relevant)} | {right / len(relevant):.0%} |")
    confusion = ["| Label / predicted | " + " | ".join(predicted) + " |",
                 "| --- | " + " | ".join("---:" for _ in predicted) + " |"]
    for topic in topics:
        counts = [str(sum(row[1] == topic and row[2] == value for row in rows))
                  for value in predicted]
        confusion.append("| " + topic + " | " + " | ".join(counts) + " |")
    return "\n".join(topic_lines), "\n".join(confusion)


def render(name, folder, rows):
    topic_table, confusion = tables(rows)
    right = sum(label == predicted for _, label, predicted, _ in rows)
    details = ["| Message | Label topic | Predicted topic | Reply key |",
               "| --- | --- | --- | --- |"]
    details.extend("| " + " | ".join(row) + " |" for row in rows)
    return (f"# {name}\n\nReplies: `{folder}`\n\nOverall: {right} / {len(rows)}\n\n"
            f"{topic_table}\n\n{confusion}\n\n" + "\n".join(details) + "\n")


def saved_reply(folder, key, message):
    """Read the reply a report names, and check it was recorded for that message."""
    path = Path(folder) / (key + ".json")
    differs = ValueError(f"Saved reply or request differs for {message.id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        request, text = data["request"], data["response"]["text"]
        users = [item["content"] for item in request["messages"] if item["role"] == "user"]
        value = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (OSError, ValueError, KeyError, TypeError):
        raise differs from None
    if (data["key"] != key or hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] != key
            or users != [message.body] or not isinstance(text, str)):
        raise differs
    return text


def check_report(path, messages, expected, parse, root=ROOT):
    """Verify reply ownership and reproduce a committed report.

    The replies are found by the keys the report lists, not by the current prompt,
    so a report made before a prompt change still checks after it.
    """
    text = Path(path).read_bytes().decode("utf-8")
    match = re.search(r"^Replies: `([^`]+)`$", text, re.MULTILINE)
    if not match:
        raise ValueError("Report replies folder differs")
    folder = Path(root) / match.group(1)
    if relative_folder(folder, root) != match.group(1):
        raise ValueError("Report replies folder differs")
    entries = re.findall(r"^\| (M-[0-9]+) \| [^|]+ \| [^|]+ \| ([0-9a-f]{16}) \|$",
                         text, re.MULTILINE)
    if len(entries) != len(messages) or {item[0] for item in entries} != {m.id for m in messages}:
        raise ValueError("Report message list differs")
    keys = dict(entries)
    replies = {message.id: (keys[message.id], saved_reply(folder, keys[message.id], message))
               for message in messages}
    if render(Path(path).stem, match.group(1), score(messages, expected, replies, parse)) != text:
        raise ValueError("Report contents differ from rescored replies")


def run_report(name, folder, messages, expected, parse, client_factory, root=ROOT):
    if not re.fullmatch(r"[a-z0-9-]+", name):
        raise ValueError("Report name must use lowercase letters, digits and dashes")
    relative = relative_folder(folder, root)
    path = Path(root) / "evals/reports" / (name + ".md")
    if path.exists():
        raise ValueError("Report already exists")
    replies = collect(messages, folder, client_factory)
    if any(not (Path(folder) / (key + ".json")).is_file() for key, _ in replies.values()):
        raise ValueError("Replies must be saved before writing a report; use record mode")
    rows = score(messages, expected, replies, parse)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(render(name, relative, rows))
    return tables(rows)


def settings_folder():
    return Path(os.environ.get("BAYLINE_LLM_REPLAY_DIR") or ROOT / "data/llm_replies")


def main(argv=None):
    import argparse

    from bayline.assist import extract

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("collect")
    report = sub.add_parser("report")
    report.add_argument("name")
    args = parser.parse_args(argv)
    try:
        messages = load_messages()
        folder = settings_folder()
        if args.command == "collect":
            collect(messages, folder, client_from_env)
            print(f"Collected {len(messages)} replies.")
        else:
            if not hasattr(extract, "parse_extraction"):
                raise ValueError("bayline.assist.extract has no parse_extraction yet; collect works without it")
            topic_table, confusion = run_report(args.name, folder, messages, labels(),
                                                extract.parse_extraction, client_from_env)
            print(topic_table + "\n\n" + confusion)
    except (ValueError, ModelError, OSError) as exc:
        print(str(exc) if isinstance(exc, ValueError) else "Could not complete the operation.")
        return 1
    return 0
