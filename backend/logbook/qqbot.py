"""QQ 官方机器人 Webhook 接入：单聊里发「登录」，机器人回一个一次性免密登录链接。

独立进程运行（uvicorn logbook.qqbot:app），与网页 API 分开：
- 网页 API 的写请求要校验 Origin，回调请求没有 Origin；分开后两边的防护各自保持严格。
- 这个进程只用到建号、签发登录链接与站内通知，不读战绩、会话和森空岛 / 成就令牌。

协议要点（QQ 机器人 API v2 文档）：
- 回调地址校验 op=13：对 event_ts + plain_token 做 Ed25519 签名，回 {"plain_token", "signature"}。
- 业务事件 op=0：用请求头 X-Signature-Ed25519 / X-Signature-Timestamp 验签，内容为 timestamp + 原始请求体。
  私钥种子 = Bot Secret 重复拼接后取前 32 字节。验签通过后回 op=12 确认。
- 单聊事件 C2C_MESSAGE_CREATE：用户为 d.author.user_openid，被动回复用 d.id 作 msg_id（60 分钟内有效）。
- 发消息 POST https://api.bot.qq.com/v2/users/{openid}/messages，Authorization: QQBot {access_token}；
  access_token 由 POST https://api.bot.qq.com/app/getAppAccessToken 用 appId + clientSecret 换取，约 7200 秒有效。
- 文档没给 op=12 回包示例，这里回 {"op": 12, "d": 0}；接入真实机器人时以平台实际行为为准。

日志不记录消息原文、openid、登录令牌和任何凭据。
"""

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

from . import accounts
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
    "第一次使用会自动为你创建账号，登录后可以设置密码、修改一次账号名。"
)


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
    """取 access_token（缓存到过期前 60 秒）并发送单聊被动回复。"""

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

    def reply_c2c(self, openid: str, msg_id: str, content: str, seq: int = 1) -> None:
        body = json.dumps({"msg_type": 0, "content": content, "msg_id": msg_id, "msg_seq": seq}).encode()
        request = UrlRequest(
            f"{API_BASE}/v2/users/{quote(openid, safe='')}/messages", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"QQBot {self.access_token()}"},
        )
        with urlopen(request, timeout=10) as response:
            response.read()


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

        if op == 0 and payload.get("t") == "C2C_MESSAGE_CREATE":
            event_id = str(payload.get("id") or data.get("id") or "")
            if event_id and seen.first_time(event_id):
                background.add_task(handle_c2c, client, config, data)
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
