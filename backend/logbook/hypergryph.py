"""鹰角通行证 → u8 token → 卫戍协议成就接口。

链路（全部在本机实测过的部分已标注）::

    手机号+密码 ──▶ as.hypergryph.com/user/auth/v1/token_by_phone_password  (已实测：存在)
                                     │  data.token  （鹰角 access token）
                                     ▼
    access token + channel uid ──▶ as.hypergryph.com/u8/user/v1/getToken   (已实测：字段校验)
                                     │  data.token  （u8 token，等价于 H5 的 code 参数）
                                     ▼
    u8 token ──▶ ak-webview.hypergryph.com/api/autoChess/act3autochess/playerSummary?code=…
                                     │  （已实测：URL 编码后 200，原样传 → 10008 找不到玩家角色）
                                     ▼
                              成就统计 JSON

`getToken` 的 `extension` 需要 `{uid, access_token}`，其中 uid 是鹰角账号 uid。
拿不到 uid 时不允许瞎猜：直接抛 `CredentialError`，让前端提示改用「粘贴链接」方式，
并用 `warnings` 把服务端原文带回，方便后续定位。
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request

HG_BASE = "https://as.hypergryph.com"
U8_BASE = "https://u8.hypergryph.com"
VIEW_BASE = "https://ak-webview.hypergryph.com"
SEASON = "act3autochess"
U8_SIGN_KEY = b"91240f70c09a08a6bc72af1a5c8d4670"
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 12; SM-A5560 Build/V417IR; wv) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36; SKLand/1.52.1"
)
TIMEOUT = 20


class CredentialError(Exception):
    """凭据链在某一步失败；message 面向用户，detail 保留服务端原文。"""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


def _request(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, str]:
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("User-Agent", USER_AGENT)
    request.add_header("Accept-Encoding", "gzip")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read()
        status = error.code
    except OSError as error:  # 断网、DNS、超时
        raise CredentialError("连接鹰角服务器失败，请检查网络后重试", str(error)) from error
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return status, raw.decode("utf-8", "replace")


def u8_sign(data: dict) -> str:
    """u8 接口的签名：按 key 排序后 urlencode，HMAC-SHA1 固定密钥，取小写十六进制。"""
    query = urllib.parse.urlencode(sorted(data.items()))
    return hmac.new(U8_SIGN_KEY, query.encode(), "sha1").hexdigest().lower()


def _device_ids() -> tuple[str, str, str]:
    return secrets.token_hex(16), "86" + "".join(secrets.choice("0123456789") for _ in range(13)), secrets.token_hex(16)


def _error_text(payload: dict) -> str:
    return str(payload.get("msg") or payload.get("message") or payload)[:300]


def token_by_password(phone: str, password: str) -> tuple[str, str]:
    """返回 (access_token, uid)。uid 可能为空，由 getToken 那一步兜底判断。"""
    status, text = _request("POST", f"{HG_BASE}/user/auth/v1/token_by_phone_password",
                            {"phone": phone, "password": password})
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise CredentialError("鹰角通行证返回了无法解析的内容", text[:300]) from None
    token = ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get("token")
    if not token:
        raise CredentialError(f"鹰角通行证登录失败：{_error_text(payload)}", text[:300])
    data = payload.get("data") or {}
    uid = ""
    for key in ("uid", "userId", "hgUid", "accountId", "account"):
        value = data.get(key)
        if isinstance(value, str) and value:
            uid = value
            break
    return token, uid


def _uid_from_token(token: str) -> str:
    """token 有时是 base64(JSON)，里面带 uid；解不出来就返回空串。"""
    padded = token + "=" * (-len(token) % 4)
    try:
        raw = base64.b64decode(padded)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if isinstance(payload, dict):
        for key in ("uid", "userId", "uidStr", "id"):
            value = payload.get(key)
            if isinstance(value, (str, int)) and str(value):
                return str(value)
    return ""


def u8_token(access_token: str, uid: str = "") -> tuple[str, str, list[str]]:
    """用 access token 换 u8 token；返回 (uid, u8_token, warnings)。"""
    warnings: list[str] = []
    channel_uid = uid or _uid_from_token(access_token)
    if not channel_uid:
        warnings.append("未能从通行证响应里读到鹰角账号 uid，按空值重试一次")
    device_id, device_id2, device_id3 = _device_ids()
    last = ""
    for candidate_uid in ([channel_uid] if channel_uid else []) + [""]:
        for key in ("access_token", "token"):
            body = {
                "appId": "1",
                "platform": 1,
                "channelId": "1",
                "subChannel": "1",
                "worldId": "1",
                "deviceId": device_id,
                "deviceId2": device_id2,
                "deviceId3": device_id3,
                "extension": json.dumps({"uid": candidate_uid, key: access_token}, separators=(",", ":")),
            }
            body["sign"] = u8_sign({k: v for k, v in body.items() if k != "sign"})
            status, text = _request("POST", f"{HG_BASE}/u8/user/v1/getToken", body)
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                last = text[:300]
                continue
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            token = (data or {}).get("token")
            if token:
                return str((data or {}).get("uid") or candidate_uid or ""), token, warnings
            last = _error_text(payload)
    raise CredentialError(
        f"鹰角拒绝了这次换取（{last or '未知错误'}）。请改用「拿令牌」：游戏内打开成就页，复制链接粘贴即可。",
        last,
    )


def extract_code(text: str) -> str:
    """从整条 H5 链接、抓包请求行、query 串或裸 token 里取出 code / u8_token。"""
    value = (text or "").strip().strip('"').strip("'")
    if not value:
        raise CredentialError("请粘贴卫戍协议成就页链接或 code 令牌")
    match = re.search(r"(?:^|[?&\s])(code|u8_token|token)=([^&\s]+)", value)
    if match:
        value = match.group(2)
    value = urllib.parse.unquote(value).strip()
    if len(value) < 32:
        raise CredentialError("令牌长度不对，请确认复制完整（应为 H5 链接或 code 参数）")
    return value


def player_summary(code: str) -> dict:
    """用 u8 token 拉成就统计原始 JSON。"""
    query = urllib.parse.urlencode({"code": code})
    status, text = _request("GET", f"{VIEW_BASE}/api/autoChess/{SEASON}/playerSummary?{query}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise CredentialError("成就接口返回了无法解析的内容", text[:300]) from None
    if payload.get("status") or payload.get("code"):
        raise CredentialError(f"成就接口拒绝：{_error_text(payload)}", text[:300])
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        raise CredentialError("成就接口没有返回数据", text[:300])
    return data


def connect_with_password(phone: str, password: str) -> tuple[str, str, dict, list[str]]:
    """账密登录：返回 (uid, u8_token, summary, warnings)。"""
    access_token, uid = token_by_password(phone, password)
    uid, code, warnings = u8_token(access_token, uid)
    return uid, code, player_summary(code), warnings


def account_info(access_token: str) -> dict:
    """通行证 access token → 账号信息（含 hgId，即 getToken 需要的 channel uid）。"""
    query = urllib.parse.urlencode({"token": access_token})
    status, text = _request("GET", f"{HG_BASE}/user/info/v1/basic?{query}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise CredentialError("读取通行证账号信息失败", text[:300]) from None
    if payload.get("status") or payload.get("code"):
        raise CredentialError(f"读取通行证账号信息失败：{_error_text(payload)}", text[:300])
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if not data:
        raise CredentialError("通行证没有返回账号信息", text[:300])
    return data


def channel_token(access_token: str) -> str:
    """网页登录后官方前端会调的接口；接口不可用时返回空串，不当作致命错误。"""
    query = urllib.parse.urlencode({"token": access_token})
    try:
        status, text = _request("GET", f"{U8_BASE}/u8/oauth2/auth/v1/channel_token?{query}")
        payload = json.loads(text)
    except (OSError, json.JSONDecodeError, CredentialError):
        return ""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    value = (data or {}).get("channelToken")
    return value if isinstance(value, str) else ""


def connect_with_access_token(access_token: str, uid: str = "") -> tuple[str, str, dict, list[str]]:
    """网页登录拿到的 access token → (uid, u8_token, summary, warnings)。"""
    warnings: list[str] = []
    if not uid:
        try:
            info = account_info(access_token)
            uid = str(info.get("hgId") or info.get("uid") or "")
        except CredentialError as error:
            warnings.append(f"读取账号信息失败：{error}")
    errors: list[str] = []
    try:
        resolved, code, notes = u8_token(access_token, uid)
        warnings.extend(notes)
        return resolved, code, player_summary(code), warnings
    except CredentialError as error:
        errors.append(str(error))
    code = channel_token(access_token)
    if code:
        try:
            return uid, code, player_summary(code), warnings
        except CredentialError as error:
            errors.append(str(error))
    raise CredentialError("换取 u8 token 失败：" + "；".join(errors[:2]), " | ".join(errors)[:400])


