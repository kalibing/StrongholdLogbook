# -*- coding: utf-8 -*-
"""从 Reqable 抓包目录里把成就接口的 u8 token 挖出来。

背景：`u8_token` 是游戏客户端（或游戏内 H5 会话）签出来的，网页侧没有公开兑换口子，
所以最稳的来源就是**抓一次包**。Reqable 的会话会落盘到
``%APPDATA%\\Reqable\\capture\\*.reqable``，请求行里带着
``GET /api/autoChess/act3autochess/playerSummary?code=…`` 或 H5 入口的 ``u8_token=…``。

这里只做「读文件 → 正则取参 → URL 解码」，不联网、不改动抓包文件。
"""

from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path

DEFAULT_DIR = Path(os.getenv("REQABLE_CAPTURE_DIR") or (Path(os.environ.get("APPDATA", "~")) / "Reqable" / "capture"))
TOKEN_PATTERN = re.compile(rb"(?:code|u8_token)=([A-Za-z0-9%+/=_\-]{32,})")
SEASON_HINTS = (b"playerSummary", b"autoChess/index", b"act3autochess", b"act1autochess")
MAX_FILES = 400
MAX_BYTES = 4 * 1024 * 1024


def capture_files(directory: Path | str | None = None, limit: int = MAX_FILES) -> list[Path]:
    base = Path(directory) if directory else DEFAULT_DIR
    if not base.is_dir():
        return []
    files = [path for path in base.iterdir() if path.is_file() and path.suffix == ".reqable"]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[:limit]


def candidate_tokens(directory: Path | str | None = None, limit: int = MAX_FILES) -> list[tuple[str, str]]:
    """返回 [(token, 来源)]，先给 Reqable 报告服务器推送的，再给磁盘上能扫到的。"""
    found: list[tuple[str, str]] = list(RECENT)
    seen = {token for token, _ in found}
    for path in capture_files(directory, limit):
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            raw = path.read_bytes()
        except OSError:
            continue
        if not any(hint in raw for hint in SEASON_HINTS):
            continue
        for match in TOKEN_PATTERN.finditer(raw):
            token = urllib.parse.unquote(match.group(1).decode("ascii", "ignore")).strip()
            if len(token) < 32 or token in seen:
                continue
            seen.add(token)
            found.append((token, path.name))
    return found


RECENT: list[tuple[str, str]] = []
RECENT_LIMIT = 20


def ingest(text: str, origin: str = "reqable-report") -> list[str]:
    """Reqable「报告服务器」推送过来的请求（HAR 或自定义 JSON）里抠 token。

    不解析结构：整段文本做正则，省得跟着 Reqable 的报文格式走。
    """
    tokens: list[str] = []
    for match in TOKEN_PATTERN.finditer(text.encode("utf-8", "replace")):
        token = urllib.parse.unquote(match.group(1).decode("ascii", "ignore")).strip()
        if len(token) >= 32 and token not in tokens:
            tokens.append(token)
    for token in reversed(tokens):  # 新的插到最前
        RECENT.insert(0, (token, origin))
    del RECENT[RECENT_LIMIT:]
    return tokens


def recent() -> list[tuple[str, str]]:
    return list(RECENT)
