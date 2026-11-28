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
        self.c2c_error = None

    def reply_c2c(self, openid, msg_id, content, seq=1):
        if self.c2c_error:
            raise self.c2c_error
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
    qqbot.record_quota._failures.clear()
    qqbot.group_link_quota._failures.clear()
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


def group_at(content, msg_id, *, member="qq-member", group="qq-group", event="GROUP_AT_MESSAGE_CREATE",
             nickname="博士"):
    return {"op": 0, "id": msg_id, "t": event, "d": {
        "id": msg_id, "group_openid": group, "content": content,
        "author": {"member_openid": member, "member_nickname": nickname},
    }}


def group_link_token(reply):
    return reply["content"].split("#qq-group=", 1)[1].strip()


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

    replies, group_replies = len(fake.replies), len(fake.group_replies)
    assert post(client, group_at("/日报", "not-at", event="GROUP_MESSAGE_CREATE")).status_code == 200
    assert len(fake.group_replies) == group_replies and fake.images == []

    # 未关联的群成员：私聊回复这条群消息的发送者一个关联链接，群里不说话。
    assert post(client, group_at("<@bot> /日报", "first-report")).status_code == 200
    assert len(fake.group_replies) == group_replies and len(fake.replies) == replies + 1
    link_reply = fake.replies[-1]
    assert link_reply["openid"] == "qq-member" and link_reply["msg_id"] == "first-report"
    token = group_link_token(link_reply)
    assert post(client, group_at("日报", "other-member", member="other-qq-member")).status_code == 200
    other_token = group_link_token(fake.replies[-1])
    assert fake.images == []

    with TestClient(api.app) as web:
        preview = web.post("/api/qq-group-link/preview", headers=origin, json={"token": token})
        assert preview.status_code == 401
        assert web.post("/api/session", headers=origin, json={
            "username": "existing", "password": "web-user-password",
        }).status_code == 200
        assert web.post("/api/qq-group-link/confirm", json={"token": token}).status_code == 403
        preview = web.post("/api/qq-group-link/preview", headers=origin, json={"token": token})
        assert preview.json() == {"nickname": "博士", "group_number": None}
        bad = web.post("/api/qq-group-link/confirm", headers=origin, json={"token": "x" * 200})
        assert bad.status_code == 422 and "x" * 20 not in bad.text
        assert web.post("/api/qq-group-link/confirm", headers=origin, json={"token": token}).status_code == 204
        replay = web.post("/api/qq-group-link/confirm", headers=origin, json={"token": token})
        assert replay.status_code == 404 and "无效" in replay.json()["detail"]

    assert post(client, group_at("日报", "repeat-report")).status_code == 200
    assert post(client, group_at("日报", "other-group", group="other-qq-group")).status_code == 200
    assert "#qq-group=" in fake.replies[-1]["content"]
    assert fake.images == [("group", "qq-group", "repeat-report", b"test-png")]

    # 「战绩」：最近 10 局有效对局，疑似直接退出不计入。
    assert post(client, group_at("<@bot> 战绩", "record")).status_code == 200
    group, msg_id, record = fake.group_replies[-1]
    assert (group, msg_id) == ("qq-group", "record")
    assert "最近 1 局战绩" in record and "胜率 100%（1 胜 0 负）" in record and "走势 胜" in record
    for index in range(3):
        post(client, group_at("战绩", f"record-quota-{index}"))
    assert "太频繁" in fake.group_replies[-1][2]
    links = len(fake.replies)
    assert post(client, group_at("战绩", "record-unlinked", member="third-qq-member")).status_code == 200
    assert len(fake.replies) == links + 1 and "#qq-group=" in fake.replies[-1]["content"]
    assert all(card.day == played_at.date() and card.wins == 1 and card.excluded == 1 for card in rendered)
    assert all(card.username != "existing" for card in rendered)
    with storage.connect() as db:
        # 别的成员的链接没被确认，仍未关联。
        assert qqbot.qq_binding.group_account(db, CONFIG.app_id, "qq-group", "other-qq-member") is None
        assert qqbot.qq_binding.group_link_info(db, CONFIG.app_id, other_token) is not None

    assert post(client, group_at("解绑", "unbind")).status_code == 200
    assert "已解除" in fake.group_replies[-1][2]
    assert post(client, group_at("解绑", "unbind-again")).status_code == 200
    assert "没有关联" in fake.group_replies[-1][2]
    assert post(client, group_at("日报", "after-unbind")).status_code == 200
    assert "#qq-group=" in fake.replies[-1]["content"] and len(fake.images) == 1


