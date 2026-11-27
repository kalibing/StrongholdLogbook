"""QQ 机器人渠道：按 openid 建号（幂等）、一次性免密登录链接、首次设密码、一次性改账号名。"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from logbook import accounts, api, storage

ORIGIN = "http://localhost:8080"
HEADERS = {"Origin": ORIGIN}
APP_ID = "102000001"
OPENID = "E4F1A2B3C4D5E6F7A8B9C0D1E2F3A4B5"
PASSWORD = "my-new-password"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    with TestClient(api.app) as test_client:
        yield test_client


def bot_signup(openid=OPENID):
    with storage.connect() as database:
        return accounts.create_for_qq_openid(database, APP_ID, openid)


def issue(user, now=None):
    with storage.connect() as database:
        return accounts.issue_login_link(database, user["id"], now)


def link_login(client, token):
    client.cookies.clear()
    return client.post("/api/session/qq-link", json={"token": token}, headers=HEADERS)


def test_openid_signup_is_idempotent(client):
    user = bot_signup()
    assert user["username"].startswith("qq-")
    assert bot_signup()["username"] == user["username"]
    assert bot_signup("0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A")["username"] != user["username"]
    with storage.connect() as database:
        other_bot = accounts.create_for_qq_openid(database, "102000002", OPENID)
    assert other_bot["username"] != user["username"]


@pytest.mark.parametrize("openid", ["", "has space", "x" * 129, "semi;colon"])
def test_openid_is_validated(client, openid):
    with pytest.raises(accounts.AccountError), storage.connect() as database:
        accounts.create_for_qq_openid(database, APP_ID, openid)


def test_link_logs_in_once_and_asks_for_password(client):
    user = bot_signup()
    token = issue(user)
    response = link_login(client, token)
    assert response.status_code == 200
    assert response.json()["needs_password"] is True and response.json()["username_editable"] is True
    assert client.get("/api/session").json()["username"] == user["username"]
    assert link_login(client, token).status_code == 401


def test_expired_and_unknown_links_are_rejected(client):
    user = bot_signup()
    stale = issue(user, datetime.now(timezone.utc) - timedelta(minutes=11))
    assert link_login(client, stale).status_code == 401
    assert link_login(client, "not-a-real-token").status_code == 401
    assert link_login(client, "x" * 200).status_code == 422


def test_link_failures_share_the_ip_throttle(client, monkeypatch):
    monkeypatch.setattr(api.login_throttle, "limit", 2)
    user = bot_signup()
    link_login(client, "guess-1")
    link_login(client, "guess-2")
    assert link_login(client, issue(user)).status_code == 429


def test_set_initial_password_once_then_password_login(client):
    user = bot_signup()
    link_login(client, issue(user))
    response = client.put("/api/account/password", json={"password": PASSWORD}, headers=HEADERS)
    assert response.status_code == 200 and response.json()["needs_password"] is False
    again = client.put("/api/account/password", json={"password": "another-password"}, headers=HEADERS)
    assert again.status_code == 409
    client.cookies.clear()
    login = client.post("/api/session", json={"username": user["username"], "password": PASSWORD}, headers=HEADERS)
    assert login.status_code == 200


def test_web_accounts_cannot_use_initial_password(client):
    with storage.connect() as database:
        accounts.create_with_password(database, "webuser", "web-user-password")
    client.post("/api/session", json={"username": "webuser", "password": "web-user-password"}, headers=HEADERS)
    response = client.put("/api/account/password", json={"password": PASSWORD}, headers=HEADERS)
    assert response.status_code == 409


def test_initial_password_is_validated(client):
    user = bot_signup()
    link_login(client, issue(user))
    short = client.put("/api/account/password", json={"password": "short"}, headers=HEADERS)
    assert short.status_code == 422 and "short" not in short.text
    same = client.put("/api/account/password", json={"password": user["username"].upper()}, headers=HEADERS)
    assert same.status_code == 422
    assert client.get("/api/session").json()["needs_password"] is True


def test_bot_account_can_rename_exactly_once(client):
    user = bot_signup()
    link_login(client, issue(user))
    client.put("/api/account/password", json={"password": PASSWORD}, headers=HEADERS)
    renamed = client.patch("/api/account/username", json={"username": "doctor.kal"}, headers=HEADERS)
    assert renamed.status_code == 200
    assert renamed.json()["username"] == "doctor.kal" and renamed.json()["username_editable"] is False
    assert client.get("/api/session").json()["username"] == "doctor.kal"
    assert client.patch("/api/account/username", json={"username": "second-try"}, headers=HEADERS).status_code == 409
    client.cookies.clear()
    assert client.post("/api/session", json={"username": "doctor.kal", "password": PASSWORD}, headers=HEADERS).status_code == 200
    assert bot_signup()["username"] == "doctor.kal"


def test_rename_conflict_keeps_the_one_chance(client):
    taken = bot_signup("0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A")
    with storage.connect() as database:
        database.execute("UPDATE users SET username = %s WHERE id = %s", ("taken-name", taken["id"]))
    user = bot_signup()
    link_login(client, issue(user))
    assert client.patch("/api/account/username", json={"username": "taken-name"}, headers=HEADERS).status_code == 409
    assert client.get("/api/session").json()["username_editable"] is True
    assert client.patch("/api/account/username", json={"username": "qq-mine"}, headers=HEADERS).status_code == 409
    assert client.patch("/api/account/username", json={"username": "Bad Name"}, headers=HEADERS).status_code == 422
    assert client.patch("/api/account/username", json={"username": "free-name"}, headers=HEADERS).status_code == 200


def test_bot_signup_puts_generated_info_in_notification(client):
    user = bot_signup()
    link_login(client, issue(user))
    items = client.get("/api/notifications").json()["items"]
    assert [item["title"] for item in items] == [accounts.QQ_NOTICE_TITLE]
    assert user["username"] in items[0]["body"]
    bot_signup()  # 重复调用不再发通知
    assert len(client.get("/api/notifications").json()["items"]) == 1
