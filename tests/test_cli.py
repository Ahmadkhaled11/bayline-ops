import json
import shutil
from pathlib import Path

import pytest

from bayline import cli
from bayline.db import connect


@pytest.mark.parametrize("machine", [False, True])
@pytest.mark.parametrize("args,code,needle", [
    (["checksum"], 0, ""), (["stats"], 0, "shipments_by_status"),
    (["shipment", "BYL260442157"], 0, "on_time"), (["customer", "CUS-00101"], 0, "Tarek"),
    (["return-check", "BYL260411871", "--at", "2026-10-24T19:40:00Z"], 0, "ALLOWED"),
    (["return-check", "BYL260439062", "--at", "2026-10-31T20:30:00Z"], 1, "WINDOW_CLOSED"),
    (["claim-check", "BYL260455803", "--kind", "damage", "--amount", "8500", "--at", "2026-10-26T07:00:00Z"], 0, "ELIGIBLE"),
    (["address-check", "BYL260459136", "--city", "Cairo", "--at", "2026-11-02T06:45:00Z"], 1, "TOO_LATE"),
    (["messages", "--status", "new", "--limit", "2"], 0, "M-"),
    (["message", "M-01001"], 0, "replies"), (["message", "M-01001", "--labels"], 0, "labels"),
])
def test_read_commands(seeded_db, capsys, args, code, needle, machine):
    assert cli.main(args + ["--db", str(seeded_db)] + (["--json"] if machine else [])) == code
    output = capsys.readouterr().out
    if args == ["checksum"]:
        expected = Path(__file__).with_name("fixtures").joinpath("sample_checksum.txt").read_text().strip()
        assert (json.loads(output) if machine else output.strip()) == expected
    else:
        text_needles = {"shipments_by_status": "Shipments by status", "replies": "Replies", "labels": "Labels"}
        assert (needle if machine else text_needles.get(needle, needle)) in output
    if machine:
        json.loads(output)
    if args == ["message", "M-01001"]:
        assert "labels" not in output


@pytest.mark.parametrize("args,code", [
    (["shipment", "BYL260411872"], 2), (["shipment", "BYL260480009"], 3),
    (["customer", "CUS-99999"], 3), (["messages", "--limit", "0"], 2),
    (["stats", "--at", "2026-10-01"], 2),
    (["claim-check", "BYL260455803", "--kind", "damage", "--amount", "nan"], 2),
    (["serve", "--port", "0"], 2), (["no-command"], 2),
])
def test_bad_inputs(seeded_db, args, code):
    assert cli.main(args + ["--db", str(seeded_db)]) == code


def test_missing_and_empty_database(tmp_path, capsys):
    path = tmp_path / "missing.db"
    assert cli.main(["stats", "--db", str(path), "--json"]) == 4
    assert not path.exists()
    path.touch()
    assert cli.main(["stats", "--db", str(path)]) == 4
    assert "Database missing or empty" in capsys.readouterr().out


def test_seed_force_and_json(tmp_path, capsys):
    path = tmp_path / "new.db"
    assert cli.main(["seed", "--db", str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["shipments"] == 400
    assert cli.main(["seed", "--db", str(path)]) == 2
    capsys.readouterr()
    assert cli.main(["seed", "--force", "--db", str(path)]) == 0
    assert "tracking_events 2647" in capsys.readouterr().out


@pytest.mark.parametrize("machine", [False, True])
def test_writing_commands(seeded_db, tmp_path, capsys, machine):
    path = tmp_path / "write.db"
    shutil.copyfile(seeded_db, path)
    tail = ["--db", str(path), "--by", "reem.adel"] + (["--json"] if machine else [])
    commands = [
        (["open-return", "BYL260411871", "--reason", "not_wanted", "--at", "2026-10-24T19:40:00Z"], 0, "RET-"),
        (["open-return", "BYL260415328", "--reason", "other"], 1, "RET-"),
        (["open-claim", "BYL260455803", "--kind", "damage", "--amount", "8500", "--at", "2026-10-26T07:00:00Z"], 0, "CLM-"),
        (["change-address", "BYL260462072", "--city", "Cairo", "--line", "8 Ribbon Row"], 0, "ADR-"),
        (["reply", "M-01001", "--body", "Thank you. We have your message."], 0, "REP-"),
    ]
    for args, code, prefix in commands:
        assert cli.main(args + tail) == code
        output = capsys.readouterr().out
        assert prefix in output
        if machine:
            json.loads(output)
    with connect(path) as conn:
        assert conn.execute("SELECT status FROM return_cases WHERE tracking_number='BYL260415328'").fetchone()[0] == "refused"


def test_policy_commands(tmp_path, monkeypatch, capsys):
    from bayline import policies

    (tmp_path / "policies").mkdir()
    (tmp_path / "policies/desk.md").write_text("# Desk\nRead the parcel record.")
    monkeypatch.setattr(policies, "docs_path", lambda: tmp_path)
    for args in (["policies"], ["policies", "--json"], ["policy", "desk"], ["policy", "desk", "--json"]):
        assert cli.main(args) == 0
        assert "Desk" in capsys.readouterr().out
    assert cli.main(["policy", "../secret"]) == 3


def test_serve_binds_loopback(seeded_db, monkeypatch):
    seen = []

    class Server:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def serve_forever(self):
            seen.append("served")

    def fake_server(host, port, app):
        assert host == "127.0.0.1" and port == 8080 and callable(app)
        return Server()

    monkeypatch.setattr(cli, "make_server", fake_server)
    assert cli.main(["serve", "--db", str(seeded_db)]) == 0
    assert seen == ["served"]
