"""B 站扫码登录：状态查询、发二维码、扫码成功后加密保存 Cookie。"""

import pytest
from fastapi.testclient import TestClient

from logbook import api, bilibili, feeds, qqbot
from logbook.credentials import PREFIX
from logbook.storage import connect

GROUP = "G1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6"


class FakeClient:
    def __init__(self):
        self.messages, self.images = [], []

    def reply(self, target_type, openid, msg_id, content, seq=1):
        self.messages.append((seq, content))

    def reply_image(self, target_type, openid, msg_id, png, content="", seq=1):
        assert png.startswith(b"\x89PNG")
        self.images.append((target_type, openid, content))


class FakeBili:
    """按 URL 前缀返回预设响应；poll 接口按顺序吐出状态码。"""

    def __init__(self, logged_in_cookie="", polls=(0,)):
        self.logged_in_cookie = logged_in_cookie
        self.polls = list(polls)
        self.calls = []

    def __call__(self, url, cookie="", parse=True):
        self.calls.append(url)
        if url.startswith(bilibili.NAV_URL):
            ok = bool(cookie) and (cookie == self.logged_in_cookie or "SESSDATA=s3" in cookie)
            data = {"isLogin": True, "uname": "方舟小号"} if ok else {"isLogin": False}
            return bilibili.Response({"code": 0 if ok else -101, "data": data}, {})
        if url.startswith(bilibili.QR_GENERATE_URL):
            return bilibili.Response({"code": 0, "data": {"url": "https://account.bilibili.com/qr?x=1",
                                                          "qrcode_key": "k1"}}, {})
        if url.startswith(bilibili.QR_POLL_URL.format(key="")):
            code = self.polls.pop(0)
            cookies = {"SESSDATA": "s3", "bili_jct": "j", "DedeUserID": "42", "other": "x"} if code == 0 else {}
            return bilibili.Response({"code": 0, "data": {"code": code}}, cookies)
        if url == bilibili.HOME_URL:
            return bilibili.Response({}, {"buvid3": "b3", "b_nut": "1"})
        raise AssertionError(url)


@pytest.fixture()
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    monkeypatch.delenv("LOGBOOK_CREDENTIAL_KEY", raising=False)
    monkeypatch.delenv("BILIBILI_COOKIE", raising=False)
    with TestClient(api.app):
        pass
    yield


def run(client, fake, target_type="group"):
    qqbot.handle_bili(client, target_type, GROUP, "msg-1", get=fake, sleep=lambda _: None)


def test_logged_in_reports_status_without_qr(database, monkeypatch):
    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=env")
    client, fake = FakeClient(), FakeBili(logged_in_cookie="SESSDATA=env")
    run(client, fake)
    assert client.images == [] and "B 站已登录：方舟小号" in client.messages[0][1]


def test_qr_login_saves_encrypted_cookie(database):
    client, fake = FakeClient(), FakeBili(polls=[86101, 86090, 0])
    with connect() as db:
        assert not bilibili.has_cookie(db)
    run(client, fake)
    assert client.images == [("group", GROUP, "B 站未登录，请用 B 站 App 扫码并确认登录（3 分钟内有效）。")]
    assert client.messages == [(2, "B 站登录成功：方舟小号。动态推送会使用这个账号。")]
    with connect() as db:
        raw = db.execute("SELECT cookie, uname FROM bili_credentials").fetchone()
        assert raw["cookie"].startswith(PREFIX) and "s3" not in raw["cookie"] and raw["uname"] == "方舟小号"
        cookie = bilibili.stored_cookie(db)
        assert bilibili.has_cookie(db)
    assert cookie == "SESSDATA=s3; bili_jct=j; DedeUserID=42; buvid3=b3; b_nut=1"
    # 登录后再查询只报状态
    client2 = FakeClient()
    run(client2, fake)
    assert client2.images == [] and "已登录" in client2.messages[0][1]


def test_expired_qr_saves_nothing(database):
    client, fake = FakeClient(), FakeBili(polls=[86101, 86038])
    run(client, fake, "c2c")
    assert client.messages == [(2, "二维码已过期，需要时请重新 @我 发「B站登录」。")]
    with connect() as db:
        assert not bilibili.has_cookie(db)


def test_invalid_cookie_says_expired_login(database, monkeypatch):
    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=old")
    client, fake = FakeClient(), FakeBili(polls=[86038])
    run(client, fake)
    assert client.images[0][2].startswith("B 站登录已失效")


def test_only_one_qr_at_a_time(database):
    client, fake = FakeClient(), FakeBili()
    assert qqbot.bili_login_lock.acquire(blocking=False)
    try:
        run(client, fake)
    finally:
        qqbot.bili_login_lock.release()
    assert client.images == [] and "等待扫码" in client.messages[0][1]


def test_wait_for_scan_times_out():
    ticks = iter(range(0, 1000, 100))
    fake = FakeBili(polls=[86101] * 10)
    assert bilibili.wait_for_scan("k", fake, lambda _: None, lifetime=180, clock=lambda: next(ticks)) is None


def test_bili_commands_and_subscribe_hint(database):
    assert qqbot.is_bili_command(" /B站状态") and qqbot.is_bili_command("b站登录")
    assert not qqbot.is_bili_command("订阅动态")
    with connect() as db:
        reply = feeds.handle_command(db, "102000001", "group", GROUP, "订阅动态")
    assert "B站状态" in reply
