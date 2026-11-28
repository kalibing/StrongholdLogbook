"""QQ 推送：明日方舟游戏公告与 B 站官号动态。

站点管理员在网页配置推送群。轮询进程发现新条目后通过 QQ 主动消息接口发给相应的群。

数据来源：
- 游戏公告：https://ak-webview.hypergryph.com/api/game/bulletinList?target=IOS，
  详情 /api/game/bulletin/{cid}；公开接口，无需登录。
- B 站动态：https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?host_mid={uid}；
  B 站会拦截未登录的请求，需要在 BILIBILI_COOKIE 里填一个 B 站账号的 Cookie，未配置时不轮询 B 站。

去重：已见过的条目记在 feed_seen 表。某个来源第一次运行（表里还没有记录）时只记录当前列表、不推送，
避免一上线就把历史公告全部发一遍。先记录再发送：进程中途退出时宁可漏发一条，也不重复刷屏。

环境变量：
- 轮询按北京时间调度（见 Schedule）：FEED_BUSY_HOURS 为密集时段，默认 10-18；
  游戏公告 FEED_AK_PEAK / FEED_AK_INTERVAL / FEED_AK_IDLE 默认 30 / 120 / 1800 秒，
  B 站 FEED_BILI_PEAK / FEED_BILI_INTERVAL / FEED_BILI_IDLE 默认 60 / 180 / 3600 秒
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
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request as UrlRequest, urlopen

from . import bilibili
from .credentials import CredentialStorageError
from .errors import StorageUnavailable
from .storage import connect

LOGGER = logging.getLogger(__name__)

AK = "ak"
BILI = "bili"
SOURCES = {AK: "明日方舟游戏公告", BILI: "明日方舟 B 站动态"}

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


# ---------------------------------------------------------------- 推送群


def observe_group(database, app_id: str, openid: str) -> None:
    database.execute("""
        INSERT INTO qq_feed_groups (bot_app_id, group_openid, updated_at)
        VALUES (%s, %s, now())
        ON CONFLICT (bot_app_id, group_openid) DO UPDATE SET updated_at = excluded.updated_at
    """, (app_id, openid))


def groups(database, app_id: str) -> list[dict]:
    rows = database.execute("""
        SELECT group_openid, group_number, updated_at FROM qq_feed_groups
        WHERE bot_app_id = %s ORDER BY updated_at DESC, group_openid
    """, (app_id,)).fetchall()
    by_group = {row["group_openid"]: {**row, "sources": []} for row in rows}
    for row in database.execute("""
        SELECT target_openid, source FROM feed_subscriptions
        WHERE bot_app_id = %s AND target_type = 'group' ORDER BY source
    """, (app_id,)).fetchall():
        if row["target_openid"] in by_group and row["source"] in SOURCES:
            by_group[row["target_openid"]]["sources"].append(row["source"])
    return list(by_group.values())


def configure_group(database, app_id: str, openid: str, group_number: str | None, sources: list[str]) -> bool:
    with database.transaction():
        group = database.execute("""
            UPDATE qq_feed_groups SET group_number = %s
            WHERE bot_app_id = %s AND group_openid = %s RETURNING group_openid
        """, (group_number, app_id, openid)).fetchone()
        if group is None:
            return False
        for source in SOURCES:
            if source in sources:
                database.execute("""
                    INSERT INTO feed_subscriptions (bot_app_id, target_type, target_openid, source)
                    VALUES (%s, 'group', %s, %s) ON CONFLICT DO NOTHING
                """, (app_id, openid, source))
            else:
                database.execute("""
                    DELETE FROM feed_subscriptions
                    WHERE bot_app_id = %s AND target_type = 'group' AND target_openid = %s AND source = %s
                """, (app_id, openid, source))
    return True


def targets(database, app_id: str, source: str) -> list[str]:
    rows = database.execute("""
        SELECT target_openid FROM feed_subscriptions
        WHERE bot_app_id = %s AND target_type = 'group' AND source = %s ORDER BY created_at, target_openid
    """, (app_id, source)).fetchall()
    return [row["target_openid"] for row in rows]


# ---------------------------------------------------------------- 抓取


@dataclass(frozen=True)
class FeedImage:
    url: str
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class Item:
    source: str
    id: str
    text: str
    link: str = ""
    published: datetime | None = None
    images: tuple[FeedImage, ...] = ()


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
    desc = (dynamic.get("desc") or {}).get("text") or ""
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
        parts.append(desc.replace("\r\n", "\n").replace("\r", "\n"))
    return "\n".join(part for part in parts if part) or "发布了新动态"


def bili_images(item: dict) -> tuple[FeedImage, ...]:
    """按动态顺序收集配图与封面，也处理转发的原动态。"""
    images: dict[str, FeedImage] = {}
    for entry in (item, item.get("orig")):
        if not isinstance(entry, dict):
            continue
        dynamic = (entry.get("modules") or {}).get("module_dynamic") or {}
        major = dynamic.get("major") or {}
        pictures = (
            *((major.get("opus") or {}).get("pics") or []),
            *((major.get("draw") or {}).get("items") or []),
            *((major.get("article") or {}).get("covers") or []),
            (major.get("archive") or {}).get("cover"),
        )
        for picture in pictures:
            value = (picture.get("url") or picture.get("src")) if isinstance(picture, dict) else picture
            if not isinstance(value, str):
                continue
            try:
                url = urlsplit("https:" + value if value.startswith("//") else value)
            except ValueError:
                continue
            if (url.scheme in {"http", "https"} and url.path
                    and re.fullmatch(r"i[0-9]+\.hdslb\.com", url.netloc, re.IGNORECASE)):
                address = urlunsplit(url._replace(scheme="https", fragment=""))
                metadata = picture if isinstance(picture, dict) else {}
                width = metadata.get("width") or metadata.get("img_width")
                height = metadata.get("height") or metadata.get("img_height")
                if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
                    old_image = images.get(address)
                    if old_image is None or old_image.width is None:
                        images[address] = FeedImage(address, width, height)
                else:
                    images.setdefault(address, FeedImage(address))
    return tuple(images.values())


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
        items.append(Item(BILI, dynamic_id, bili_text(entry), f"https://t.bilibili.com/{dynamic_id}", published, bili_images(entry)))
    return items


def bili_message(item: Item) -> tuple[str, str]:
    footer = []
    if item.published:
        footer.append(item.published.strftime("%Y-%m-%d %H:%M"))
    if links_enabled():
        footer.append(item.link)
    return f"【明日方舟 B 站动态】\n{item.text}", "\n".join(footer)


def bili_markdown(content: str, images: tuple[FeedImage, ...], footer: str) -> str:
    # QQ Markdown keeps paragraph breaks and collapses consecutive empty lines.
    lines = [
        re.sub(r"([\\`*_{}\[\]<>#+!~|&.\-])", r"\\\1", line) if line.strip() else "\u200b"
        for line in content.split("\n")
    ]
    for index, image in enumerate(images, 1):
        label = f"配图 {index}"
        if image.width and image.height:
            width = min(600, image.width)
            height = max(1, round(image.height * width / image.width))
            label += f" #{width}px #{height}px"
        url = quote(image.url, safe=":/?&=%@+,$#;[]!~*'-_")
        lines.append(f"![{label}]({url})")
    if footer:
        lines.extend(footer.split("\n"))
    return "\n\n".join(lines)


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


SEND_ERRORS = (HTTPError, URLError, TimeoutError, RuntimeError, ValueError)


def deliver(client, database, app_id: str, source: str, content: str, sleep: Callable = time.sleep,
            *, markdown: bool = False) -> int:
    send = client.send_group_markdown if markdown else client.send_group
    sent = 0
    for openid in targets(database, app_id, source):
        try:
            send(openid, content)
            sent += 1
        except SEND_ERRORS as error:
            # 只记发送错误的类型和状态码，不记群 openid。
            LOGGER.warning("Group push failed: %s %s", type(error).__name__, getattr(error, "code", ""))
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
            content, footer = bili_message(item)
            if item.images:
                content = bili_markdown(content, item.images, footer)
            elif footer:
                content = f"{content}\n{footer}"
            deliver(self.client, database, self.app_id, BILI, content, self.sleep, markdown=bool(item.images))
            pushed += 1
        return pushed


POLL_ERRORS = (HTTPError, URLError, TimeoutError, RuntimeError, ValueError)


def poll_ak(poller: Poller, database) -> None:
    """跑一轮公告轮询；除了数据库中断，任何异常都只记日志，不让推送进程退出。"""
    try:
        if pushed := poller.run_ak(database):
            LOGGER.info("Pushed %d new bulletin(s)", pushed)
    except StorageUnavailable:
        raise
    except POLL_ERRORS as error:
        LOGGER.warning("Bulletin poll failed: %s", type(error).__name__)
    except Exception:  # noqa: BLE001 - 接口返回结构变化等意外错误，下一轮再试
        LOGGER.exception("Unexpected bulletin poll error")


def poll_bili(poller: Poller, database, uid: str, cookie: str) -> bool:
    """跑一轮 B 站轮询，成功返回 True；失败只记日志（调用方据此退避），数据库中断照常抛出。"""
    try:
        if pushed := poller.run_bili(database, uid, cookie):
            LOGGER.info("Pushed %d new Bilibili dynamic(s)", pushed)
        return True
    except StorageUnavailable:
        raise
    except (BiliBlocked, *POLL_ERRORS) as error:
        # Cookie 失效（-101）时管理员在私聊发「B站状态」重新扫码。
        LOGGER.warning("Bilibili poll failed: %s %s", type(error).__name__,
                       error if isinstance(error, BiliBlocked) else "")
    except Exception:  # noqa: BLE001 - 接口返回结构变化等意外错误，按失败退避
        LOGGER.exception("Unexpected Bilibili poll error")
    return False


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
        # 只为下一个忙时整点提前唤醒。闲时不需要每小时 :58 都查询。
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1 if minute < 58 else 2)
        if next_hour.hour >= self.busy_end:
            next_hour = next_hour.replace(hour=self.busy_start) + timedelta(days=1)
        elif next_hour.hour < self.busy_start:
            next_hour = next_hour.replace(hour=self.busy_start)
        until_window = (next_hour - timedelta(minutes=2) - now).total_seconds()
        return max(1.0, min(chosen, until_window))


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
        idle=interval("FEED_AK_IDLE", 1800), busy_start=start, busy_end=end,
    )
    # B 站请求太密容易触发风控，下限 60 秒。
    bili_schedule = Schedule(
        peak=interval("FEED_BILI_PEAK", 60, 60), busy=interval("FEED_BILI_INTERVAL", 180, 60),
        idle=interval("FEED_BILI_IDLE", 3600, 60), busy_start=start, busy_end=end,
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
                    poll_ak(poller, database)
                if now >= next_bili:
                    # 每轮重新读：机器人扫码登录后不用重启推送进程。
                    try:
                        cookie = bilibili.stored_cookie(database)
                    except CredentialStorageError:
                        LOGGER.exception("Could not decrypt Bilibili cookie")
                        cookie = ""
                    if not cookie:
                        if not warned_no_cookie:
                            LOGGER.warning("No Bilibili cookie yet; ask a site administrator to message the bot「B站状态」")
                            warned_no_cookie = True
                        next_bili = now + 60
                    else:
                        warned_no_cookie = False
                        # 失败时按 2 的幂退避，最长 30 分钟。
                        bili_failures = 0 if poll_bili(poller, database, uid, cookie) else bili_failures + 1
                        if bili_failures > 1:
                            LOGGER.warning("Bilibili poll failed %d times in a row", bili_failures)
                        regular = bili_schedule.delay(datetime.now(CHINA))
                        backoff = min(bili_schedule.busy * 2 ** min(bili_failures, 4), 1800)
                        next_bili = now + (max(regular, backoff) if bili_failures else regular)
        except StorageUnavailable:
            LOGGER.warning("Database connection interrupted; retrying")
        stop.wait(max(1.0, min(next_ak, next_bili) - time.monotonic()))


if __name__ == "__main__":
    main()
