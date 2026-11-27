"""B 站登录态：给动态推送用的 Cookie，扫码登录获取并加密存库。

流程（B 站网页端扫码登录接口）：
1. GET passport.bilibili.com/x/passport-login/web/qrcode/generate → data.url（二维码内容）与 data.qrcode_key。
2. 每 2 秒 GET .../qrcode/poll?qrcode_key=…：86101 未扫码、86090 已扫码待确认、86038 已过期、0 成功。
   成功时登录 Cookie（SESSDATA、bili_jct、DedeUserID…）在响应的 Set-Cookie 里。
3. 再访问一次 www.bilibili.com 拿浏览器标识 buvid3（不少接口缺它会被风控）。
4. 用 api.bilibili.com/x/web-interface/nav 检查登录状态（data.isLogin、data.uname）。

Cookie 用 LOGBOOK_CREDENTIAL_KEY 加密后存在 bili_credentials 表（只有一行）；
库里没有时退回环境变量 BILIBILI_COOKIE。日志不记录 Cookie 与二维码内容。
"""

from dataclasses import dataclass
from http.cookies import SimpleCookie
import io
import json
import logging
import os
import time
from typing import Callable
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen

from .credentials import PREFIX, CredentialVault, load_key

LOGGER = logging.getLogger(__name__)

QR_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={key}"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
HOME_URL = "https://www.bilibili.com/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
PURPOSE = "bilibili-cookie"
OWNER = "feeds"
LOGIN_COOKIES = ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "sid")
BROWSER_COOKIES = ("buvid3", "buvid4", "b_nut")
QR_LIFETIME = 180
POLL_EVERY = 2

WAITING = {86101, 86090}
EXPIRED = 86038


@dataclass(frozen=True)
class Response:
    data: dict
    cookies: dict


def http_get(url: str, cookie: str = "", parse: bool = True) -> Response:
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"}
    if cookie:
        headers["Cookie"] = cookie
    with urlopen(UrlRequest(url, headers=headers), timeout=10) as response:
        body = response.read()
        cookies = {}
        for header in response.headers.get_all("Set-Cookie") or []:
            jar = SimpleCookie()
            try:
                jar.load(header)
            except Exception:  # noqa: BLE001 - 不规范的 Set-Cookie 跳过即可
                continue
            cookies.update({name: morsel.value for name, morsel in jar.items()})
    return Response(json.loads(body) if parse else {}, cookies)


def join_cookies(cookies: dict) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items() if value)


# ---------------------------------------------------------------- 存储


def vault(database) -> CredentialVault:
    row = database.execute("SELECT cookie FROM bili_credentials WHERE id = 1").fetchone()
    return CredentialVault(load_key(bool(row and row["cookie"].startswith(PREFIX))))


def stored_cookie(database) -> str:
    """库里的 Cookie（解密后），没有时用环境变量 BILIBILI_COOKIE。"""
    row = database.execute("SELECT cookie FROM bili_credentials WHERE id = 1").fetchone()
    if row and row["cookie"]:
        return vault(database).unseal(PURPOSE, OWNER, row["cookie"])
    return os.getenv("BILIBILI_COOKIE", "").strip()


def has_cookie(database) -> bool:
    row = database.execute("SELECT 1 FROM bili_credentials WHERE id = 1").fetchone()
    return row is not None or bool(os.getenv("BILIBILI_COOKIE", "").strip())


def save_cookie(database, cookie: str, uname: str) -> None:
    sealed = vault(database).seal(PURPOSE, OWNER, cookie)
    database.execute(
        "INSERT INTO bili_credentials (id, cookie, uname, updated_at) VALUES (1, %s, %s, now()) "
        "ON CONFLICT (id) DO UPDATE SET cookie = EXCLUDED.cookie, uname = EXCLUDED.uname, "
        "updated_at = EXCLUDED.updated_at",
        (sealed, uname[:64]),
    )


# ---------------------------------------------------------------- 接口


def login_status(cookie: str, get: Callable = http_get) -> tuple[bool, str]:
    """返回 (是否已登录, 用户名)。没有 Cookie 时不发请求。"""
    if not cookie:
        return False, ""
    data = get(NAV_URL, cookie).data
    info = data.get("data") or {}
    if data.get("code") == 0 and info.get("isLogin"):
        return True, str(info.get("uname") or "")
    return False, ""


def generate_qr(get: Callable = http_get) -> tuple[str, str]:
    data = get(QR_GENERATE_URL).data
    info = data.get("data") or {}
    if data.get("code") != 0 or not info.get("url") or not info.get("qrcode_key"):
        raise RuntimeError(f"qrcode generate code {data.get('code')}")
    return str(info["url"]), str(info["qrcode_key"])


def qr_png(content: str) -> bytes:
    import qrcode

    image = qrcode.make(content, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def wait_for_scan(key: str, get: Callable = http_get, sleep: Callable = time.sleep,
                  lifetime: float = QR_LIFETIME, clock: Callable = time.monotonic) -> str | None:
    """轮询扫码结果；成功返回完整 Cookie 字符串，过期或超时返回 None。"""
    deadline = clock() + lifetime
    while clock() < deadline:
        response = get(QR_POLL_URL.format(key=quote(key, safe="")))
        info = (response.data.get("data") or {})
        code = info.get("code")
        if code == 0:
            cookies = {name: response.cookies[name] for name in LOGIN_COOKIES if name in response.cookies}
            if "SESSDATA" not in cookies:
                raise RuntimeError("login succeeded without SESSDATA")
            try:
                home = get(HOME_URL, join_cookies(cookies), parse=False)
                cookies.update({name: home.cookies[name] for name in BROWSER_COOKIES if name in home.cookies})
            except Exception as error:  # noqa: BLE001 - buvid3 拿不到也先保存登录态
                LOGGER.warning("Could not fetch Bilibili browser cookies: %s", type(error).__name__)
            return join_cookies(cookies)
        if code == EXPIRED:
            return None
        if code not in WAITING:
            raise RuntimeError(f"qrcode poll code {code}")
        sleep(POLL_EVERY)
    return None
