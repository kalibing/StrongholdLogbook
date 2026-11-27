"""QQ 官方机器人 Webhook 接入：单聊里发「登录」，机器人回一个一次性免密登录链接；
群里 @机器人 或单聊发「订阅公告」「订阅动态」等指令管理推送订阅（推送由 logbook.feeds 进程发送）。

独立进程运行（uvicorn logbook.qqbot:app），与网页 API 分开：
- 网页 API 的写请求要校验 Origin，回调请求没有 Origin；分开后两边的防护各自保持严格。
- 这个进程只用到建号、签发登录链接与站内通知，不读战绩、会话和森空岛 / 成就令牌。

协议要点（QQ 机器人 API v2 文档）：
- 回调地址校验 op=13：对 event_ts + plain_token 做 Ed25519 签名，回 {"plain_token", "signature"}。
- 业务事件 op=0：用请求头 X-Signature-Ed25519 / X-Signature-Timestamp 验签，内容为 timestamp + 原始请求体。
  私钥种子 = Bot Secret 重复拼接后取前 32 字节。验签通过后回 op=12 确认。
- 单聊事件 C2C_MESSAGE_CREATE：用户为 d.author.user_openid，被动回复用 d.id 作 msg_id（60 分钟内有效）。
- 群 @ 事件 GROUP_AT_MESSAGE_CREATE：群为 d.group_openid，回复 POST /v2/groups/{group_openid}/messages。
- 不带 msg_id 的同一接口即主动消息，受每日条数限制，用户 / 群可在客户端关闭接收。
- 发消息 POST https://api.bot.qq.com/v2/users/{openid}/messages，Authorization: QQBot {access_token}；
  access_token 由 POST https://api.bot.qq.com/app/getAppAccessToken 用 appId + clientSecret 换取，约 7200 秒有效。
- 文档没给 op=12 回包示例，这里回 {"op": 12, "d": 0}；接入真实机器人时以平台实际行为为准。

日志不记录消息原文、openid、登录令牌和任何凭据。
"""

import base64
from collections import OrderedDict
from dataclasses import dataclass
import json
import logging
import os
from threading import Lock
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import accounts, bilibili, feeds
from .credentials import CredentialStorageError
from .config import settings
from .errors import StorageUnavailable
from .limits import FailureThrottle, RequestSizeLimit
from .storage import connect

LOGGER = logging.getLogger(__name__)

# 按 API v2 文档：换 token 与 OpenAPI 统一地址都在 api.bot.qq.com；平台变更时可用环境变量覆盖。
TOKEN_URL = os.getenv("QQBOT_TOKEN_URL", "https://api.bot.qq.com/app/getAppAccessToken")
API_BASE = os.getenv("QQBOT_API_BASE", "https://api.bot.qq.com").rstrip("/")
WEBHOOK_PATH = "/qqbot/webhook"
MAX_BODY = 64 * 1024
# 回调时间戳与本机时间相差太多时拒绝，挡住旧请求重放；平台重投同一事件由事件 ID 去重。
MAX_CLOCK_SKEW = 10 * 60
LOGIN_COMMANDS = {"登录", "登陆", "注册", "login", "/登录", "/login"}
HELP_TEXT = (
    "发送「登录」获取作战档案的一次性登录链接（10 分钟内有效，只能用一次）。\n"
    "第一次使用会自动为你创建账号，登录后可以设置密码、修改一次账号名。\n\n"
    + feeds.USAGE
)
GROUP_HELP_TEXT = "@我 并发送以下指令：\n" + feeds.USAGE


@dataclass(frozen=True)
class BotConfig:
    app_id: str
    secret: str

    @classmethod
    def from_env(cls) -> "BotConfig":
        app_id = os.getenv("QQBOT_APP_ID", "").strip()
        secret = os.getenv("QQBOT_APP_SECRET", "").strip()
        if not app_id or not secret:
            raise RuntimeError("QQBOT_APP_ID and QQBOT_APP_SECRET must be set")
        if not accounts.OPENID_PATTERN.fullmatch(app_id):
            raise RuntimeError("QQBOT_APP_ID has an unexpected format")
        return cls(app_id, secret)

    @property
    def signing_key(self) -> Ed25519PrivateKey:
        seed = self.secret
        while len(seed) < 32:
            seed += seed
        return Ed25519PrivateKey.from_private_bytes(seed[:32].encode())


def sign(config: BotConfig, message: bytes) -> str:
    return config.signing_key.sign(message).hex()


