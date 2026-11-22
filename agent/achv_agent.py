#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""卫戍协议成就档案 · 本机助手（源码，可自行打包为 exe）

作用：在你自己的 Windows 机器上，静态解出「明日方舟 PC 端」的登录态，
换一枚 u8 token，然后把成就数据推给你部署的站点。全程不抓包、不启动游戏。

链路（每一步都经作者实测，详见 docs/achievements.md §9.6）::

    HKCU\\SOFTWARE\\HyperGryph\\sdk_data\\<hash>\\REG_GUID
        └─ MMKV key = MD5(REG_GUID + SALT)[:16]
    %LocalAppData%Low\\Hypergryph\\Arknights\\sdk_data_*\\login_cache
        └─ AES-128-CFB 解密（IV 取同名 .crc 偏移 12）→ <hgid>_user_token
    POST as.hypergryph.com/user/oauth2/v2/grant   {type:1, appCode, token}
        └─ data.token = access_token
    POST as.hypergryph.com/u8/user/v1/getToken    appId/channel/world/subChannel + sign
        └─ data.token = u8 token
    POST <站点>/api/session  →  POST <站点>/api/achv/session  {token:"code=<u8token>"}

只读取本机文件与注册表，不写注册表、不改游戏目录、不联网上传任何凭据（只把 u8 token 发给你指定的站点）。

打包：``pyinstaller --onefile --name ArknightsAchvAgent agent/achv_agent.py``
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import getpass
import hashlib
import hmac
import http.cookiejar
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

APP_CODE = "7318def77669979d"
SIGN_KEY = b"91240f70c09a08a6bc72af1a5c8d4670"
SALT = "*6E39452-319B-409C-AB75-865FEA25EC3*"
GRANT_URL = "https://as.hypergryph.com/user/oauth2/v2/grant"
U8_URL = "https://as.hypergryph.com/u8/user/v1/getToken"
CHANNEL = {"appId": "1", "channelId": "1", "worldId": "1", "subChannel": "1"}
SALT_SEED = SALT.encode()
UA = "Mozilla/5.0"
MMKV_MAGIC = b"\xff\xff\xff\x07"


# ------------------------------------------------------------------ 控制台编码
if os.name == "nt":
    os.system("chcp 65001 >nul")
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- 工具
def say(message: str) -> None:
    print(message, flush=True)


def http(url: str, payload: dict | None = None, headers: dict | None = None, opener=None) -> tuple[int, str]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    request.add_header("User-Agent", UA)
    request.add_header("Accept-Encoding", "identity")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    open_fn = opener.open if opener else urllib.request.urlopen
    try:
        with open_fn(request, timeout=25) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except OSError as error:
        return -1, f"{type(error).__name__}: {error}"


# ------------------------------------------------------------------- hgsdk 登录态
class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> DATA_BLOB:
    buffer = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))


def dpapi_unprotect(data: bytes) -> bytes | None:
    out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(_blob(data)), None, None, None, None, 0, ctypes.byref(out))
    return ctypes.string_at(out.pbData, out.cbData) if ok else None


def qt_bytes(raw: bytes) -> bytes:
    """Qt QSettings 里的 @ByteArray(...) → 原始字节。"""
    text = raw.decode("utf-16le", "ignore") if raw[:1] == b"@" and raw[1:2] == b"\x00" else raw.decode("latin-1")
    text = text.strip()
    if not text.startswith("@ByteArray("):
        return text.encode("latin-1", "ignore")
    inner = text[len("@ByteArray("):].rstrip(")")
    if inner.startswith('"') and inner.endswith('"'):
        inner = inner[1:-1]
    out = bytearray()
    index = 0
    while index < len(inner):
        if inner[index] == "\\" and inner[index + 1: index + 2] == "x":
            out.append(int(inner[index + 2: index + 4], 16))
            index += 4
        else:
            out.extend(inner[index].encode("latin-1", "ignore"))
            index += 1
    return bytes(out)


def registry_guids() -> list[str]:
    import winreg

    guids: list[str] = []
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\HyperGryph\sdk_data")
    except OSError:
        return guids
    with root:
        index = 0
        while True:
            try:
                name = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            try:
                with winreg.OpenKey(root, name) as sub:
                    guid, _ = winreg.QueryValueEx(sub, "REG_GUID")
                    if isinstance(guid, str) and guid:
                        guids.append(guid.strip())
            except OSError:
                continue
    return guids


def mmkv_key(guid: str) -> bytes:
    return hashlib.md5((guid + SALT).encode()).hexdigest()[:16].encode()


