"""QQ 官方机器人 Webhook 接入：单聊里发「登录」，机器人回一个一次性免密登录链接；
群里 @机器人发「日报」查询自己的昨日战报。

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
from datetime import datetime, timedelta
import json
import logging
import os
import re
from threading import Lock
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import accounts, bilibili, daily_card, feeds, qq_binding
from .credentials import CredentialStorageError
from .config import settings
from .errors import StorageUnavailable
from .limits import FailureThrottle, RequestSizeLimit
from .records import CHINA
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
        app_id = settings.qq_app_id
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

    def _upload_image(self, base: str, source: dict[str, str]) -> str:
        uploaded = self._post(f"{base}/files", {"file_type": 1, "srv_send_msg": False, **source})
        file_info = uploaded.get("file_info")
        if not isinstance(file_info, str) or not file_info:
            raise RuntimeError("QQ media upload returned no file_info")
        return file_info

    def reply_image(self, target_type: str, openid: str, msg_id: str, png: bytes, content: str = "",
                    seq: int = 1) -> None:
        """用 PNG 作为图片回复一条收到的 QQ 消息。"""
        base = f"/v2/groups/{quote(openid, safe='')}" if target_type == "group" else f"/v2/users/{quote(openid, safe='')}"
        file_info = self._upload_image(base, {"file_data": base64.b64encode(png).decode("ascii")})
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

    def send_group(self, group_openid: str, content: str) -> None:
        """主动消息：不带 msg_id。"""
        self._post(f"/v2/groups/{quote(group_openid, safe='')}/messages", {"msg_type": 0, "content": content})

    def send_group_image(self, group_openid: str, image_url: str, content: str) -> None:
        base = f"/v2/groups/{quote(group_openid, safe='')}"
        file_info = self._upload_image(base, {"url": image_url})
        self._post(f"{base}/messages", {
            "msg_type": 7, "content": content or " ", "media": {"file_info": file_info},
        })


def login_reply(link: str, username: str) -> str:
    return (
        f"你的作战档案账号：{username}\n"
        f"一次性登录链接（10 分钟内有效，只能用一次，请勿转发）：\n{link}"
    )


# 每个 openid 每小时最多签发 5 个登录链接，防止刷消息。
link_quota = FailureThrottle(limit=5, window=60 * 60)
report_quota = FailureThrottle(limit=3, window=60)


def command_parts(content):
    # QQ normally removes the @ prefix, but some group payloads retain it.
    text = re.sub(r"^(?:<@!?[A-Za-z0-9_-]{1,128}>\s*)+", "", content.strip()).lstrip("/")
    parts = text.split(maxsplit=1)
    if not parts:
        return "", ""
    return parts[0], parts[1].strip().upper() if len(parts) == 2 else ""


def binding_reply(config, openid, code):
    if not isinstance(openid, str) or not accounts.OPENID_PATTERN.fullmatch(openid):
        return "暂时无法确认你的 QQ 身份，请重新在私聊里发送指令。"
    if not re.fullmatch(qq_binding.CODE_PATTERN, code):
        return (
            f"已有站点账号：在「我的主页」获取绑定码，然后在这里发送「{settings.qq_bind_command} 绑定码」。\n"
            "新用户：发送「登录」即可注册并自动绑定 QQ。"
        )
    try:
        with connect() as database:
            if code.startswith("W"):
                qq_binding.bind_account(database, config.app_id, openid, code)
                return f"QQ 已绑定。到群里 @我发送「{settings.qq_report_command}」可以查看昨日战报。"
            if code.startswith("G"):
                confirmation = qq_binding.confirm_in_private(database, config.app_id, openid, code)
                return f"回到发起请求的群，@我发送「{settings.qq_report_command} {confirmation}」确认一次。确认码请勿转发。"
    except accounts.AccountError as error:
        return str(error)
    except StorageUnavailable:
        LOGGER.warning("Could not verify a QQ binding")
        return "暂时无法处理绑定，请稍后再试。"
    return "请发送网站绑定码或群里的验证请求码。"


def handle_c2c(client: QQClient, config: BotConfig, data: dict) -> None:
    author = data.get("author")
    author = author if isinstance(author, dict) else {}
    user_openid = author.get("user_openid")
    openid = user_openid or author.get("id")
    msg_id = data.get("id")
    content = (data.get("content") or "").strip()
    if not isinstance(openid, str) or not isinstance(msg_id, str):
        LOGGER.warning("C2C event without user_openid or id; ignored")
        return
    try:
        if is_bili_command(content):
            handle_bili(client, config, "c2c", openid, msg_id, user_openid)
            return
        command, code = command_parts(content)
        if command == settings.qq_bind_command and command not in LOGIN_COMMANDS:
            client.reply_c2c(openid, msg_id, binding_reply(config, user_openid, code))
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


BILI_COMMANDS = {"b站", "b站状态", "b站登录", "登录b站", "bilibili", "哔哩哔哩"}
# 同一时间只挂一张扫码二维码，避免多人同时触发互相覆盖登录态。
bili_login_lock = Lock()


def is_bili_command(content: str) -> bool:
    return re.sub(r"\s+", "", "".join(command_parts(content))).lower() in BILI_COMMANDS


def handle_bili(client: QQClient, config: BotConfig, target_type: str, openid: str, msg_id: str,
                actor_openid: str | None, *, get=bilibili.http_get, sleep=time.sleep) -> None:
    """站点管理员可查询推送账号状态，并在私聊中扫码登录。"""
    def say(text: str, seq: int = 1) -> None:
        client.reply(target_type, openid, msg_id, text, seq)

    denied = "请使用已绑定的站点管理员 QQ 发送「B站状态」。"
    if not isinstance(actor_openid, str) or not accounts.OPENID_PATTERN.fullmatch(actor_openid):
        say(denied)
        return
    try:
        with connect() as database:
            if target_type == "group":
                user = qq_binding.group_account(database, config.app_id, openid, actor_openid)
            else:
                user = accounts.find_qq_account(database, config.app_id, actor_openid)
            allowed = user is not None and accounts.is_admin(database, user["id"])
            cookie = bilibili.stored_cookie(database) if allowed else ""
    except (StorageUnavailable, CredentialStorageError):
        LOGGER.warning("Could not authorize or load the Bilibili status request")
        say("暂时无法读取 B 站登录状态，请稍后再试。")
        return
    if not allowed:
        say(denied)
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
    if target_type == "group":
        say("B 站当前需要登录，请私聊我发「B站状态」扫码。")
        return
    if not bili_login_lock.acquire(blocking=False):
        say("正在等待已有的 B 站登录请求，请稍后再试。")
        return
    try:
        try:
            url, key = bilibili.generate_qr(get)
            png = bilibili.qr_png(url)
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError, ImportError) as error:
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
            say("扫码登录失败，请在私聊重新发「B站状态」。", 2)
            return
        if not new_cookie:
            say("二维码已过期，请在私聊重新发「B站状态」。", 2)
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


def group_report(client, config, group_openid, member_openid, msg_id, code):
    if not isinstance(member_openid, str) or not all(
        accounts.OPENID_PATTERN.fullmatch(value) for value in (group_openid, member_openid)
    ):
        client.reply_group(group_openid, msg_id, "暂时无法确认请求者的 QQ 身份。")
        return
    if code and (not code.startswith("C") or not re.fullmatch(qq_binding.CODE_PATTERN, code)):
        client.reply_group(group_openid, msg_id, f"发「{settings.qq_report_command}」查看昨日战报。")
        return
    day = datetime.now(CHINA).date() - timedelta(days=1)
    try:
        with connect() as database:
            user = qq_binding.group_account(database, config.app_id, group_openid, member_openid)
            if user is None and code:
                user = qq_binding.confirm_in_group(database, config.app_id, group_openid, member_openid, code)
            if user is None:
                request_code = qq_binding.issue_group_code(database, config.app_id, group_openid, member_openid)
                reply = (
                    f"请先私聊我认证。已有站点账号可发「{settings.qq_bind_command}」查看绑定方法，新用户发「登录」。\n"
                    f"已绑定但仍收到提示时，请私聊发「{settings.qq_bind_command} {request_code}」验证本群身份。"
                )
            else:
                reply = ""
                if report_quota.take(str(user["id"])):
                    card = daily_card.load(database, user, day, group=True)
                else:
                    reply = "查询日报太频繁，请稍后再试。"
        if reply:
            client.reply_group(group_openid, msg_id, reply)
        elif not card.matches:
            client.reply_group(group_openid, msg_id, f"{day:%m 月 %d 日}暂无有效作战记录。")
        else:
            png = daily_card.render(card)
            client.reply_image("group", group_openid, msg_id, png)
    except accounts.AccountError as error:
        client.reply_group(group_openid, msg_id, str(error))
    except (StorageUnavailable, daily_card.CardFontError) as error:
        LOGGER.warning("Could not produce a QQ group report: %s", type(error).__name__)
        client.reply_group(group_openid, msg_id, "暂时无法生成昨日战报，请稍后再试。")


def handle_group_at(client: QQClient, config: BotConfig, data: dict) -> None:
    group_openid = data.get("group_openid")
    msg_id = data.get("id")
    content = (data.get("content") or "").strip()
    if not isinstance(group_openid, str) or not accounts.OPENID_PATTERN.fullmatch(group_openid) or not isinstance(msg_id, str):
        LOGGER.warning("Group event without group_openid or id; ignored")
        return
    author = data.get("author")
    member_openid = author.get("member_openid") if isinstance(author, dict) else None
    try:
        with connect() as database:
            feeds.observe_group(database, config.app_id, group_openid)
    except StorageUnavailable:
        LOGGER.warning("Could not record a QQ group event")
    try:
        command, code = command_parts(content)
        if is_bili_command(content):
            handle_bili(client, config, "group", group_openid, msg_id, member_openid)
        elif command == settings.qq_report_command:
            group_report(client, config, group_openid, member_openid, msg_id, code)
        elif command == settings.qq_bind_command:
            client.reply_group(group_openid, msg_id, "请私聊我完成账号绑定，绑定码只发在私聊里。")
        else:
            client.reply_group(group_openid, msg_id, f"@我发送「{settings.qq_report_command}」查看自己的昨日战报。")
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
