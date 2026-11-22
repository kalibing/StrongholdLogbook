"""鹰角通行证「网页登录」反向代理。

目的：让用户在本站里打开鹰角官方登录页、正常输账号密码/短信/扫码（人机验证由官方页面自己处理），
登录成功后由**服务端**从登录响应里取走 access token，再换成 u8 token 拉成就。

路由（全部同源，所以不受 CORS 限制）::

    /hg/user/login       →  https://user.hypergryph.com/login     （HTML / 静态页，改写 CDN 与 API 地址）
    /hg/cdn/*            →  https://web.hycdn.cn/*                （页面 bundle，改写 API 域名）
    /hg/as/*             →  https://as.hypergryph.com/*           （表单登录接口，顺带捕获 token）
    /hg/u8/*             →  https://u8.hypergryph.com/*
    /hg/binding/*        →  https://binding-api-account-prod.hypergryph.com/*
    /hg/web/*            →  https://web-api.hypergryph.com/*

服务端只做转发：请求体不落盘、不写日志。命中登录接口时只把响应里的 `data.token` / `data.uid`
记进 10 分钟的内存槽（按浏览器 nonce 区分），前端取走后立刻调用 `/api/achv/session` 完成绑定。
"""

from __future__ import annotations

import gzip
import json
import re
import secrets
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

HOSTS = {
    "user": "https://user.hypergryph.com",
    "as": "https://as.hypergryph.com",
    "u8": "https://u8.hypergryph.com",
    "binding": "https://binding-api-account-prod.hypergryph.com",
    "web": "https://web-api.hypergryph.com",
}
CDN = "https://web.hycdn.cn"
CAPTURE_TTL = 600
CAPTURES: dict[str, dict] = {}
NONCE_COOKIE = "hg_login"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")

LOGIN_PATHS = re.compile(r"/user/auth/v\d/token_by_(?:phone_password|phone_code|scan_code)$")
DROP_REQUEST_HEADERS = {
    "host", "origin", "referer", "content-length", "connection", "accept-encoding",
    "cookie2", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "if-none-match",
}
DROP_RESPONSE_HEADERS = {
    "content-encoding", "content-length", "transfer-encoding", "connection",
    "content-security-policy", "content-security-policy-report-only", "x-frame-options",
    "strict-transport-security", "public-key-pins", "alt-svc", "clear-site-data",
}

router = APIRouter(prefix="/hg")


def build_url(base: str, path: str, query: str) -> str:
    return base + "/" + path.lstrip("/") + (("?" + query) if query else "")


def fetch(url: str, method: str, headers: dict, body: bytes | None) -> tuple[int, dict, bytes]:
    request = urllib.request.Request(url, data=body, method=method)
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), error.read()
    except OSError as error:
        raise HTTPException(502, f"连接鹰角服务器失败：{error}") from error


def decode_body(headers: dict, body: bytes) -> bytes:
    encoding = ""
    for key, value in headers.items():
        if key.lower() == "content-encoding":
            encoding = value.lower()
    if body[:2] == b"\x1f\x8b" or "gzip" in encoding:
        try:
            return gzip.decompress(body)
        except OSError:
            return body
    return body


def is_text(headers: dict) -> bool:
    for key, value in headers.items():
        if key.lower() == "content-type":
            lowered = value.lower()
            return any(kind in lowered for kind in ("text/", "javascript", "json", "css", "xml"))
    return False


def rewrite_cookie(value: str) -> str:
    """官方域 cookie → 本站可用：去掉 Domain / Secure，SameSite=None → Lax。"""
    parts = [part.strip() for part in value.split(";") if part.strip()]
    kept: list[str] = []
    for part in parts:
        name = part.split("=", 1)[0].strip().lower()
        if name in {"domain", "secure", "partitioned"}:
            continue
        kept.append("SameSite=Lax" if name == "samesite" else part)
    return "; ".join(kept)


def rewrite_text(text: str) -> str:
    """把官方页面里的绝对地址换成本站同源路径。"""
    text = text.replace(CDN + "/user-center/", "/hg/cdn/user-center/")
    text = text.replace(CDN + "/", "/hg/cdn/")
    for alias in ("as", "u8", "binding", "web"):
        text = text.replace(HOSTS[alias], f"/hg/{alias}")
    return text


def nonce_of(request: Request) -> str:
    value = request.cookies.get(NONCE_COOKIE) or ""
    return value if re.fullmatch(r"[A-Za-z0-9]{16,64}", value) else ""