def _varint(buf: bytes, index: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if index >= len(buf):
            raise IndexError
        byte = buf[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
        shift += 7


def _records(body: bytes) -> list[tuple[bytes, bytes]]:
    index = 4
    items: list[tuple[bytes, bytes]] = []
    while index < len(body):
        try:
            klen, index = _varint(body, index)
            if not 0 < klen <= 512 or index + klen > len(body):
                break
            key = body[index: index + klen]
            index += klen
            vlen, index = _varint(body, index)
            if vlen > len(body) - index:
                break
            items.append((key, body[index: index + vlen]))
            index += vlen
        except IndexError:
            break
    return items


def _decode(value: bytes):
    if len(value) == 1:
        return bool(value[0]) if value[0] <= 1 else value[0]
    if len(value) >= 2 and value[0] == len(value) - 1 and all(0x20 <= c < 0x7F for c in value[1:]):
        return value[1:].decode("utf-8", "replace")
    if value and all(0x20 <= c < 0x7F for c in value):
        return value.decode("utf-8", "replace")
    try:
        number, used = _varint(value, 0)
        if used == len(value):
            return number
    except IndexError:
        pass
    return value.hex()


def decrypt_mmkv(path: Path, key: bytes) -> dict:
    from Crypto.Cipher import AES  # pycryptodome

    blob = path.read_bytes()
    actual = int.from_bytes(blob[:4], "little")
    if actual == 0 or actual > len(blob) - 4:
        return {}
    body = blob[4: 4 + actual]
    if body[:4] == MMKV_MAGIC:
        plain = body
    else:
        meta = Path(str(path) + ".crc")
        ivs: list[bytes | None] = [None, b"\x00" * 16, key]
        if meta.exists():
            raw = meta.read_bytes()
            if len(raw) >= 28:
                ivs.insert(0, raw[12:28])
        plain = b""
        for iv in [candidate for candidate in ivs if candidate]:
            candidate_plain = AES.new(key, AES.MODE_CFB, iv=iv, segment_size=128).decrypt(body)
            if candidate_plain[:4] == MMKV_MAGIC:
                plain = candidate_plain
                break
        if not plain:
            return {}
    fields: dict = {}
    for key_bytes, value_bytes in _records(plain):
        fields[key_bytes.decode("utf-8", "replace")] = _decode(value_bytes)
    return fields


def find_login(app_root: Path) -> tuple[str, str] | None:
    """返回 (hgid, user_token)。"""
    guids = registry_guids()
    if not guids:
        return None
    for guid in guids:
        key = mmkv_key(guid)
        for path in app_root.rglob("login_cache"):
            if not path.is_file():
                continue
            fields = decrypt_mmkv(path, key)
            for name, value in fields.items():
                if name.endswith("_user_token") and isinstance(value, str) and len(value) >= 16:
                    hgid = name.split("_", 1)[0]
                    return hgid, value
    return None


# --------------------------------------------------------------------- 换取 token
def grant(user_token: str) -> str:
    status, text = http(GRANT_URL, {"type": 1, "appCode": APP_CODE, "token": user_token},
                        {"X-AppCode": APP_CODE, "X-DeviceType": "2"})
    try:
        payload = json.loads(text)
    except ValueError:
        payload = {}
    token = ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get("token")
    if status != 200 or not token:
        raise RuntimeError(f"换 access_token 失败（HTTP {status}）：{payload.get('msg') or text[:120]}")
    return str(token)


def u8_token(access_token: str) -> str:
    body = {
        "appId": CHANNEL["appId"], "channelId": CHANNEL["channelId"],
        "worldId": CHANNEL["worldId"], "subChannel": CHANNEL["subChannel"],
        "platform": 2, "deviceId": secrets.token_hex(16), "deviceId2": "", "deviceId3": "",
        "extension": json.dumps({"code": access_token, "type": 2, "isSuc": True}, separators=(",", ":")),
    }
    message = "&".join(f"{key}={body[key]}" for key in sorted(body))
    body["sign"] = hmac.new(SIGN_KEY, message.encode(), hashlib.sha1).hexdigest()
    status, text = http(U8_URL, body, {"X-AppCode": APP_CODE, "X-DeviceType": "2"})
    try:
        payload = json.loads(text)
    except ValueError:
        payload = {}
    token = payload.get("token") or ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get("token")
    if status != 200 or not token:
        raise RuntimeError(f"换 u8 token 失败（HTTP {status}）：{payload.get('message') or payload.get('msg') or text[:120]}")
    return str(token)


# ------------------------------------------------------------------------- 推站点
def push(api: str, origin: str, user: str, password: str, token: str) -> dict:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    status, text = http(f"{api}/api/session", {"username": user, "password": password},
                        {"Origin": origin}, opener)
    if status != 200:
        raise RuntimeError(f"站点登录失败（HTTP {status}）：{text[:120]}")
    status, text = http(f"{api}/api/achv/session", {"token": "code=" + token}, {"Origin": origin}, opener)
    if status != 200:
        raise RuntimeError(f"推送失败（HTTP {status}）：{text[:160]}")
    return json.loads(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="卫戍协议成就档案 · 本机助手")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="站点地址")
    parser.add_argument("--origin", default="http://localhost:5173", help="站点 Origin（写请求校验用）")
    parser.add_argument("--user", help="站点账号")
    parser.add_argument("--password", help="站点密码")
    parser.add_argument("--app-root", help="Arknights 的 AppData 目录（默认自动查找）")
    parser.add_argument("--print-token", action="store_true", help="只打印 u8 token，不推站点")
    args = parser.parse_args()

    app_root = Path(args.app_root) if args.app_root else (
        Path(os.environ.get("USERPROFILE", "~")) / "AppData" / "LocalLow" / "Hypergryph" / "Arknights")
    say(f"[1/3] 读取本机登录态：{app_root}")
    login = find_login(app_root)
    if not login:
        say("[!] 没找到可用的登录态：请先在「明日方舟 PC 端」登录过一次，再运行本工具。")
        return 2
    hgid, user_token = login
    say(f"      hgid={hgid}  user_token len={len(user_token)}")

    say("[2/3] 换取 u8 token …")
    token = u8_token(grant(user_token))
    say(f"      u8 token len={len(token)} head={token[:8]}…")
    if args.print_token:
        say(token)
        return 0

    user = args.user or input("站点账号: ").strip()
    password = args.password or getpass.getpass("站点密码: ")
    say(f"[3/3] 推送到 {args.api} …")
    body = push(args.api, args.origin, user, password, token)
    data = body.get("data") or {}
    player = data.get("player") or {}
    say(f"      ✓ {player.get('nickname')}#{player.get('nick_number')} "
        f"奖杯 {(data.get('trophy') or {}).get('total')} 称号 {len(data.get('titles') or [])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as error:  # noqa: BLE001
        say(f"[!] {error}")
        raise SystemExit(1)