def verify(config: BotConfig, signature_hex: str, timestamp: str, body: bytes) -> bool:
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    if len(signature) != 64 or not timestamp.isdigit():
        return False
    try:
        config.signing_key.public_key().verify(signature, timestamp.encode() + body)
    except InvalidSignature:
        return False
    return True


class SeenEvents:
    """进程内去重：平台超时重投同一事件时只处理一次。"""

    def __init__(self, limit: int = 4096):
        self.limit = limit
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._lock = Lock()

    def first_time(self, key: str) -> bool:
        with self._lock:
            if key in self._seen:
                return False
            self._seen[key] = None
            while len(self._seen) > self.limit:
                self._seen.popitem(last=False)
            return True


class QQClient:
    """取 access_token（缓存到过期前 60 秒），发送单聊 / 群的被动回复与主动消息。"""

    def __init__(self, config: BotConfig):
        self.config = config
        self._token = ""
        self._expires = 0.0
        self._lock = Lock()

    def access_token(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._expires:
                return self._token
            payload = json.dumps({"appId": self.config.app_id, "clientSecret": self.config.secret}).encode()
            request = UrlRequest(TOKEN_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=10) as response:
                data = json.loads(response.read())
            token = data.get("access_token")
            if not isinstance(token, str) or not token:
                raise RuntimeError("QQ access token response has no access_token")
            self._token = token
            self._expires = time.monotonic() + max(60, int(data.get("expires_in", 7200)) - 60)
            return token

    def _post(self, path: str, payload: dict) -> dict:
        request = UrlRequest(
            f"{API_BASE}{path}", data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"QQBot {self.access_token()}"},
        )
        with urlopen(request, timeout=20) as response:
            body = response.read()
        try:
            data = json.loads(body) if body else {}
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def reply_image(self, target_type: str, openid: str, msg_id: str, png: bytes, content: str = "",
                    seq: int = 1) -> None:
        """富媒体消息：先上传图片（file_type 1，base64）拿 file_info，再发 msg_type 7 的被动回复。"""
        base = f"/v2/groups/{quote(openid, safe='')}" if target_type == "group" else f"/v2/users/{quote(openid, safe='')}"
        uploaded = self._post(f"{base}/files", {
            "file_type": 1, "file_data": base64.b64encode(png).decode("ascii"), "srv_send_msg": False,
        })
        file_info = uploaded.get("file_info")
        if not isinstance(file_info, str) or not file_info:
            raise RuntimeError("QQ media upload returned no file_info")
        self._post(f"{base}/messages", {
            "msg_type": 7, "content": content or " ", "media": {"file_info": file_info},
            "msg_id": msg_id, "msg_seq": seq,
        })

    def reply(self, target_type: str, openid: str, msg_id: str, content: str, seq: int = 1) -> None:
        if target_type == "group":
            self.reply_group(openid, msg_id, content, seq)
        else:
            self.reply_c2c(openid, msg_id, content, seq)

    def reply_c2c(self, openid: str, msg_id: str, content: str, seq: int = 1) -> None:
        self._post(f"/v2/users/{quote(openid, safe='')}/messages",
                   {"msg_type": 0, "content": content, "msg_id": msg_id, "msg_seq": seq})

    def reply_group(self, group_openid: str, msg_id: str, content: str, seq: int = 1) -> None:
        self._post(f"/v2/groups/{quote(group_openid, safe='')}/messages",
                   {"msg_type": 0, "content": content, "msg_id": msg_id, "msg_seq": seq})

    def send_c2c(self, openid: str, content: str) -> None:
        """主动消息：不带 msg_id。"""
        self._post(f"/v2/users/{quote(openid, safe='')}/messages", {"msg_type": 0, "content": content})

    def send_group(self, group_openid: str, content: str) -> None:
        """主动消息：不带 msg_id。"""
        self._post(f"/v2/groups/{quote(group_openid, safe='')}/messages", {"msg_type": 0, "content": content})


def login_reply(link: str, username: str) -> str:
    return (
        f"你的作战档案账号：{username}\n"
        f"一次性登录链接（10 分钟内有效，只能用一次，请勿转发）：\n{link}"
    )


# 每个 openid 每小时最多签发 5 个登录链接，防止刷消息。
link_quota = FailureThrottle(limit=5, window=60 * 60)


