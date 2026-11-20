import json
from wsgiref.util import setup_testing_defaults

import pytest

from bayline.db import connect
from bayline.sample.load import checksum
from bayline.web import create_app


def request(app, path, query="", method="GET"):
    env = {}
    setup_testing_defaults(env)
    env.update(PATH_INFO=path, QUERY_STRING=query, REQUEST_METHOD=method)
    response = {}

    def start(status, headers):
        response["status"] = int(status.split()[0])
        response["headers"] = dict(headers)

    body = b"".join(app(env, start))
    assert response["headers"]["Content-Type"] == "application/json"
    assert int(response["headers"]["Content-Length"]) == len(body)
    return response["status"], json.loads(body)


@pytest.mark.parametrize("path,query,field,expected", [
    ("/health", "", "status", "ok"), ("/shipments/BYL260411871", "", "status", "delivered"),
    ("/shipments/BYL260411871/events", "", "events", None),
    ("/shipments/BYL260411871/checks/return", "at=2026-10-24T19:40:00Z", "reason", "ALLOWED"),
    ("/shipments/BYL260455803/checks/claim", "kind=damage&amount=8500&at=2026-10-26T07:00:00Z", "payable_piastres", 300000),
    ("/shipments/BYL260459136/checks/address", "city=Cairo&at=2026-11-02T06:45:00Z", "reason", "TOO_LATE"),
    ("/customers/CUS-00101", "", "id", "CUS-00101"), ("/messages", "status=new&limit=3", "messages", None),
    ("/messages/M-01001", "", "replies", None),
])
def test_routes(seeded_db, path, query, field, expected):
    code, result = request(create_app(seeded_db), path, query)
    assert code == 200 and field in result
    if expected is not None:
        assert result[field] == expected
    if path.startswith("/messages"):
        assert "labels" not in json.dumps(result)


@pytest.mark.parametrize("path,query,method,code,error", [
    ("/missing", "", "GET", 404, "not_found"), ("/shipments/BYL260480009", "", "GET", 404, "not_found"),
    ("/shipments/BYL260411872", "", "GET", 400, "bad_request"),
    ("/messages", "limit=bad", "GET", 400, "bad_request"), ("/messages", "status=bad", "GET", 400, "bad_request"),
    ("/health", "at=bad", "GET", 400, "bad_request"), ("/messages", "limit=1&limit=2", "GET", 400, "bad_request"),
    ("/shipments/BYL260411871/checks/claim", "", "GET", 400, "bad_request"),
    ("/health", "", "POST", 405, "method_not_allowed"), ("/messages/M-01001", "", "DELETE", 405, "method_not_allowed"),
])
def test_errors(seeded_db, path, query, method, code, error):
    status, result = request(create_app(seeded_db), path, query, method)
    assert (status, result["error"]) == (code, error)
    assert result["detail"]


def test_policies_and_read_only(seeded_db, tmp_path):
    (tmp_path / "policies").mkdir()
    (tmp_path / "policies/desk.md").write_text("# Desk\nRead the record.")
    app = create_app(seeded_db, tmp_path)
    with connect(seeded_db) as conn:
        before = checksum(conn)
    assert request(app, "/policies")[1]["documents"] == [{"slug": "desk", "title": "Desk"}]
    assert request(app, "/policies/desk")[1]["markdown"].startswith("# Desk")
    assert request(app, "/policies/%2e%2e%2fsecret")[0] == 404
    request(app, "/shipments/BYL260411871/checks/return")
    request(app, "/messages/M-01001", method="POST")
    with connect(seeded_db) as conn:
        assert checksum(conn) == before


def test_missing_database(tmp_path):
    path = tmp_path / "absent.db"
    assert request(create_app(path), "/health")[0] == 400
    assert not path.exists()
