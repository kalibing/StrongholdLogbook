"""站内通知：全站公告 + 个人通知、已读状态、隔离与命令行。"""

import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from logbook import admin, api, notifications, storage
from logbook.security import hasher

ORIGIN = "http://localhost:8080"
HEADERS = {"Origin": ORIGIN}
PASSWORD = "local-test-password"


@pytest.fixture()
def site(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    monkeypatch.setenv("LOGBOOK_REGISTRATION", "open")
    with TestClient(api.app) as client:
        ids = {}
        with storage.connect() as database:
            for name in ("alice", "bob"):
                ids[name] = uuid4()
                database.execute(
                    "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
                    (ids[name], name, hasher.hash(PASSWORD)),
                )
        yield client, ids


def login(client, name):
    client.cookies.clear()
    assert client.post("/api/session", json={"username": name, "password": PASSWORD}, headers=HEADERS).status_code == 200


def test_requires_login(site):
    client, _ = site
    assert client.get("/api/notifications").status_code == 401
    assert client.post("/api/notifications/read", json={}, headers=HEADERS).status_code == 401


def test_announcements_and_personal_notices_are_isolated(site):
    client, ids = site
    with storage.connect() as database:
        notifications.create(database, "维护通知", "今晚 23:00 维护")
        notifications.create(database, "给 alice", "只有 alice 能看到", ids["alice"])
    login(client, "alice")
    alice = client.get("/api/notifications").json()
    assert alice["unread"] == 2
    assert {item["kind"] for item in alice["items"]} == {"announcement", "personal"}
    login(client, "bob")
    bob = client.get("/api/notifications").json()
    assert [item["title"] for item in bob["items"]] == ["维护通知"]


def test_mark_read_is_per_user(site):
    client, ids = site
    with storage.connect() as database:
        first = notifications.create(database, "公告一", "正文")
        notifications.create(database, "公告二", "正文")
    login(client, "alice")
    assert client.post("/api/notifications/read", json={"ids": [str(first)]}, headers=HEADERS).status_code == 204
    assert client.get("/api/notifications").json()["unread"] == 1
    assert client.post("/api/notifications/read", json={}, headers=HEADERS).status_code == 204
    assert client.get("/api/notifications").json()["unread"] == 0
    login(client, "bob")
    assert client.get("/api/notifications").json()["unread"] == 2


def test_cannot_mark_other_users_notice(site):
    client, ids = site
    with storage.connect() as database:
        private = notifications.create(database, "给 bob", "正文", ids["bob"])
    login(client, "alice")
    client.post("/api/notifications/read", json={"ids": [str(private)]}, headers=HEADERS)
    with storage.connect() as database:
        assert database.execute("SELECT count(*) AS n FROM notification_reads").fetchone()["n"] == 0


def test_registration_sends_welcome_notice(site):
    client, _ = site
    client.cookies.clear()
    assert client.post("/api/register", json={"qq": "123456789"}, headers=HEADERS).status_code == 201
    items = client.get("/api/notifications").json()["items"]
    assert [item["title"] for item in items] == [api.WELCOME_TITLE]
    assert "密码" in items[0]["body"]


def test_content_is_cleaned_and_bounded():
    assert notifications.clean(" 标题\x07 ", 60, "标题", False) == "标题"
    assert notifications.clean("一行\r\n两行", 100, "正文", True) == "一行\n两行"
    with pytest.raises(notifications.NotificationError):
        notifications.clean("x" * 61, 60, "标题", False)
    with pytest.raises(notifications.NotificationError):
        notifications.clean("\x00 ", 60, "标题", False)


def test_admin_commands(site, monkeypatch, capsys):
    client, _ = site
    monkeypatch.setattr(sys, "argv", ["admin", "announce", "公告", r"第一行\n第二行"])
    admin.main()
    monkeypatch.setattr(sys, "argv", ["admin", "notify", "bob", "私信", "只给 bob"])
    admin.main()
    login(client, "bob")
    items = client.get("/api/notifications").json()["items"]
    assert {item["title"] for item in items} == {"公告", "私信"}
    assert next(item for item in items if item["title"] == "公告")["body"] == "第一行\n第二行"
    notice_id = next(item["id"] for item in items if item["title"] == "私信")
    monkeypatch.setattr(sys, "argv", ["admin", "remove-notice", notice_id])
    admin.main()
    assert [item["title"] for item in client.get("/api/notifications").json()["items"]] == ["公告"]
    monkeypatch.setattr(sys, "argv", ["admin", "notify", "nobody", "t", "b"])
    with pytest.raises(SystemExit):
        admin.main()
