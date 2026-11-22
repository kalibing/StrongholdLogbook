"""本机全自动换取 u8 token（不抓包、不开游戏）。

链路（每一步都实测过）::

    .local/hgsdk_plain.json  ← tools/hgsdk_unlock.py 解出的 hgsdk 登录态
            │  user_token
            ▼
    POST https://as.hypergryph.com/user/oauth2/v2/grant
         {"type":1,"appCode":"7318def77669979d","token":<user_token>}
            │  data.token = access_token（176 字符）
            ▼
    POST https://as.hypergryph.com/u8/user/v1/getToken
         appId=1 / channelId=1 / worldId=1 / subChannel="1" / platform=2
         deviceId=<u8 设备号>，extension={"code":<access_token>,"type":2,"isSuc":true}
         sign = HMAC-SHA1(salt, 除 sign 外按键名升序 k=v 用 & 连接，值不编码)
            │  data.token = u8 token（544 字符）
            ▼
    playerSummary?code=<u8 token>

appId / channelId / worldId / subChannel 来自 `U8Data\\config\\config.bin`
（AES-256-CBC，key/IV 硬编码在 U8SDK.dll 的 .rdata，见 tools/decrypt_u8_config.py）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

APP_CODE = "7318def77669979d"
SIGN_KEY = b"91240f70c09a08a6bc72af1a5c8d4670"
GRANT_URL = "https://as.hypergryph.com/user/oauth2/v2/grant"
U8_URL = "https://as.hypergryph.com/u8/user/v1/getToken"
DEFAULT_DEVICE = "c7d7ec13d0e1d29f941697f93b715fc3"
CHANNEL = {"appId": "1", "channelId": "1", "worldId": "1", "subChannel": "1"}
TIMEOUT = 25

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".local" / "hgsdk_plain.json"
FOUND = ROOT / ".local" / "u8_found.json"


class DeviceTokenError(Exception):
    """本机换取失败；message 面向用户。"""


def _call(url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    for key, value in {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept-Encoding": "identity",
        "X-AppCode": APP_CODE,
        "X-DeviceType": "2",
        "X-DeviceModel": "DESKTOP-D59UCI1",
    }.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw, status = response.read(), response.status
    except urllib.error.HTTPError as error:
        raw, status = error.read(), error.code
    except OSError as error:
        raise DeviceTokenError(f"连接鹰角失败：{error}") from error
    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return status, {"_raw": raw[:200].decode("utf-8", "replace")}


def device_id() -> str:
    """u8 层设备号：优先用上次抓包记录的值，否则用已知常量。"""
    try:
        payload = json.loads(FOUND.read_text(encoding="utf-8"))
        value = payload.get("u8_device") or payload.get("device")
        if isinstance(value, str) and len(value) == 32:
            return value
    except (OSError, ValueError):
        pass
    return DEFAULT_DEVICE


def load_login() -> tuple[str, str]:
    """读 hgsdk 登录态，返回 (hypergryph_id, user_token)。"""
    if not STATE.is_file():
        raise DeviceTokenError(
            "缺少 hgsdk 登录态缓存：先运行 `python tools\\hgsdk_unlock.py` 解一次本机登录信息")
    try:
        payload = json.loads(STATE.read_text(encoding="utf-8"))
    except ValueError as error:
        raise DeviceTokenError(f"hgsdk 缓存无法解析：{error}") from error
    for account in payload.get("accounts") or []:
        token = account.get("user_token")
        uid = account.get("uid")
        if token and uid:
            return str(uid), str(token)
    raise DeviceTokenError("hgsdk 缓存里没有有效账号（可能未在 PC 端登录过）")


def sign(params: dict) -> str:
    message = "&".join(f"{key}={params[key]}" for key in sorted(params) if key != "sign")
    return hmac.new(SIGN_KEY, message.encode(), hashlib.sha1).hexdigest()


def grant(user_token: str) -> str:
    status, payload = _call(GRANT_URL, {"type": 1, "appCode": APP_CODE, "token": user_token})
    token = ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get("token")
    if status != 200 or not token:
        raise DeviceTokenError(f"换取 access_token 失败（HTTP {status}）：{payload.get('msg') or payload}")
    return str(token)


def get_u8_token(access_token: str) -> str:
    body = {
        "appId": CHANNEL["appId"],
        "channelId": CHANNEL["channelId"],
        "worldId": CHANNEL["worldId"],
        "subChannel": CHANNEL["subChannel"],
        "platform": 2,
        "deviceId": device_id(),
        "deviceId2": "",
        "deviceId3": "",
        "extension": json.dumps({"code": access_token, "type": 2, "isSuc": True}, separators=(",", ":")),
    }
    body["sign"] = sign(body)
    status, payload = _call(U8_URL, body)
    token = payload.get("token") or ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get("token")
    if status != 200 or not token:
        raise DeviceTokenError(f"换取 u8 token 失败（HTTP {status}）：{payload.get('message') or payload.get('msg') or payload}")
    return str(token)


def mint() -> tuple[str, str]:
    """返回 (hypergryph_id, u8_token)。"""
    uid, user_token = load_login()
    return uid, get_u8_token(grant(user_token))