def handle_c2c(client: QQClient, config: BotConfig, data: dict) -> None:
    author = data.get("author") or {}
    openid = author.get("user_openid") or author.get("id")
    msg_id = data.get("id")
    content = (data.get("content") or "").strip()
    if not isinstance(openid, str) or not isinstance(msg_id, str):
        LOGGER.warning("C2C event without user_openid or id; ignored")
        return
    try:
        if is_bili_command(content):
            handle_bili(client, "c2c", openid, msg_id)
            return
        if feeds.is_command(content):
            client.reply_c2c(openid, msg_id, subscription_reply(config, "c2c", openid, content))
            return
        if content.lower() not in LOGIN_COMMANDS:
            client.reply_c2c(openid, msg_id, HELP_TEXT)
            return
        if not link_quota.take(openid):
            client.reply_c2c(openid, msg_id, "登录链接获取太频繁，请一小时后再试。")
            return
        try:
            with connect() as database:
                user = accounts.create_for_qq_openid(database, config.app_id, openid)
                token = accounts.issue_login_link(database, user["id"])
        except (StorageUnavailable, accounts.AccountError):
            LOGGER.exception("Could not issue a login link")
            link_quota.refund(openid)
            client.reply_c2c(openid, msg_id, "暂时无法生成登录链接，请稍后再试。")
            return
        link = f"{settings.public_origin}/#qq-login={token}"
        client.reply_c2c(openid, msg_id, login_reply(link, user["username"]))
    except (HTTPError, URLError, RuntimeError, ValueError) as error:
        # 只记录类型和状态码，不记录消息内容和令牌。
        LOGGER.warning("QQ reply failed: %s %s", type(error).__name__, getattr(error, "code", ""))


def subscription_reply(config: BotConfig, target_type: str, openid: str, content: str) -> str:
    if not accounts.OPENID_PATTERN.fullmatch(openid):
        return "暂时无法处理订阅，请稍后再试。"
    try:
        with connect() as database:
            return feeds.handle_command(database, config.app_id, target_type, openid, content) or ""
    except StorageUnavailable:
        LOGGER.exception("Could not update feed subscription")
        return "暂时无法处理订阅，请稍后再试。"


BILI_COMMANDS = {"b站", "b站状态", "b站登录", "登录b站", "bilibili", "哔哩哔哩"}
# 同一时间只挂一张扫码二维码，避免多人同时触发互相覆盖登录态。
bili_login_lock = Lock()


def is_bili_command(content: str) -> bool:
    return feeds.normalize_command(content).lower() in BILI_COMMANDS


def handle_bili(client: QQClient, target_type: str, openid: str, msg_id: str,
                get=bilibili.http_get, sleep=time.sleep) -> None:
    """查询动态推送用的 B 站登录状态；未登录或已失效时发扫码二维码，扫码成功后加密保存 Cookie。

    只有当前没有可用登录态时才发二维码，已登录时任何人都无法通过这个指令替换账号。
    """
    def say(text: str, seq: int = 1) -> None:
        client.reply(target_type, openid, msg_id, text, seq)

    try:
        with connect() as database:
            cookie = bilibili.stored_cookie(database)
    except (StorageUnavailable, CredentialStorageError):
        LOGGER.exception("Could not read Bilibili cookie")
        say("暂时无法读取 B 站登录状态，请稍后再试。")
        return
    try:
        logged_in, uname = bilibili.login_status(cookie, get)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        LOGGER.warning("Bilibili status check failed: %s", type(error).__name__)
        say("暂时连不上 B 站，请稍后再试。")
        return
    if logged_in:
        say(f"B 站已登录：{uname or '（未取到用户名）'}\n动态推送使用这个账号。")
        return
    if not bili_login_lock.acquire(blocking=False):
        say("已经有一张 B 站登录二维码在等待扫码，请扫那张，或 3 分钟后再试。")
        return
    try:
        try:
            url, key = bilibili.generate_qr(get)
            png = bilibili.qr_png(url)
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as error:
            LOGGER.warning("Bilibili QR generate failed: %s", type(error).__name__)
            say("B 站未登录，二维码生成失败，请稍后再试。")
            return
        state = "B 站登录已失效" if cookie else "B 站未登录"
        try:
            client.reply_image(target_type, openid, msg_id, png,
                               f"{state}，请用 B 站 App 扫码并确认登录（3 分钟内有效）。", seq=1)
        except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as error:
            LOGGER.warning("QQ image reply failed: %s %s", type(error).__name__, getattr(error, "code", ""))
            say(f"{state}，但二维码图片发送失败（机器人可能没有发图权限）。")
            return
        try:
            new_cookie = bilibili.wait_for_scan(key, get, sleep)
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as error:
            LOGGER.warning("Bilibili QR poll failed: %s", type(error).__name__)
            say("扫码登录失败，请重新 @我 发「B站登录」。", 2)
            return
        if not new_cookie:
            say("二维码已过期，需要时请重新 @我 发「B站登录」。", 2)
            return
        try:
            _, uname = bilibili.login_status(new_cookie, get)
        except (HTTPError, URLError, TimeoutError, ValueError):
            uname = ""
        try:
            with connect() as database:
                bilibili.save_cookie(database, new_cookie, uname)
        except (StorageUnavailable, CredentialStorageError):
            LOGGER.exception("Could not save Bilibili cookie")
            say("登录成功，但保存失败，请稍后重试。", 2)
            return
        say(f"B 站登录成功：{uname or '（未取到用户名）'}。动态推送会使用这个账号。", 2)
    finally:
        bili_login_lock.release()