def ensure_nonce(request: Request, response: Response) -> None:
    if nonce_of(request):
        return
    response.set_cookie(NONCE_COOKIE, secrets.token_hex(16), max_age=CAPTURE_TTL,
                        httponly=False, samesite="lax", path="/")


def remember(nonce: str, payload: dict) -> None:
    if not nonce:
        return
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    token = ""
    for key in ("token", "accessToken", "access_token"):
        value = (data or {}).get(key)
        if isinstance(value, str) and len(value) >= 16:
            token = value
            break
    if not token:
        return
    uid = ""
    for key in ("uid", "hgId", "userId"):
        value = (data or {}).get(key)
        if isinstance(value, (str, int)) and str(value):
            uid = str(value)
            break
    CAPTURES[nonce] = {"access_token": token, "uid": uid, "at": time.time()}


def purge() -> None:
    now = time.time()
    for key in [key for key, value in CAPTURES.items() if now - value["at"] > CAPTURE_TTL]:
        CAPTURES.pop(key, None)


def respond(status: int, headers: dict, payload: bytes, request: Request, rewrite: bool) -> Response:
    raw = decode_body(headers, payload) if rewrite else payload
    if rewrite and is_text(headers):
        raw = rewrite_text(raw.decode("utf-8", "replace")).encode("utf-8")
        headers = {key: value for key, value in headers.items() if key.lower() != "content-encoding"}
    response = Response(content=raw, status_code=status)
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in DROP_RESPONSE_HEADERS:
            continue
        response.headers.append(key, rewrite_cookie(value) if lowered == "set-cookie" else value)
    response.headers["Cache-Control"] = "no-store"
    if rewrite:
        ensure_nonce(request, response)
    return response


async def relay(host: str, path: str, request: Request, rewrite: bool) -> Response:
    target = build_url(HOSTS[host], path, request.url.query)
    headers = {key: value for key, value in request.headers.items() if key.lower() not in DROP_REQUEST_HEADERS}
    headers.setdefault("User-Agent", UA)
    headers["Accept-Encoding"] = "identity"
    body = await request.body() if request.method not in {"GET", "HEAD"} else None
    status, upstream, payload = fetch(target, request.method, headers, body)

    if LOGIN_PATHS.search("/" + path.lstrip("/")):
        try:
            parsed = json.loads(decode_body(upstream, payload).decode("utf-8", "replace"))
        except (ValueError, UnicodeDecodeError):
            parsed = {}
        if isinstance(parsed, dict) and not parsed.get("status"):
            remember(nonce_of(request), parsed)

    return respond(status, upstream, payload, request, rewrite)


@router.get("")
@router.get("/")
def landing() -> RedirectResponse:
    return RedirectResponse("/hg/user/login", status_code=302)


@router.get("/cdn/{path:path}")
async def cdn(path: str, request: Request) -> Response:
    target = build_url(CDN, path, request.url.query)
    status, headers, payload = fetch(target, "GET", {"User-Agent": UA, "Accept-Encoding": "identity"}, None)
    return respond(status, headers, payload, request, rewrite=True)


for _alias in HOSTS:  # /hg/user/*、/hg/as/*、/hg/u8/* …
    async def _entry(path: str, request: Request, alias=_alias) -> Response:
        return await relay(alias, path, request, rewrite=True)

    router.add_api_route(f"/{_alias}/{{path:path}}", _entry,
                         methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])

capture_router = APIRouter(prefix="/api/hg")


@capture_router.get("/capture")
def capture(request: Request) -> dict:
    purge()
    data = CAPTURES.get(nonce_of(request)) if nonce_of(request) else None
    if not data:
        return {"ready": False}
    return {"ready": True, "access_token": data["access_token"], "uid": data["uid"]}


@capture_router.delete("/capture", status_code=204)
def forget(request: Request) -> Response:
    if nonce_of(request):
        CAPTURES.pop(nonce_of(request), None)
    return Response(status_code=204)


@capture_router.post("/report")
async def reqable_report(request: Request) -> dict:
    """Reqable「报告服务器」回调：整段报文做正则，捞出 playerSummary 的 code。"""
    from . import capture as capture_module

    client = request.client.host if request.client else ""
    if client not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(403, "仅接受本机 Reqable 上报")
    body = (await request.body())[: 8 * 1024 * 1024]
    tokens = capture_module.ingest(body.decode("utf-8", "replace"))
    return {"ok": True, "captured": len(tokens)}
