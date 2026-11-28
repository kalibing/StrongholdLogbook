"""QQ 机器人回调：地址校验、验签、去重、发「登录」拿到可用的一次性链接。"""

from datetime import datetime, timedelta
import json
import time

import pytest
from fastapi.testclient import TestClient

from logbook import accounts, api, qqbot, storage, worker
from logbook.records import CHINA

ORIGIN = "http://localhost:8080"
SECRET = "test-bot-secret"
CONFIG = qqbot.BotConfig("102000001", SECRET)
OPENID = "E4F1A2B3C4D5E6F7A8B9C0D1E2F3A4B5"


class FakeClient:
    def __init__(self):
        self.replies = []
        self.group_replies = []
        self.images = []

    def reply_c2c(self, openid, msg_id, content, seq=1):
        self.replies.append({"openid": openid, "msg_id": msg_id, "content": content})

    def reply_group(self, group_openid, msg_id, content, seq=1):
        self.group_replies.append((group_openid, msg_id, content))

    def reply_image(self, target_type, openid, msg_id, png, content="", seq=1):
        self.images.append((target_type, openid, msg_id, png))


@pytest.fixture()
def bot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    qqbot.link_quota._failures.clear()
    qqbot.report_quota._failures.clear()
    client = FakeClient()
    with TestClient(api.app):  # 建表
        pass
    yield TestClient(qqbot.create_app(CONFIG, client)), client


def signed(payload, timestamp=None, config=CONFIG):
    body = json.dumps(payload).encode()
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    signature = qqbot.sign(config, timestamp.encode() + body)
    headers = {
        "Content-Type": "application/json", "X-Bot-Appid": config.app_id,
        "X-Signature-Ed25519": signature, "X-Signature-Timestamp": timestamp,
    }
    return body, headers


def c2c(content="登录", event_id="evt-1", msg_id="msg-1"):
    return {"op": 0, "id": event_id, "t": "C2C_MESSAGE_CREATE",
            "d": {"id": msg_id, "content": content, "author": {"user_openid": OPENID}}}


def post(client, payload, **kwargs):
    body, headers = signed(payload, **kwargs)
    return client.post(qqbot.WEBHOOK_PATH, content=body, headers=headers)


def group_at(content, msg_id, *, member="qq-member", group="qq-group", event="GROUP_AT_MESSAGE_CREATE"):
    return {"op": 0, "id": msg_id, "t": event, "d": {
        "id": msg_id, "group_openid": group, "content": content, "author": {"member_openid": member},
    }}


