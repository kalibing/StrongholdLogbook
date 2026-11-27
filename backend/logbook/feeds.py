"""QQ 推送：明日方舟游戏公告与 B 站官号动态。

两部分：
- 订阅指令（由 qqbot 回调进程调用）：群里 @机器人 或单聊发「订阅公告」「订阅动态」「取消订阅」「订阅状态」。
- 轮询推送进程（python -m logbook.feeds）：定时拉取两个来源，发现新条目后用 QQ 主动消息接口
  发给所有订阅了该来源的群 / 单聊。

数据来源：
- 游戏公告：https://ak-webview.hypergryph.com/api/game/bulletinList?target=IOS，
  详情 /api/game/bulletin/{cid}；公开接口，无需登录。
- B 站动态：https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?host_mid={uid}；
  B 站会拦截未登录的请求，需要在 BILIBILI_COOKIE 里填一个 B 站账号的 Cookie，未配置时不轮询 B 站。

去重：已见过的条目记在 feed_seen 表。某个来源第一次运行（表里还没有记录）时只记录当前列表、不推送，
避免一上线就把历史公告全部发一遍。先记录再发送：进程中途退出时宁可漏发一条，也不重复刷屏。

环境变量：
- 轮询按北京时间调度（见 Schedule）：FEED_BUSY_HOURS 为密集时段，默认 10-18；
  游戏公告 FEED_AK_PEAK / FEED_AK_INTERVAL / FEED_AK_IDLE 默认 30 / 120 / 600 秒，
  B 站 FEED_BILI_PEAK / FEED_BILI_INTERVAL / FEED_BILI_IDLE 默认 60 / 180 / 900 秒
  （分别是忙时段整点前后、忙时段其他时间、其余时间）。
- FEED_BILI_UID：B 站账号 UID，默认 161775300（明日方舟官号）。
- BILIBILI_COOKIE：B 站 Cookie（至少包含 SESSDATA 与 buvid3）。
- FEED_LINKS：设为 1 时在推送里附原文链接。QQ 机器人消息里的链接需要在开放平台配置过域名才能发出，
  默认不附。

日志不记录 Cookie、openid 和消息正文。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html
import json
import logging
import os
import re
import signal
from threading import Event
import time
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from . import bilibili
from .credentials import CredentialStorageError
from .errors import StorageUnavailable
from .storage import connect

LOGGER = logging.getLogger(__name__)

AK = "ak"
BILI = "bili"
SOURCES = {AK: "明日方舟游戏公告", BILI: "明日方舟 B 站动态"}
TARGET_TYPES = ("group", "c2c")

AK_LIST_URL = "https://ak-webview.hypergryph.com/api/game/bulletinList?target=IOS"
AK_DETAIL_URL = "https://ak-webview.hypergryph.com/api/game/bulletin/{cid}"
BILI_FEED_URL = (
    "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
    "?host_mid={uid}&timezone_offset=-480&features=itemOpusStyle"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CHINA = timezone(timedelta(hours=8))
# 超过这个时间的条目不推送（例如 B 站置顶的旧动态、公告列表里被重新排上来的旧公告）。
MAX_AGE = timedelta(days=3)
SUMMARY_LIMIT = 150
# 连续两条主动消息之间的间隔，远低于群聊每分钟 30~60 条的频控。
SEND_GAP = 1.5


# ---------------------------------------------------------------- 订阅


COMMANDS = {
    "订阅公告": ("add", (AK,)),
    "订阅动态": ("add", (BILI,)),
    "订阅全部": ("add", (AK, BILI)),
    "取消订阅公告": ("remove", (AK,)),
    "取消订阅动态": ("remove", (BILI,)),
    "取消订阅": ("remove", (AK, BILI)),
    "退订": ("remove", (AK, BILI)),
    "订阅": ("status", ()),
    "订阅状态": ("status", ()),
}
USAGE = (
    "推送指令：\n"
    "订阅公告 · 明日方舟游戏内公告\n"
    "订阅动态 · 明日方舟 B 站官号动态\n"
    "订阅全部 / 取消订阅公告 / 取消订阅动态 / 取消订阅 / 订阅状态\n"
    "B站状态 · 查看动态推送用的 B 站登录，未登录时发扫码二维码"
)


def normalize_command(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lstrip("/")


def is_command(text: str) -> bool:
    return normalize_command(text) in COMMANDS


def subscribed(database, app_id: str, target_type: str, openid: str) -> list[str]:
    rows = database.execute(
        "SELECT source FROM feed_subscriptions WHERE bot_app_id = %s AND target_type = %s AND target_openid = %s",
        (app_id, target_type, openid),
    ).fetchall()
    return sorted((row["source"] for row in rows if row["source"] in SOURCES), key=list(SOURCES).index)


def subscribe(database, app_id: str, target_type: str, openid: str, sources: Iterable[str]) -> None:
    for source in sources:
        database.execute(
            "INSERT INTO feed_subscriptions (bot_app_id, target_type, target_openid, source) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (app_id, target_type, openid, source),
        )


def unsubscribe(database, app_id: str, target_type: str, openid: str, sources: Iterable[str]) -> None:
    for source in sources:
        database.execute(
            "DELETE FROM feed_subscriptions WHERE bot_app_id = %s AND target_type = %s "
            "AND target_openid = %s AND source = %s",
            (app_id, target_type, openid, source),
        )


def targets(database, app_id: str, source: str) -> list[tuple[str, str]]:
    rows = database.execute(
        "SELECT target_type, target_openid FROM feed_subscriptions WHERE bot_app_id = %s AND source = %s "
        "ORDER BY created_at, target_openid",
        (app_id, source),
    ).fetchall()
    return [(row["target_type"], row["target_openid"]) for row in rows]


def status_text(sources: list[str]) -> str:
    if not sources:
        return "当前没有订阅任何推送。\n" + USAGE
    return "当前订阅：" + "、".join(SOURCES[source] for source in sources) + "\n" + USAGE


def handle_command(database, app_id: str, target_type: str, openid: str, text: str) -> str | None:
    """处理订阅指令并返回回复文本；不是订阅指令时返回 None。"""
    command = COMMANDS.get(normalize_command(text))
    if command is None:
        return None
    if target_type not in TARGET_TYPES:
        raise ValueError("unknown target type")
    action, sources = command
    if action == "add":
        subscribe(database, app_id, target_type, openid, sources)
        names = "、".join(SOURCES[source] for source in sources)
        place = "本群" if target_type == "group" else "你"
        note = ""
        if BILI in sources and not bilibili.has_cookie(database):
            note = "\n（B 站还没登录，@我 发「B站状态」扫码登录后才会开始推送动态）"
        return f"已订阅：{names}。有新内容时会推送给{place}。{note}"
    if action == "remove":
        unsubscribe(database, app_id, target_type, openid, sources)
        remaining = subscribed(database, app_id, target_type, openid)
        names = "、".join(SOURCES[source] for source in sources)
        return f"已取消订阅：{names}。" + ("" if not remaining else "\n" + status_text(remaining))
    return status_text(subscribed(database, app_id, target_type, openid))


# ---------------------------------------------------------------- 抓取


@dataclass(frozen=True)
class Item:
    source: str
    id: str
    text: str
    link: str = ""
    published: datetime | None = None


def get_json(url: str, headers: dict | None = None, timeout: float = 10) -> dict:
    request = UrlRequest(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def plain_text(value: str) -> str:
    """公告正文是 HTML，标题里换行是字面量 \\n：统一转成单行纯文本。"""
    text = re.sub(r"<br\s*/?>|</p>|</div>", "\n", value or "", flags=re.IGNORECASE)
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\\n", "\n")
    lines = (re.sub(r"[ \t　]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def shorten(text: str, limit: int = SUMMARY_LIMIT) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def fetch_ak(fetch: Callable = get_json) -> list[Item]:
    data = fetch(AK_LIST_URL)
    if data.get("code") != 0:
        raise RuntimeError(f"bulletin list code {data.get('code')}")
    items = []
    for entry in (data.get("data") or {}).get("list") or []:
        cid = entry.get("cid")
        if not isinstance(cid, str) or not cid:
            continue
        published = None
        try:
            published = datetime.strptime(str(entry.get("displayTime")), "%Y-%m-%d").replace(tzinfo=CHINA)
        except ValueError:
            pass
        title = " ".join(plain_text(str(entry.get("title") or "")).splitlines())
        items.append(Item(AK, cid, title, published=published))
    return items


def ak_message(item: Item, fetch: Callable = get_json) -> str:
    """新公告再取一次详情，用完整标题和正文开头组成推送；详情取不到时退回列表标题。"""
    title, summary, link = item.text, "", ""
    try:
        detail = (fetch(AK_DETAIL_URL.format(cid=item.id)).get("data") or {})
        title = plain_text(str(detail.get("header") or "")).replace("\n", " ") or title
        summary = shorten(plain_text(str(detail.get("content") or "")).replace("\n", " "))
        link = str(detail.get("jumpLink") or "")
    except (HTTPError, URLError, TimeoutError, ValueError, AttributeError) as error:
        LOGGER.warning("Bulletin detail failed: %s", type(error).__name__)
    lines = ["【明日方舟公告】", title]
    if item.published:
        lines.append(item.published.strftime("%Y-%m-%d"))
    if summary:
        lines.append(summary)
    if links_enabled() and link.startswith("https://"):
        lines.append(link)
    return "\n".join(lines)


class BiliBlocked(RuntimeError):
    """B 站返回非 0 code（如 -352 风控、-101 未登录）或非 JSON 页面。"""


def bili_text(item: dict) -> str:
    modules = item.get("modules") or {}
    dynamic = modules.get("module_dynamic") or {}
    major = dynamic.get("major") or {}
    desc = ((dynamic.get("desc") or {}).get("text") or "").strip()
    kind = item.get("type")
    parts = []
    if archive := major.get("archive"):
        parts.append(f"发布了视频：{archive.get('title', '')}")
        if not desc:
            desc = archive.get("desc") or ""
    elif opus := major.get("opus"):
        if opus.get("title"):
            parts.append(opus["title"])
        desc = desc or ((opus.get("summary") or {}).get("text") or "")
    elif article := major.get("article"):
        parts.append(f"发布了专栏：{article.get('title', '')}")
        desc = desc or article.get("desc") or ""
    elif kind == "DYNAMIC_TYPE_LIVE_RCMD" or major.get("live_rcmd"):
        parts.append("开始直播了")
    elif kind == "DYNAMIC_TYPE_FORWARD":
        parts.append("转发了动态")
    if desc:
        parts.append(shorten(plain_text(desc).replace("\n", " ")))
    return "\n".join(part for part in parts if part) or "发布了新动态"


def fetch_bili(uid: str, cookie: str, fetch: Callable = get_json) -> list[Item]:
    headers = {
        "Cookie": cookie,
        "Referer": f"https://space.bilibili.com/{uid}/dynamic",
        "Origin": "https://space.bilibili.com",
    }
    try:
        data = fetch(BILI_FEED_URL.format(uid=uid), headers)
    except json.JSONDecodeError:
        raise BiliBlocked("non-json response") from None
    if data.get("code") != 0:
        raise BiliBlocked(f"code {data.get('code')}")
    items = []
    for entry in (data.get("data") or {}).get("items") or []:
        dynamic_id = entry.get("id_str")
        if not isinstance(dynamic_id, str) or not dynamic_id:
            continue
        author = (entry.get("modules") or {}).get("module_author") or {}
        published = None
        if isinstance(author.get("pub_ts"), (int, float)) or str(author.get("pub_ts", "")).isdigit():
            published = datetime.fromtimestamp(int(author["pub_ts"]), CHINA)
        items.append(Item(BILI, dynamic_id, bili_text(entry), f"https://t.bilibili.com/{dynamic_id}", published))
    return items


def bili_message(item: Item) -> str:
    lines = ["【明日方舟 B 站动态】", item.text]
    if item.published:
        lines.append(item.published.strftime("%Y-%m-%d %H:%M"))
    if links_enabled():
        lines.append(item.link)
    return "\n".join(lines)


def links_enabled() -> bool:
    return os.getenv("FEED_LINKS", "0").strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------- 去重与推送


def new_items(database, source: str, items: list[Item], now: datetime | None = None) -> list[Item]:
    """记下本次见到的条目，返回需要推送的新条目（按发布时间从旧到新）。"""
    if not items:
        return []
    first_run = database.execute(
        "SELECT 1 FROM feed_seen WHERE source = %s LIMIT 1", (source,),
    ).fetchone() is None
    ids = [item.id for item in items]
    placeholders = ", ".join(["%s"] * len(ids))
    known = {
        row["item_id"] for row in database.execute(
            f"SELECT item_id FROM feed_seen WHERE source = %s AND item_id IN ({placeholders})", (source, *ids),
        ).fetchall()
    }
    fresh = []
    for item in items:
        if item.id in known:
            continue
        database.execute(
            "INSERT INTO feed_seen (source, item_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (source, item.id),
        )
        known.add(item.id)
        fresh.append(item)
    if first_run:
        return []
    now = now or datetime.now(CHINA)
    fresh = [item for item in fresh if item.published is None or now - item.published <= MAX_AGE]
    return sorted(fresh, key=lambda item: item.published or now)


def deliver(client, database, app_id: str, source: str, content: str, sleep: Callable = time.sleep) -> int:
    sent = 0
    for target_type, openid in targets(database, app_id, source):
        try:
            if target_type == "group":
                client.send_group(openid, content)
            else:
                client.send_c2c(openid, content)
            sent += 1
        except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as error:
            # 群把机器人移出、用户关闭主动消息等都会失败；只记类型和状态码，不记 openid。
            LOGGER.warning("Push to %s failed: %s %s", target_type, type(error).__name__, getattr(error, "code", ""))
        sleep(SEND_GAP)
    return sent


@dataclass
class Poller:
    client: object
    app_id: str
    fetch: Callable = get_json
    sleep: Callable = time.sleep

    def run_ak(self, database) -> int:
        pushed = 0
        for item in new_items(database, AK, fetch_ak(self.fetch)):
            deliver(self.client, database, self.app_id, AK, ak_message(item, self.fetch), self.sleep)
            pushed += 1
        return pushed

    def run_bili(self, database, uid: str, cookie: str) -> int:
        pushed = 0
        for item in new_items(database, BILI, fetch_bili(uid, cookie, self.fetch)):
            deliver(self.client, database, self.app_id, BILI, bili_message(item), self.sleep)
            pushed += 1
        return pushed


def interval(name: str, default: int, floor: int = 30) -> int:
    try:
        return max(floor, int(os.getenv(name, default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Schedule:
    """按北京时间决定轮询间隔：白天密集、整点前后更密集、其余时间放慢。

    官方公告和动态多在整点发布，所以忙时段内每个整点前 2 分钟到整点后 5 分钟（:58–:05）用 peak 间隔。
    """

    peak: int
    busy: int
    idle: int
    busy_start: int = 10
    busy_end: int = 18

    def delay(self, now: datetime) -> float:
        now = now.astimezone(CHINA)
        hour, minute = now.hour, now.minute
        # :58 起算作下一个小时的整点窗口，所以 9:58 已经进入 10 点的密集时段。
        window_hour = (hour + 1) % 24 if minute >= 58 else hour
        busy = self.busy_start <= window_hour < self.busy_end
        if busy and (minute >= 58 or minute <= 5):
            chosen = self.peak
        else:
            chosen = self.busy if busy else self.idle
        # 不要一觉睡过下一个整点窗口的开头。
        until_window = ((58 - minute) % 60) * 60 - now.second
        if until_window > 0:
            chosen = min(chosen, until_window)
        return float(max(chosen, 1))


def parse_hours(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*", value or "")
    if not match or not 0 <= int(match[1]) < int(match[2]) <= 24:
        raise RuntimeError("FEED_BUSY_HOURS must look like 10-18")
    return int(match[1]), int(match[2])


def main():
    from .qqbot import BotConfig, QQClient

    logging.basicConfig(level=logging.INFO)
    config = BotConfig.from_env()
    poller = Poller(QQClient(config), config.app_id)
    start, end = parse_hours(os.getenv("FEED_BUSY_HOURS", "10-18"))
    ak_schedule = Schedule(
        peak=interval("FEED_AK_PEAK", 30), busy=interval("FEED_AK_INTERVAL", 120),
        idle=interval("FEED_AK_IDLE", 600), busy_start=start, busy_end=end,
    )
    # B 站请求太密容易触发风控，下限 60 秒。
    bili_schedule = Schedule(
        peak=interval("FEED_BILI_PEAK", 60, 60), busy=interval("FEED_BILI_INTERVAL", 180, 60),
        idle=interval("FEED_BILI_IDLE", 900, 60), busy_start=start, busy_end=end,
    )
    uid = os.getenv("FEED_BILI_UID", "161775300").strip()
    if not uid.isdigit():
        raise RuntimeError("FEED_BILI_UID must be numeric")

    stop = Event()
    for interrupt in (signal.SIGINT, signal.SIGTERM):
        signal.signal(interrupt, lambda *_: stop.set())
    next_ak = next_bili = 0.0
    bili_failures = 0
    warned_no_cookie = False
    while not stop.is_set():
        now = time.monotonic()
        try:
            with connect() as database:
                if now >= next_ak:
                    next_ak = now + ak_schedule.delay(datetime.now(CHINA))
                    try:
                        if pushed := poller.run_ak(database):
                            LOGGER.info("Pushed %d new bulletin(s)", pushed)
                    except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as error:
                        LOGGER.warning("Bulletin poll failed: %s", type(error).__name__)
                if now >= next_bili:
                    # 每轮重新读：机器人扫码登录后不用重启推送进程。
                    try:
                        cookie = bilibili.stored_cookie(database)
                    except CredentialStorageError:
                        LOGGER.exception("Could not decrypt Bilibili cookie")
                        cookie = ""
                    if not cookie:
                        if not warned_no_cookie:
                            LOGGER.warning("No Bilibili cookie yet; send「B站状态」to the bot to log in")
                            warned_no_cookie = True
                        next_bili = now + 60
                    else:
                        warned_no_cookie = False
                        try:
                            if pushed := poller.run_bili(database, uid, cookie):
                                LOGGER.info("Pushed %d new Bilibili dynamic(s)", pushed)
                            bili_failures = 0
                        except (BiliBlocked, HTTPError, URLError, TimeoutError, ValueError) as error:
                            # 风控时按 2 的幂退避，最长 30 分钟；Cookie 失效（-101）时 @机器人「B站状态」重新扫码。
                            bili_failures += 1
                            LOGGER.warning("Bilibili poll failed (%d in a row): %s %s", bili_failures,
                                           type(error).__name__, error if isinstance(error, BiliBlocked) else "")
                        regular = bili_schedule.delay(datetime.now(CHINA))
                        backoff = min(bili_schedule.busy * 2 ** min(bili_failures, 4), 1800)
                        next_bili = now + (max(regular, backoff) if bili_failures else regular)
        except StorageUnavailable:
            LOGGER.warning("Database connection interrupted; retrying")
        stop.wait(max(1.0, min(next_ak, next_bili) - time.monotonic()))


if __name__ == "__main__":
    main()
