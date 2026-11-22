# -*- coding: utf-8 -*-
"""u8_watch.py — 抓包目录守护：自动把抓到的 u8 token 绑进 logbook，取代「每天手动贴链接」。

用法
----
    python tools\\u8_watch.py --dir "<用户目录>\\Desktop\\新建文件夹" \\
        --api http://127.0.0.1:8000 --user demo --password <站点密码>

    python tools\\u8_watch.py --dir <抓包目录> --api ... --once      # 只跑一轮

行为
----
1. 轮询 --dir（递归，可多次指定）下的 ``*request_*.txt``（Reqable 导出的请求报文）。
2. 文件若是 gzip 先解压；取首行，用 ``u8_token=([^\\s&]+)`` 或
   ``playerSummary?code=([^\\s&]+)`` 抓 token，再做 URL 解码。
3. 用 --user/--password 登录 ``POST {api}/api/session``（带 Origin 头）拿会话 cookie，
   再 ``POST {api}/api/achv/session`` body ``{"token": "code=<token>"}``。
4. 成功打印昵称/奖杯，失败打印原因。
5. 幂等：``.local\\u8_watch_state.json`` 记录已处理的 (路径, mtime) 与已提交 token，
   不重复提交；token 去重。

依赖：仅标准库（gzip / json / urllib / http.cookiejar）。
"""
from __future__ import annotations

import argparse
import getpass
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / ".local" / "u8_watch_state.json"
ORIGIN = "http://localhost:5173"
REQUEST_GLOB = "*request_*.txt"
PATTERNS = (re.compile(r"u8_token=([^\s&\"']+)"), re.compile(r"playerSummary\?code=([^\s&\"']+)"))
MIN_TOKEN = 32


# ------------------------------------------------------------------ 抓 token
def read_request_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw)
        except OSError:
            return raw
    return raw


def token_from_file(path: Path) -> tuple[str | None, str]:
    """返回 (token, 说明)。取首行匹配，失败返回 (None, 原因)。"""
    try:
        blob = read_request_bytes(path)
    except OSError as error:
        return None, f"读取失败: {error}"
    first = blob.split(b"\n", 1)[0].decode("latin-1", "replace")
    for pattern in PATTERNS:
        match = pattern.search(first)
        if match:
            token = urllib.parse.unquote(match.group(1)).strip()
            if len(token) >= MIN_TOKEN:
                return token, pattern.pattern
            return None, f"token 太短({len(token)})"
    return None, "首行没有 u8_token / code 参数"


def discover(directories: list[Path]) -> list[Path]:
    found: list[Path] = []
    for base in directories:
        if not base.is_dir():
            print(f"[!] 目录不存在，跳过: {base}")
            continue
        found.extend(sorted((p for p in base.rglob(REQUEST_GLOB) if p.is_file()),
                            key=lambda p: p.stat().st_mtime))
    return found


# ------------------------------------------------------------------ HTTP 客户端
class Client:
    def __init__(self, api: str) -> None:
        self.api = api.rstrip("/")
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.api + path, data=data, method=method)
        request.add_header("Origin", ORIGIN)
        request.add_header("Referer", ORIGIN + "/")
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(request, timeout=30) as response:
                raw, status = response.read(), response.status
        except urllib.error.HTTPError as error:
            raw, status = error.read(), error.code
        except OSError as error:
            return -1, f"连接失败: {error}"
        text = raw.decode("utf-8", "replace")
        try:
            return status, json.loads(text)
        except ValueError:
            return status, text

    def login(self, user: str, password: str) -> bool:
        status, payload = self.call("POST", "/api/session", {"username": user, "password": password})
        if status == 200:
            return True
        print(f"[!] 登录失败 HTTP {status}: {str(payload)[:200]}")
        return False

    def bind(self, token: str) -> tuple[bool, str]:
        status, payload = self.call("POST", "/api/achv/session", {"token": "code=" + token})
        if status == 200 and isinstance(payload, dict):
            data = payload.get("data") or {}
            player = data.get("player") or {}
            trophy = data.get("trophy") or {}
            state = payload.get("state") or {}
            name = player.get("nickname") or state.get("nickname") or "?"
            total = trophy.get("total")
            return True, f"昵称={name} 奖杯={total} uid={player.get('uid') or state.get('uid')}"
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("message") or payload
        else:
            detail = payload
        return False, f"HTTP {status} {str(detail)[:200]}"


# ------------------------------------------------------------------ 状态
def load_state(path: Path) -> dict:
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("files", {})
                data.setdefault("tokens", [])
                return data
        except (OSError, ValueError):
            pass
    return {"files": {}, "tokens": []}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ 主循环
def scan_once(directories: list[Path], client: Client, state: dict) -> tuple[int, int]:
    """返回 (新提交数, 失败数)。"""
    submitted = failed = 0
    seen_tokens = set(state["tokens"])
    for path in discover(directories):
        key = str(path)
        try:
            mtime = int(path.stat().st_mtime)
        except OSError:
            continue
        if state["files"].get(key) == mtime:
            continue
        token, note = token_from_file(path)
        if not token:
            state["files"][key] = mtime        # 记住，别反复报同一文件
            continue
        short = token[:8] + "…(%d)" % len(token)
        if token in seen_tokens:
            state["files"][key] = mtime
            print(f"[=] 跳过重复 token {short}  <- {path.name}")
            continue
        ok, message = client.bind(token)
        state["files"][key] = mtime
        if ok:
            submitted += 1
            state["tokens"].append(token)
            seen_tokens.add(token)
            print(f"[+] 绑定成功 {short}  {message}  <- {path.name}")
        else:
            failed += 1
            print(f"[-] 绑定失败 {short}  {message}  <- {path.name}")
    return submitted, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="抓包目录守护：自动绑定 u8 token")
    parser.add_argument("--dir", action="append", required=True, help="抓包目录（可多次指定）")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    args = parser.parse_args()

    directories = [Path(item) for item in args.dir]
    state_path = Path(args.state)
    state = load_state(state_path)
    client = Client(args.api)

    password = args.password or getpass.getpass('站点密码: ')
    if not client.login(args.user, password):
        return 2
    print(f"[*] 登录成功 {args.user} @ {args.api}")

    if args.once:
        new, bad = scan_once(directories, client, state)
        save_state(state_path, state)
        print(f"[*] 本轮结束：新提交 {new}，失败 {bad}")
        return 0 if new or not bad else 1

    print(f"[*] 守护中，每 {args.interval:g}s 扫一次（Ctrl+C 退出）")
    while True:
        try:
            new, bad = scan_once(directories, client, state)
            save_state(state_path, state)
            if new or bad:
                print(f"[*] {time.strftime('%H:%M:%S')} 新提交 {new}，失败 {bad}")
        except KeyboardInterrupt:
            print("\n[*] 退出")
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