def handle_group_at(client: QQClient, config: BotConfig, data: dict) -> None:
    group_openid = data.get("group_openid")
    msg_id = data.get("id")
    content = (data.get("content") or "").strip()
    if not isinstance(group_openid, str) or not isinstance(msg_id, str):
        LOGGER.warning("Group event without group_openid or id; ignored")
        return
    try:
        if is_bili_command(content):
            handle_bili(client, "group", group_openid, msg_id)
        elif feeds.is_command(content):
            client.reply_group(group_openid, msg_id, subscription_reply(config, "group", group_openid, content))
        else:
            client.reply_group(group_openid, msg_id, GROUP_HELP_TEXT)
    except (HTTPError, URLError, RuntimeError, ValueError) as error:
        LOGGER.warning("QQ group reply failed: %s %s", type(error).__name__, getattr(error, "code", ""))


def create_app(config: BotConfig | None = None, client: QQClient | None = None) -> FastAPI:
    config = config or BotConfig.from_env()
    client = client or QQClient(config)
    seen = SeenEvents()
    application = FastAPI(title="QQ bot webhook", docs_url=None, redoc_url=None, openapi_url=None)
    application.add_middleware(RequestSizeLimit, limit=MAX_BODY)
    application.state.config = config
    application.state.client = client

    @application.get("/qqbot/health")
    def health():
        return {"status": "ok"}

    @application.post(WEBHOOK_PATH)
    async def webhook(request: Request, background: BackgroundTasks):
        if request.headers.get("x-bot-appid", config.app_id) != config.app_id:
            raise HTTPException(403, "unknown app")
        body = await request.body()
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(400, "invalid json") from None
        if not isinstance(payload, dict):
            raise HTTPException(400, "invalid payload")
        op = payload.get("op")
        data = payload.get("d") if isinstance(payload.get("d"), dict) else {}

        if op == 13:
            # 回调地址校验：用 Bot Secret 派生的私钥签 event_ts + plain_token。
            plain_token, event_ts = data.get("plain_token"), data.get("event_ts")
            if not isinstance(plain_token, str) or not isinstance(event_ts, str):
                raise HTTPException(400, "invalid validation payload")
            return {"plain_token": plain_token, "signature": sign(config, (event_ts + plain_token).encode())}

        timestamp = request.headers.get("x-signature-timestamp", "")
        if not verify(config, request.headers.get("x-signature-ed25519", ""), timestamp, body):
            raise HTTPException(401, "bad signature")
        if abs(time.time() - int(timestamp)) > MAX_CLOCK_SKEW:
            raise HTTPException(401, "stale request")

        handlers = {"C2C_MESSAGE_CREATE": handle_c2c, "GROUP_AT_MESSAGE_CREATE": handle_group_at}
        if op == 0 and payload.get("t") in handlers:
            event_id = str(payload.get("id") or data.get("id") or "")
            if event_id and seen.first_time(event_id):
                background.add_task(handlers[payload["t"]], client, config, data)
        return JSONResponse({"op": 12, "d": 0})

    return application


def _lazy_app():
    logging.basicConfig(level=logging.INFO)
    return create_app()


class _LazyApp:
    """uvicorn logbook.qqbot:app 启动时才读取环境变量；导入本模块（如测试）不需要机器人凭据。"""

    def __init__(self):
        self._app = None

    async def __call__(self, scope, receive, send):
        if self._app is None:
            self._app = _lazy_app()
        await self._app(scope, receive, send)


app = _LazyApp()
