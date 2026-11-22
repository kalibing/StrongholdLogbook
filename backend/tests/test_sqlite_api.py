"""SQLite 后端的完整链路：登录 → 建档 → 上传 → worker 写库 → 查询 → 删除。

这些用例走真实的 HTTP 请求与真实的 SQLite 文件，不需要 PostgreSQL。
"""

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


def create_role(client, name="主号"):
    response = client.post("/api/roles", json={"name": name}, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, role_id, fixtures):
    payload = (fixtures / "sample-snapshot.json").read_bytes()
    return client.post(
        f"/api/roles/{role_id}/imports", content=payload,
        headers={**HEADERS, "Content-Type": "application/json"},
    )


def drain():
    with storage.connect() as database:
        while process_one(database):
            pass


def test_import_and_query_flow(client, fixtures):
    role = create_role(client)
    assert client.get(f"/api/roles/{role['id']}/facets").json() == []

    response = upload(client, role["id"], fixtures)
    assert response.status_code == 202, response.text
    assert response.json()["total"] == 6
    jobs = client.get(f"/api/roles/{role['id']}/imports").json()
    assert jobs[0]["status"] == "pending"

    drain()

    jobs = client.get(f"/api/roles/{role['id']}/imports").json()
    assert jobs[0]["status"] == "done"
    assert jobs[0]["processed"] == 6
    finished = datetime.fromisoformat(jobs[0]["completed_at"])
    assert datetime.now(timezone.utc) - finished < timedelta(hours=1)

    facets = client.get(f"/api/roles/{role['id']}/facets").json()
    assert {(item["protocol"], item["play"]) for item in facets} == {
        ("V3_1", "独立模拟"), ("V3_1", "联合模拟"),
    }

    overview = client.get(f"/api/roles/{role['id']}/overview?scope=all").json()
    assert overview["matches"] == 5
    assert overview["wins"] == 3
    assert overview["excluded"] == 1
    assert overview["max_layers"] == 11
    assert overview["start"] == "2026-11-16"
    assert len(overview["points"]) == 5

    with_exits = client.get(f"/api/roles/{role['id']}/overview?scope=all&include_exits=true").json()
    assert with_exits["matches"] == 6
    assert with_exits["excluded"] == 0
    assert with_exits["total_coins"] == 451

    daily = client.get(f"/api/roles/{role['id']}/overview?scope=day").json()
    assert [point["label"] for point in daily["points"]] == [
        "2026-11-16", "2026-11-17", "2026-11-19", "2026-11-20",
    ]

    page = client.get(f"/api/roles/{role['id']}/matches?limit=4").json()
    assert page["total"] == 5 and page["pages"] == 2 and len(page["matches"]) == 4
    first = page["matches"][0]
    assert first["result"] == "loss"
    assert first["scenario"] == "深海猎人分队"
    assert first["bond_layers"] == 6
    assert first["played_at"].startswith("2026-11-20T13:44:18")
    assert datetime.fromisoformat(first["played_at"]).astimezone(CHINA).hour == 21

    losses = client.get(f"/api/roles/{role['id']}/matches?result=loss").json()
    assert losses["total"] == 2

    detail = client.get(f"/api/roles/{role['id']}/matches/{first['id']}").json()
    assert detail["bonds"] == [{"name": "深海猎人", "layers": 5}, {"name": "术师", "layers": 1}]
    assert [unit["name"] for unit in detail["squad"]] == ["斯卡蒂", "阿米娅"]
    assert detail["bosses"] == ["霜星"]
    assert detail["trophies"] == -18

    operators = client.get(f"/api/roles/{role['id']}/operators").json()
    assert operators["with_squad"] == 5
    names = [row["name"] for row in operators["operators"]]
    assert "阿米娅" in names
    assert operators["operators"][0]["count"] >= operators["operators"][-1]["count"]


def test_duplicate_import_is_idempotent(client, fixtures):
    role = create_role(client)
    assert upload(client, role["id"], fixtures).status_code == 202
    drain()
    assert upload(client, role["id"], fixtures).status_code == 202
    drain()

    totals = client.get(f"/api/roles/{role['id']}/overview?scope=all&include_exits=true").json()
    assert totals["matches"] == 6
    page = client.get(f"/api/roles/{role['id']}/matches?include_exits=true&limit=50").json()
    assert page["total"] == 6


def test_role_lifecycle_and_conflicts(client):
    first = create_role(client, "主号")
    duplicate = client.post("/api/roles", json={"name": "主号"}, headers=HEADERS)
    assert duplicate.status_code == 409

    renamed = client.patch(f"/api/roles/{first['id']}", json={"name": "二号"}, headers=HEADERS)
    assert renamed.status_code == 200
    assert [role["name"] for role in client.get("/api/roles").json()] == ["二号"]

    second = create_role(client, "小号")
    conflict = client.patch(f"/api/roles/{first['id']}", json={"name": "小号"}, headers=HEADERS)
    assert conflict.status_code == 409
    assert client.delete(f"/api/roles/{second['id']}", headers=HEADERS).status_code == 204

    assert client.delete(f"/api/roles/{first['id']}", headers=HEADERS).status_code == 204
    assert client.get(f"/api/roles/{first['id']}/matches").status_code == 404
    assert client.get("/api/roles").json() == []


def test_upload_rejects_invalid_payload(client):
    role = create_role(client)
    response = client.post(
        f"/api/roles/{role['id']}/imports", content=b'{"matches": []}',
        headers={**HEADERS, "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "1–5000" in response.json()["detail"]


def test_session_cookie_is_scoped_and_hardened(client):
    response = client.post("/api/session", json={"username": "tester", "password": PASSWORD}, headers=HEADERS)
    cookie = response.headers["set-cookie"]
    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert client.get("/api/session").json() == {"username": "tester"}
    assert client.delete("/api/session", headers=HEADERS).status_code == 204
    assert client.get("/api/session").status_code == 401