def test_bind_web_account_in_private_and_request_group_report(bot, monkeypatch):
    client, fake = bot
    monkeypatch.setenv("QQBOT_APP_ID", CONFIG.app_id)
    origin = {"Origin": ORIGIN}
    rendered = []

    def render(card):
        rendered.append(card)
        return b"test-png"

    monkeypatch.setattr(qqbot.daily_card, "render", render)
    played_at = (datetime.now(CHINA) - timedelta(days=1)).replace(hour=12)
    with TestClient(api.app) as web:
        with storage.connect() as db:
            user = accounts.create_with_password(db, "existing", "web-user-password")
            other = accounts.create_with_password(db, "other", "other-user-password")
            match = {"external_id": "visible", "played_at": played_at.isoformat(),
                     "play": "独立模拟", "difficulty": "规程等级 8", "result": "win"}
            db.execute(worker.UPSERT_MATCH, worker.write_parameters(db, user["id"], match))
            db.execute(worker.UPSERT_MATCH, worker.write_parameters(
                db, user["id"], {**match, "external_id": "exit", "suspected_exit": True},
            ))
            db.execute(worker.UPSERT_MATCH, worker.write_parameters(db, other["id"], match))
        assert web.post("/api/profile/qq-binding", headers=origin).status_code == 401
        assert web.post("/api/session", headers=origin, json={
            "username": "existing", "password": "web-user-password",
        }).status_code == 200
        assert web.post("/api/profile/qq-binding").status_code == 403
        code_response = web.post("/api/profile/qq-binding", headers=origin)
        assert code_response.status_code == 201
        command = code_response.json()["command"]
        assert post(client, group_at(command, "public-bind")).status_code == 200
        assert "私聊" in fake.group_replies[-1][2]
        assert web.get("/api/profile").json()["qq"]["bound"] is False
        assert post(client, c2c(command, "private-bind", "private-bind")).status_code == 200
        assert "已绑定" in fake.replies[-1]["content"]
        assert web.get("/api/profile").json()["qq"]["bound"] is True
        session = web.get("/api/session").json()
        assert not session["username_editable"] and not session["needs_password"]
        assert post(client, c2c(command, "replay-bind", "replay-bind")).status_code == 200
        assert "无效" in fake.replies[-1]["content"]
        assert post(client, c2c(event_id="private-login", msg_id="private-login")).status_code == 200
        token = fake.replies[-1]["content"].split("#qq-login=")[1]
        web.cookies.clear()
        assert web.post("/api/session/qq-link", headers=origin, json={"token": token}).json()["username"] == "existing"

    replies = len(fake.group_replies)
    assert post(client, group_at("/日报", "not-at", event="GROUP_MESSAGE_CREATE")).status_code == 200
    assert len(fake.group_replies) == replies and fake.images == []
    assert post(client, group_at("<@bot> /日报", "first-report")).status_code == 200
    request = fake.group_replies[-1][2].rsplit("「", 1)[1].split("」")[0]
    assert post(client, c2c(request, "private-proof", "private-proof")).status_code == 200
    proof = fake.replies[-1]["content"].split("「")[1].split("」")[0]
    assert post(client, group_at(proof, "wrong-member", member="other-qq-member")).status_code == 200
    assert post(client, group_at(proof, "wrong-group", group="other-qq-group")).status_code == 200
    assert fake.images == []
    assert post(client, group_at(proof, "correct-member")).status_code == 200
    assert post(client, group_at("日报", "repeat-report")).status_code == 200
    assert fake.images == [
        ("group", "qq-group", "correct-member", b"test-png"),
        ("group", "qq-group", "repeat-report", b"test-png"),
    ]
    assert all(card.day == played_at.date() and card.wins == 1 and card.excluded == 1 for card in rendered)
    assert all(card.username != "existing" for card in rendered)


def test_qq_signup_binds_openid_for_group_reports(bot, monkeypatch):
    client, fake = bot
    monkeypatch.setenv("QQBOT_APP_ID", CONFIG.app_id)
    assert post(client, group_at("日报", "before-signup", member=OPENID)).status_code == 200
    assert "私聊" in fake.group_replies[-1][2] and "登录" in fake.group_replies[-1][2]
    with storage.connect() as db:
        assert accounts.find_qq_account(db, CONFIG.app_id, OPENID) is None

    assert post(client, c2c(event_id="signup", msg_id="signup")).status_code == 200
    token = fake.replies[-1]["content"].split("#qq-login=")[1]
    with TestClient(api.app) as web:
        response = web.post("/api/session/qq-link", headers={"Origin": ORIGIN}, json={"token": token})
        assert response.json()["username"].startswith("qq-")
        assert web.get("/api/profile").json()["qq"]["bound"] is True

    assert post(client, group_at("/日报", "after-signup", member=OPENID)).status_code == 200
    assert "暂无有效作战记录" in fake.group_replies[-1][2]


def test_seed_is_secret_repeated_to_32_bytes():
    seed = (SECRET * 3)[:32].encode()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    expected = Ed25519PrivateKey.from_private_bytes(seed).sign(b"x")
    assert qqbot.sign(CONFIG, b"x") == expected.hex()


def test_group_image_push_uploads_without_sending_then_sends_media(monkeypatch):
    client = qqbot.QQClient(CONFIG)
    calls = []

    def post(path, payload):
        calls.append((path, payload))
        return {"file_info": "uploaded-image"}

    monkeypatch.setattr(client, "_post", post)
    url = "https://i0.hdslb.com/cover.jpg"
    client.send_group_image("group", url, "动态摘要")
    assert calls == [
        ("/v2/groups/group/files", {"file_type": 1, "srv_send_msg": False, "url": url}),
        ("/v2/groups/group/messages", {
            "msg_type": 7, "content": "动态摘要", "media": {"file_info": "uploaded-image"},
        }),
    ]


