"""注册（开关 / 邀请码 / 按 IP 限制）与按账号的每日额度。"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from logbook import api, daily_review
from logbook.limits import client_key

ORIGIN = "http://localhost:8080"
HEADERS = {"Origin": ORIGIN}


@pytest.fixture()
def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    clients = []

    def factory(mode="open", invite=""):
        monkeypatch.setenv("LOGBOOK_REGISTRATION", mode)
        monkeypatch.setenv("LOGBOOK_INVITE_CODE", invite)
        client = TestClient(api.app)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def register(client, qq, **extra):
    return client.post("/api/register", json={"qq": qq, **extra}, headers=HEADERS)


def test_registration_is_off_by_default(make_client, monkeypatch):
    client = make_client(mode="")
    assert client.get("/api/registration").json() == {"enabled": False, "invite": False}
    assert register(client, "10001").status_code == 403


def test_qq_registration_generates_password_and_logs_in(make_client):
    client = make_client()
    assert client.get("/api/registration").json() == {"enabled": True, "invite": False}
    response = register(client, "123456789")
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["username"] == "123456789"
    password = body["password"]
    assert len(password) == 16 and password.isalnum()
    assert client.get("/api/session").json() == {key: value for key, value in body.items() if key != "password"}
    client.cookies.clear()
    login = client.post("/api/session", json={"username": "123456789", "password": password}, headers=HEADERS)
    assert login.status_code == 200


def test_passwords_are_random(make_client):
    client = make_client()
    first = register(client, "10001").json()["password"]
    client.cookies.clear()
    second = register(client, "10002").json()["password"]
    assert first != second


@pytest.mark.parametrize("qq", ["1234", "012345", "123456789012", "12345a", " 12345", "newcomer"])
def test_registration_rejects_invalid_qq(make_client, qq):
    response = register(make_client(), qq)
    assert response.status_code == 422
    assert qq not in response.text


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


def test_failed_attempts_are_throttled(make_client):
    client = make_client(mode="invite", invite="secret-invite")
    for _ in range(10):
        assert register(client, "10001", invite_code="wrong-guess").status_code == 403
    assert register(client, "10001", invite_code="secret-invite").status_code == 429


def test_invite_code_is_required(make_client):
    client = make_client(mode="invite", invite="secret-invite")
    assert client.get("/api/registration").json() == {"enabled": True, "invite": True}
    assert register(client, "10001").status_code == 403
    assert register(client, "10001", invite_code="secret-invite").status_code == 201


def test_invite_mode_without_code_fails_at_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    monkeypatch.setenv("LOGBOOK_REGISTRATION", "invite")
    monkeypatch.delenv("LOGBOOK_INVITE_CODE", raising=False)
    with pytest.raises(ValueError):
        with TestClient(api.app):
            pass


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
