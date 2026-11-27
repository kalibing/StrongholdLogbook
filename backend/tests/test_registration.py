"""注册（开关 / 邀请码 / 按 IP 限制）与按账号的每日额度。"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from logbook import api, daily_review
from logbook.limits import client_key

ORIGIN = "http://localhost:8080"
HEADERS = {"Origin": ORIGIN}
PASSWORD = "my-own-password"


@pytest.fixture()
def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    clients = []

    def factory(mode="open"):
        monkeypatch.setenv("LOGBOOK_REGISTRATION", mode)
        client = TestClient(api.app)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def register(client, username, password=PASSWORD):
    return client.post("/api/register", json={"username": username, "password": password}, headers=HEADERS)


def test_registration_is_off_by_default(make_client, monkeypatch):
    client = make_client(mode="")
    assert client.get("/api/registration").json() == {"enabled": False}
    assert register(client, "10001").status_code == 403


def test_registration_uses_own_password_and_logs_in(make_client):
    client = make_client()
    assert client.get("/api/registration").json() == {"enabled": True}
    response = register(client, "doctor.kal")
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "doctor.kal" and "password" not in body
    assert client.get("/api/session").json() == body
    client.cookies.clear()
    login = client.post("/api/session", json={"username": "doctor.kal", "password": PASSWORD}, headers=HEADERS)
    assert login.status_code == 200


@pytest.mark.parametrize("password", ["short", "x" * 257])
def test_registration_rejects_bad_password_length(make_client, password):
    response = register(make_client(), "doctor.kal", password)
    assert response.status_code == 422
    assert "密码" in response.json()["detail"]
    assert password not in response.text


def test_password_must_differ_from_username(make_client):
    assert register(make_client(), "doctor.kal.1", "Doctor.Kal.1").status_code == 422


@pytest.mark.parametrize("username", ["ab", "Bad Name", "_lead", "x" * 65, "中文账号"])
def test_registration_rejects_invalid_username(make_client, username):
    response = register(make_client(), username)
    assert response.status_code == 422
    assert username not in response.text


def test_qq_prefix_is_reserved_for_bot(make_client):
    assert register(make_client(), "qq-squatter").status_code == 422


def test_web_accounts_cannot_rename(make_client):
    client = make_client()
    assert register(client, "doctor.kal").json()["username_editable"] is False
    response = client.patch("/api/account/username", json={"username": "another"}, headers=HEADERS)
    assert response.status_code == 409


def test_registration_requires_cross_site_protection(make_client):
    client = make_client()
    response = client.post("/api/register", json={"qq": "10001"})
    assert response.status_code == 403


def test_duplicate_username_is_rejected(make_client):
    client = make_client()
    assert register(client, "10001").status_code == 201
    response = register(client, "10001")
    assert response.status_code == 409
    assert "password" not in response.json()


def test_ip_quota_limits_accounts_per_network(make_client):
    client = make_client()
    assert register(client, "10001").status_code == 201
    assert register(client, "10002").status_code == 201
    response = register(client, "10003")
    assert response.status_code == 429
    assert "上限" in response.json()["detail"]



@pytest.mark.parametrize(("host", "key"), [
    ("203.0.113.7", "203.0.113.7"),
    ("2001:db8:1:2:aaaa::1", "2001:db8:1:2::/64"),
    ("2001:db8:1:2:bbbb::9", "2001:db8:1:2::/64"),
    ("::ffff:198.51.100.4", "198.51.100.4"),
])
def test_ipv6_clients_are_grouped_by_prefix(host, key):
    assert client_key(SimpleNamespace(client=SimpleNamespace(host=host))) == key


def test_ai_review_is_limited_to_two_successes_per_day(make_client, monkeypatch):
    client = make_client()
    register(client, "10001")
    monkeypatch.setattr(daily_review, "model_config", lambda: object())
    monkeypatch.setattr(api, "daily_review_data", lambda *_: {"wins": {"matches": 1}, "losses": {"matches": 0}})
    outcomes = iter([ValueError("upstream"), "ok", "ok", "ok"])

    def analyze(_config, _recap):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(daily_review, "analyze", analyze)
    statuses = [client.post("/api/daily-review?day=2026-11-20", headers=HEADERS).status_code for _ in range(4)]
    # 上游失败（502）不占额度，所以还能成功两次，第四次才被拒绝
    assert statuses == [502, 200, 200, 429]


def test_failed_attempts_are_throttled(make_client):
    client = make_client()
    assert register(client, "taken").status_code == 201
    client.cookies.clear()
    for _ in range(10):
        assert register(client, "taken").status_code == 409
    assert register(client, "fresh-name").status_code == 429
