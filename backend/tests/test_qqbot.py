"""QQ 机器人回调：地址校验、验签、去重、发「登录」拿到可用的一次性链接。"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from logbook import api, qqbot

ORIGIN = "http://localhost:8080"
SECRET = "test-bot-secret"
CONFIG = qqbot.BotConfig("102000001", SECRET)
OPENID = "E4F1A2B3C4D5E6F7A8B9C0D1E2F3A4B5"


class FakeClient:
    def __init__(self):
        self.replies = []

    def reply_c2c(self, openid, msg_id, content, seq=1):
        self.replies.append({"openid": openid, "msg_id": msg_id, "content": content})


@pytest.fixture()
def bot(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    qqbot.link_quota._failures.clear()
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


def test_seed_is_secret_repeated_to_32_bytes():
    seed = (SECRET * 3)[:32].encode()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    expected = Ed25519PrivateKey.from_private_bytes(seed).sign(b"x")
    assert qqbot.sign(CONFIG, b"x") == expected.hex()


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