def test_group_link_confirmed_by_qq_signup_account(bot, monkeypatch):
    client, fake = bot
    monkeypatch.setenv("QQBOT_APP_ID", CONFIG.app_id)
    origin = {"Origin": ORIGIN}
    assert post(client, c2c(event_id="signup", msg_id="signup")).status_code == 200
    login_token = fake.replies[-1]["content"].split("#qq-login=")[1]
    # 私聊注册不会自动关联群身份：文档没说群成员 openid 与私聊 openid 相同。
    assert post(client, group_at("/日报", "before-link", member=OPENID)).status_code == 200
    assert fake.group_replies == []
    token = group_link_token(fake.replies[-1])
    with storage.connect() as db:
        db.execute("INSERT INTO qq_feed_groups (bot_app_id, group_openid, group_number, updated_at) "
                   "VALUES (%s, %s, %s, now()) ON CONFLICT (bot_app_id, group_openid) DO UPDATE SET "
                   "group_number = excluded.group_number", (CONFIG.app_id, "qq-group", "123456"))
    with TestClient(api.app) as web:
        assert web.post("/api/session/qq-link", headers=origin, json={"token": login_token}).status_code == 200
        preview = web.post("/api/qq-group-link/preview", headers=origin, json={"token": token}).json()
        assert preview == {"nickname": "博士", "group_number": "123456"}
        assert web.post("/api/qq-group-link/confirm", headers=origin, json={"token": token}).status_code == 204

    assert post(client, group_at("/日报", "after-link", member=OPENID)).status_code == 200
    assert "暂无有效作战记录" in fake.group_replies[-1][2]


def test_group_link_needs_friendship(bot):
    client, fake = bot
    fake.c2c_error = qqbot.QQApiError(400, qqbot.NOT_FRIEND)
    assert post(client, group_at("日报", "not-friend")).status_code == 200
    assert "好友" in fake.group_replies[-1][2]
    fake.c2c_error = qqbot.QQApiError(500, 11255)
    assert post(client, group_at("日报", "other-error")).status_code == 200
    assert len(fake.group_replies) == 1


def test_group_link_quota_per_member(bot):
    client, fake = bot
    qqbot.group_link_quota._failures.clear()
    for index in range(6):
        post(client, group_at("日报", f"quota-{index}"))
    assert sum("#qq-group=" in reply["content"] for reply in fake.replies) == 5
    assert fake.group_replies == []


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
    client.send_group_image("group", url, "caption")
    assert calls == [
        ("/v2/groups/group/files", {"file_type": 1, "srv_send_msg": False, "url": url}),
        ("/v2/groups/group/messages", {
            "msg_type": 7, "content": "caption", "media": {"file_info": "uploaded-image"},
        }),
    ]


def test_send_group_markdown_posts_a_single_message(monkeypatch):
    client = qqbot.QQClient(CONFIG)
    calls = []
    monkeypatch.setattr(client, "_post", lambda path, payload: calls.append((path, payload)))
    content = "正文\n\n![配图 #600px #300px](https://i0.hdslb.com/cover.jpg)"
    client.send_group_markdown("group", content)
    assert calls == [("/v2/groups/group/messages", {"msg_type": 2, "markdown": {"content": content}})]


def test_callback_validation_returns_signature(bot):
    client, _ = bot
    response = client.post(qqbot.WEBHOOK_PATH, json={"op": 13, "d": {"plain_token": "abc", "event_ts": "1700000000"}},
                           headers={"X-Bot-Appid": CONFIG.app_id})
    assert response.status_code == 200
    body = response.json()
    assert body["plain_token"] == "abc"
    CONFIG.signing_key.public_key().verify(bytes.fromhex(body["signature"]), b"1700000000abc")


def test_callback_validation_cannot_sign_a_forged_event(bot):
    client, fake = bot
    timestamp = str(int(time.time()))
    forged = json.dumps(c2c()).encode()
    response = client.post(qqbot.WEBHOOK_PATH, json={"op": 13, "d": {"plain_token": forged.decode(), "event_ts": timestamp}},
                           headers={"X-Bot-Appid": CONFIG.app_id})
    assert response.status_code == 400
    for d in ({"plain_token": "abc", "event_ts": "17x"}, {"plain_token": "a b", "event_ts": "1700000000"}):
        response = client.post(qqbot.WEBHOOK_PATH, json={"op": 13, "d": d}, headers={"X-Bot-Appid": CONFIG.app_id})
        assert response.status_code == 400
    assert fake.replies == []


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


def test_api_errors_carry_platform_code(monkeypatch):
    import io
    from urllib.error import HTTPError

    def fail(request, timeout):
        raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"code": 40054004, "message": "x"}'))

    client = qqbot.QQClient(CONFIG)
    monkeypatch.setattr(client, "access_token", lambda: "token")
    monkeypatch.setattr(qqbot, "urlopen", fail)
    with pytest.raises(qqbot.QQApiError) as raised:
        client.reply_c2c("member", "msg", "hi")
    assert raised.value.code == 400 and raised.value.err_code == qqbot.NOT_FRIEND


def test_group_link_failures_are_logged_with_platform_code(bot, caplog):
    client, fake = bot
    caplog.set_level("INFO", logger="logbook.qqbot")
    fake.c2c_error = qqbot.QQApiError(400, 11255, "invalid request")
    assert post(client, group_at("日报", "logged-failure")).status_code == 200
    text = caplog.text
    assert "Group @ event: 日报" in text and "unlinked, sending link" in text
    assert "QQApiError 400 11255 invalid request" in text
    assert "qq-member" not in text and "qq-group" not in text
