"""SQLite 后端的完整链路：登录 → 上传 → worker 写库 → 查询。"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from logbook import storage
from logbook.api import app
from logbook.records import CHINA
from logbook.security import hasher
from logbook.worker import process_one

ORIGIN = "http://localhost:8080"
PASSWORD = "local-test-password"
HEADERS = {"Origin": ORIGIN}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    with TestClient(app) as test_client:
        with storage.connect() as database:
            database.execute(
                "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
                (uuid4(), "tester", hasher.hash(PASSWORD)),
            )
        response = test_client.post("/api/session", json={"username": "tester", "password": PASSWORD}, headers=HEADERS)
        assert response.status_code == 200
        yield test_client


def upload(client, fixtures):
    payload = (fixtures / "sample-snapshot.json").read_bytes()
    return client.post("/api/imports", content=payload, headers={**HEADERS, "Content-Type": "application/json"})


def drain():
    with storage.connect() as database:
        while process_one(database):
            pass


def test_import_and_query_flow(client, fixtures):
    assert client.get("/api/facets").json() == []

    response = upload(client, fixtures)
    assert response.status_code == 202, response.text
    assert response.json()["total"] == 6
    assert client.get("/api/imports").json()[0]["status"] == "pending"

    drain()

    jobs = client.get("/api/imports").json()
    assert jobs[0]["status"] == "done"
    assert jobs[0]["processed"] == 6
    finished = datetime.fromisoformat(jobs[0]["completed_at"])
    assert datetime.now(timezone.utc) - finished < timedelta(hours=1)

    facets = client.get("/api/facets").json()
    assert {(item["protocol"], item["play"]) for item in facets} == {
        ("V3_1", "独立模拟"), ("V3_1", "联合模拟"),
    }

    overview = client.get("/api/overview?scope=all").json()
    assert overview["matches"] == 5
    assert overview["wins"] == 3
    assert overview["excluded"] == 1
    assert overview["max_layers"] == 11
    assert len(overview["points"]) == 5

    with_exits = client.get("/api/overview?scope=all&include_exits=true").json()
    assert with_exits["matches"] == 6
    assert with_exits["total_coins"] == 451

    page = client.get("/api/matches?limit=4").json()
    assert page["total"] == 5 and page["pages"] == 2 and len(page["matches"]) == 4
    first = page["matches"][0]
    assert first["result"] == "loss"
    assert first["scenario"] == "伊比利亚分队"
    assert first["bond_layers"] == 6
    assert first["played_at"].startswith("2026-11-20T13:44:18")
    assert datetime.fromisoformat(first["played_at"]).astimezone(CHINA).hour == 21

    detail = client.get(f"/api/matches/{first['id']}").json()
    assert detail["bonds"] == [{"name": "伊比利亚", "layers": 5}, {"name": "奥术", "layers": 1}]
    assert [unit["name"] for unit in detail["squad"]] == ["斯卡蒂", "阿米娅"]
    assert detail["bosses"] == ["霜星"]

    operators = client.get("/api/operators").json()
    assert operators["with_squad"] == 5


def test_duplicate_import_is_idempotent(client, fixtures):
    assert upload(client, fixtures).status_code == 202
    drain()
    assert upload(client, fixtures).status_code == 202
    drain()

    totals = client.get("/api/overview?scope=all&include_exits=true").json()
    assert totals["matches"] == 6
    assert client.get("/api/matches?include_exits=true&limit=50").json()["total"] == 6


def test_upload_rejects_invalid_payload(client):
    response = client.post("/api/imports", content=b'{"matches": []}', headers={**HEADERS, "Content-Type": "application/json"})
    assert response.status_code == 422
    assert "1–5000" in response.json()["detail"]


def test_session_cookie_is_scoped_and_hardened(client):
    response = client.post("/api/session", json={"username": "tester", "password": PASSWORD}, headers=HEADERS)
    lowered = response.headers["set-cookie"].lower()
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert client.get("/api/session").json() == {"username": "tester"}
    assert client.delete("/api/session", headers=HEADERS).status_code == 204
    assert client.get("/api/session").status_code == 401


def test_matches_are_scoped_to_the_owner(client, fixtures):
    drain_after = upload(client, fixtures)
    assert drain_after.status_code == 202
    drain()

    with storage.connect() as database:
        database.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
            (uuid4(), "other", hasher.hash(PASSWORD)),
        )
    other = TestClient(app)
    login = other.post("/api/session", json={"username": "other", "password": PASSWORD}, headers=HEADERS)
    assert login.status_code == 200
    assert other.get("/api/matches").json()["total"] == 0
    assert other.get("/api/overview?scope=all").json()["matches"] == 0