def test_callback_validation_returns_signature(bot):
    client, _ = bot
    response = client.post(qqbot.WEBHOOK_PATH, json={"op": 13, "d": {"plain_token": "abc", "event_ts": "1700000000"}},
                           headers={"X-Bot-Appid": CONFIG.app_id})
    assert response.status_code == 200
    body = response.json()
    assert body["plain_token"] == "abc"
    CONFIG.signing_key.public_key().verify(bytes.fromhex(body["signature"]), b"1700000000abc")


def test_login_command_creates_account_and_link_works(bot):
    client, fake = bot
    response = post(client, c2c())
    assert response.status_code == 200 and response.json() == {"op": 12, "d": 0}
    assert len(fake.replies) == 1
    reply = fake.replies[0]
    assert reply["openid"] == OPENID and reply["msg_id"] == "msg-1"
    link = reply["content"].split("\n")[-1]
    assert link.startswith(ORIGIN + "/#qq-login=")
    token = link.split("#qq-login=", 1)[1]
    with TestClient(api.app) as web:
        login = web.post("/api/session/qq-link", json={"token": token}, headers={"Origin": ORIGIN})
        assert login.status_code == 200
        assert login.json()["needs_password"] is True
        assert login.json()["username"] in reply["content"]


def test_same_openid_gets_same_account(bot):
    client, fake = bot
    post(client, c2c(event_id="evt-1", msg_id="m1"))
    post(client, c2c(event_id="evt-2", msg_id="m2"))
    first, second = (reply["content"].split("\n")[0] for reply in fake.replies)
    assert first == second


def test_duplicate_events_are_processed_once(bot):
    client, fake = bot
    assert post(client, c2c()).status_code == 200
    assert post(client, c2c()).status_code == 200
    assert len(fake.replies) == 1


def test_other_messages_get_help(bot):
    client, fake = bot
    post(client, c2c(content="你好"))
    assert fake.replies[0]["content"] == qqbot.HELP_TEXT


def test_link_quota_per_openid(bot):
    client, fake = bot
    for index in range(6):
        post(client, c2c(event_id=f"evt-{index}", msg_id=f"m{index}"))
    assert "太频繁" in fake.replies[-1]["content"]
    assert sum("#qq-login=" in reply["content"] for reply in fake.replies) == 5


def test_bad_signature_is_rejected(bot):
    client, fake = bot
    body, headers = signed(c2c())
    headers["X-Signature-Ed25519"] = "00" * 64
    assert client.post(qqbot.WEBHOOK_PATH, content=body, headers=headers).status_code == 401
    other = qqbot.BotConfig(CONFIG.app_id, "another-secret")
    assert post(client, c2c(), config=other).status_code == 401
    assert fake.replies == []


def test_tampered_body_is_rejected(bot):
    client, fake = bot
    _, headers = signed(c2c())
    tampered = json.dumps(c2c(content="登录", msg_id="other")).encode()
    assert client.post(qqbot.WEBHOOK_PATH, content=tampered, headers=headers).status_code == 401
    assert fake.replies == []


def test_stale_timestamp_is_rejected(bot):
    client, fake = bot
    assert post(client, c2c(), timestamp=int(time.time()) - 3600).status_code == 401
    assert fake.replies == []


def test_wrong_app_id_is_rejected(bot):
    client, _ = bot
    body, headers = signed(c2c())
    headers["X-Bot-Appid"] = "999"
    assert client.post(qqbot.WEBHOOK_PATH, content=body, headers=headers).status_code == 403


def test_oversized_body_is_rejected(bot):
    client, _ = bot
    response = client.post(qqbot.WEBHOOK_PATH, content=b"x" * (qqbot.MAX_BODY + 1),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_missing_credentials_fail_at_startup(monkeypatch):
    monkeypatch.delenv("QQBOT_APP_ID", raising=False)
    monkeypatch.delenv("QQBOT_APP_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        qqbot.BotConfig.from_env()
