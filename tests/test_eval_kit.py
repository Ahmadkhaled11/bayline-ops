import json
from types import SimpleNamespace

import pytest

from bayline.assist.extract import build_request, extract_raw
from bayline.llm import ChatResponse, ModelError, RecordingClient, ReplayClient, request_key
from bayline.sample.authored import load_messages
from evals.kit import check_report, collect, labels, run_report


def parse(raw):
    if raw == "bad":
        raise ValueError("bad reply")
    return SimpleNamespace(primary_topic=raw)


class Client:
    def __init__(self, fail_after=None):
        self.calls = 0
        self.fail_after = fail_after

    def complete(self, request):
        if self.calls == self.fail_after:
            raise ModelError("unavailable")
        self.calls += 1
        return ChatResponse("other", "test", "stop")


def test_messages_and_starter():
    messages = load_messages()
    from bayline.config import ROOT

    rows = [json.loads(line) for line in (ROOT / "data/authored/messages.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert [m.id for m in messages] == [f"M-{n:05}" for n in range(1001, 1041)]
    assert [m.body for m in messages] == [row["body"] for row in rows]
    request = build_request(messages[0])
    assert request.model is None and request.messages[1].content == messages[0].body
    assert extract_raw(Client(), messages[0]) == "other"


def test_recovery_and_report(tmp_path):
    folder = tmp_path / "replies"
    (tmp_path / "evals/reports").mkdir(parents=True)
    messages = load_messages()
    first = Client(fail_after=7)
    with pytest.raises(ValueError, match="7 replies saved.*again keeps them"):
        run_report("first", folder, messages, labels(), parse,
                   lambda: RecordingClient(first, folder), root=tmp_path)
    assert not list((tmp_path / "evals/reports").glob("*.md"))
    second = Client()
    def factory():
        return RecordingClient(second, folder)

    run_report("first", folder, messages, labels(), parse, factory, root=tmp_path)
    assert second.calls == 33
    collect(messages, folder, lambda: pytest.fail("already saved"))
    path = tmp_path / "evals/reports/first.md"
    original = path.read_text(encoding="utf-8")
    check_report(path, messages, labels(), parse, root=tmp_path)
    with pytest.raises(ValueError, match="already exists"):
        run_report("first", folder, messages, labels(), parse, factory, root=tmp_path)
    path.write_text(original.replace("Overall: ", "Overall: 9"), encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="contents differ"):
        check_report(path, messages, labels(), parse, root=tmp_path)
    path.write_text(original, encoding="utf-8", newline="\n")
    files = sorted(folder.glob("*.json"))
    files[0].write_bytes(files[1].read_bytes())
    with pytest.raises(ValueError, match="Saved reply or request differs"):
        check_report(path, messages, labels(), parse, root=tmp_path)


def test_missing_and_outside(tmp_path):
    messages = load_messages()
    folder = tmp_path / "replies"
    with pytest.raises(ValueError, match=r"M-01001.*replies.*again keeps them"):
        collect(messages, folder, lambda: ReplayClient(folder))
    with pytest.raises(ValueError, match="inside the repository"):
        run_report("first", tmp_path.parent, messages, labels(), parse,
                   lambda: ReplayClient(folder), root=tmp_path)


def test_report_requires_saved_replies(tmp_path):
    (tmp_path / "evals/reports").mkdir(parents=True)
    with pytest.raises(ValueError, match="Replies must be saved"):
        run_report("live", tmp_path / "replies", load_messages(), labels(), parse,
                   Client, root=tmp_path)
    assert not list((tmp_path / "evals/reports").glob("*.md"))


def test_report_checks_after_prompt_change(tmp_path, monkeypatch):
    from bayline.assist import extract

    folder = tmp_path / "replies"
    (tmp_path / "evals/reports").mkdir(parents=True)
    messages = load_messages()
    run_report("before", folder, messages, labels(), parse,
               lambda: RecordingClient(Client(), folder), root=tmp_path)
    path = tmp_path / "evals/reports/before.md"
    monkeypatch.setattr(extract, "PROMPT", extract.PROMPT + " Use the handbook's topic meanings.")
    check_report(path, messages, labels(), parse, root=tmp_path)
    collect(messages, folder, lambda: RecordingClient(Client(), folder))
    assert len(list(folder.glob("*.json"))) == 2 * len(messages)
    check_report(path, messages, labels(), parse, root=tmp_path)


def test_reply_recorded_for_another_message_fails(tmp_path):
    folder = tmp_path / "replies"
    (tmp_path / "evals/reports").mkdir(parents=True)
    messages = load_messages()
    run_report("first", folder, messages, labels(), parse,
               lambda: RecordingClient(Client(), folder), root=tmp_path)
    path = tmp_path / "evals/reports/first.md"
    key = request_key(build_request(messages[0]))
    saved = folder / (key + ".json")
    data = json.loads(saved.read_text(encoding="utf-8"))
    data["request"]["messages"][1]["content"] = messages[1].body
    saved.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Saved reply or request differs for M-01001"):
        check_report(path, messages, labels(), parse, root=tmp_path)
