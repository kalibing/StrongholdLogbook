# -*- coding: utf-8 -*-
"""一条命令全自动更新成就档案：
解 hgsdk 登录态 → oauth grant → u8 getToken → 打成就接口 → 绑定到本地站点。

不需要抓包、不需要打开游戏。

用法：
    python tools\\auto_achv.py [--api http://127.0.0.1:8000] [--user demo] [--password xxx]
"""
import argparse
import gzip
import http.cookiejar
import io
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
MINT = ROOT / "tools" / "u8_gettoken_from_hgsdk.py"
RESULT = ROOT / ".local" / "u8_gettoken_hgsdk.json"


def call(url: str, method: str = "GET", body: dict | None = None, headers: dict | None = None,
         opener=None) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("User-Agent", "Mozilla/5.0")
    request.add_header("Accept-Encoding", "gzip")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    open_fn = opener.open if opener else urllib.request.urlopen
    try:
        with open_fn(request, timeout=30) as response:
            raw, status = response.read(), response.status
    except urllib.error.HTTPError as error:
        raw, status = error.read(), error.code
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return status, raw.decode("utf-8", "replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--origin", default="http://localhost:5173")
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None, help="站点密码（缺省交互输入）")
    parser.add_argument("--token", help="跳过自动换取，直接用给定 u8 token 绑定")
    args = parser.parse_args()

    token = args.token
    if not token:
        print("[1/3] 解 hgsdk 登录态并换 u8 token …")
        result = subprocess.run([str(PYTHON), str(MINT)], cwd=str(ROOT),
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        tail = "\n".join(result.stdout.strip().splitlines()[-4:])
        print(tail or "(无输出)")
        if result.returncode != 0 or not RESULT.exists():
            print("[!] 换取失败：", (result.stderr or "")[-300:])
            return 1
        payload = json.loads(RESULT.read_text(encoding="utf-8"))
        token = payload.get("u8_token", "")
        print(f"    u8 token len={len(token)} head={token[:8]}…  nickname={payload.get('nickname')}")
        if not token:
            print("[!] 结果里没有 u8_token")
            return 1

    print(f"[2/3] 登录站点 {args.api} …")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    status, text = call(f"{args.api}/api/session", "POST",
                        {"username": args.user, "password": args.password},
                        {"Origin": args.origin}, opener)
    if status != 200:
        print(f"[!] 登录失败 {status} {text[:120]}")
        return 1
    print("    ok")

    print("[3/3] 绑定成就数据 …")
    status, text = call(f"{args.api}/api/achv/session", "POST",
                        {"token": "code=" + token}, {"Origin": args.origin}, opener)
    if status != 200:
        print(f"[!] 绑定失败 {status} {text[:200]}")
        return 1
    body = json.loads(text)
    data = body.get("data") or {}
    player = data.get("player") or {}
    print(f"    ✓ 已更新：{player.get('nickname')}#{player.get('nick_number')} "
          f"奖杯 {data.get('trophy', {}).get('total')} 称号 {len(data.get('titles') or [])} "
          f"标识 {len((data.get('bands') or {}).get('badges') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
