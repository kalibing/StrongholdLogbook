"""每日战报与 QQ 近期战绩的 PNG 渲染。

取数口径与网页「昨日战报」一致：北京时间按开局时间归到当天，默认排除疑似直接退出。
"""

import io
import os
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from threading import Lock

from PIL import Image, ImageChops, ImageDraw, ImageFont

from . import bands, daily_review, stats
from .bond_names import BOND_NAMES
from .records import CHINA, Filters

WIDTH = 1080
PAD = 40

# 与 frontend/src/style.css 的默认深色主题保持一致（卡片主要用下面的 RECORD_* 配色）。
BG = "#080b0c"
PANEL = "#0f1415"
INSET = "#0b0f10"
LINE = "#1f2829"
TEXT = "#ecf0ee"
MUTED = "#8d9996"
ACCENT = "#e1ea8f"
WIN = "#b9e8b4"
LOSS = "#ffb3ba"
CHART_AVERAGE = "#7bc9f1"
RADIUS = 2
PALETTE = ["#628ef5", "#36bda3", "#a486ef", "#f5b552", "#45a9d1", "#eb7f9c", "#8593ae"]
# 所有战绩卡片统一使用：QQ 缩略图需要更亮的面板和文字，保留网页主题的强调色与胜负色。
RECORD_BG = "#172025"
RECORD_PANEL = "#27363b"
RECORD_RAISED = "#33474d"
RECORD_INSET = "#1e2b30"
RECORD_LINE = "#566c72"
RECORD_MUTED = "#c2d0cf"
RECORD_LOSS_BAR = "#8a5560"  # 胜率条的负场部分：比 LOSS 暗，避免整列红色抢眼
RECORD_GAP = 26
RECORD_PNG_CACHE_SIZE = 24
_record_pngs: OrderedDict[bytes, bytes] = OrderedDict()
_record_png_lock = Lock()
WEEKDAYS = "一二三四五六日"
MAX_ROWS = 12
BACKEND_DIR = Path(__file__).resolve().parents[1]
ART = BACKEND_DIR / "art"
if not ART.is_dir():
    ART = BACKEND_DIR.parent / "frontend" / "public" / "art"
BOND_ICONS = {name: f"bond-{key}.png" for key, name in BOND_NAMES.items()}
MAJOR_BONDS = ("炎", "乌萨斯", "维多利亚", "伊比利亚", "阿戈尔", "莱塔尼亚", "卡西米尔",
               "萨尔贡", "叙拉古", "谢拉格", "哥伦比亚", "玻利瓦尔", "雷姆必拓", "米诺斯")

FONT_CANDIDATES = {
    False: [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",  # RHEL / OpenCloudOS / Fedora
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ],
    True: [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",  # RHEL / OpenCloudOS / Fedora
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ],
}


class CardFontError(RuntimeError):
    """找不到可显示中文的字体。"""


# Noto Sans CJK 的 .ttc 里 face 0 是日文字形（JP），简体中文是第 3 个 face（index 2）。
# 不指定 index 时 PIL 取 face 0，简繁字体混用会让人一眼看出「字不对」。
NOTO_SC_FACE = 2


def _face_index(path: str, override: str) -> int:
    if override.strip():
        try:
            return max(0, int(override))
        except ValueError:
            return 0
    name = os.path.basename(path).lower()
    if name.startswith("notosanscjk") and name.endswith(".ttc"):
        return NOTO_SC_FACE
    return 0


@lru_cache(maxsize=2)
def font_path(bold):
    override = os.getenv("LOGBOOK_CARD_FONT_BOLD" if bold else "LOGBOOK_CARD_FONT", "").strip()
    for path in ([override] if override else []) + FONT_CANDIDATES[bold]:
        if path and os.path.exists(path):
            return path
    if bold:
        return font_path(False)
    raise CardFontError("服务器缺少中文字体，请安装 Noto Sans CJK 或设置 LOGBOOK_CARD_FONT")


@lru_cache(maxsize=64)
def font(size, bold=False):
    path = font_path(bold)
    index = _face_index(path, os.getenv("LOGBOOK_CARD_FONT_INDEX", ""))
    return ImageFont.truetype(path, size, index=index)


@dataclass
class Card:
    day: date
    username: str
    matches: list
    excluded: int
    trophy_change: int | None
    recap: dict
    trophy_icon: str = "trophy_level1_icon.png"
    # 「最近 N 局战绩」这类非按天统计的卡片：标题与「昨日/当天」措辞都要覆盖。
    title: str | None = None
    word: str | None = None

    @property
    def wins(self):
        return sum(row["result"] == "win" for row in self.matches)

    @property
    def is_yesterday(self):
        return self.day == datetime.now(CHINA).date() - timedelta(days=1)

    @property
    def day_word(self):
        """标题与文案用「昨日」还是「当天」：传了别的日期时不该写成昨日。"""
        return self.word or ("昨日" if self.is_yesterday else "当天")


def build(rows, excluded, day, username, *, badge=None, trophy_total=None):
    """rows：当天已排除疑似直接退出的对局，按开局时间倒序。"""
    trophies = [row["trophies"] for row in rows if row.get("trophies") is not None]
    badge = badge or {}
    valid_icons = {f"trophy_level{level}_icon" for level in range(1, 9)}
    badge_icon = badge.get("icon")
    if badge_icon not in valid_icons:
        level = badge.get("level")
        if level is None:
            level = sum((trophy_total or 0) >= threshold for threshold in (0, 10, 30, 60, 100, 150, 200, 300))
        badge_icon = f"trophy_level{level}_icon"
        if badge_icon not in valid_icons:
            badge_icon = "trophy_level1_icon"
    return Card(day=day, username=username, matches=list(rows), excluded=excluded,
                trophy_change=sum(trophies) if trophies else None, recap=daily_review.summarize(rows),
                trophy_icon=f"{badge_icon}.png")


def load(database, user, day, *, group=False):
    user_id = user["id"]
    where, params = Filters(start=day, end=day, include_exits=True).sql(user_id)
    rows = database.execute(
        "SELECT id, played_at, result, play, difficulty, strategy, rounds, kills, coins, trophies, "
        f"duration_seconds, suspected_exit, bonds, bosses FROM matches WHERE {where} ORDER BY played_at DESC, id DESC",
        params,
    ).fetchall()
    profile = database.execute("SELECT nickname FROM skland_profiles WHERE user_id = %s", (user_id,)).fetchone()
    nickname = profile["nickname"] if profile else None
    display_name = nickname or ("QQ 群成员" if group else user["username"])
    trophies = trophy_summary(database, user_id)
    total = trophies["trophy_total"]
    kept = [row for row in rows if not row["suspected_exit"]]
    return build(kept, len(rows) - len(kept), day, display_name, badge=trophies["trophy_badge"],
                 trophy_total=total["total"] if total else None)


RECORD_LIMIT = 10


def load_recent(database, user, *, limit: int = RECORD_LIMIT, group: bool = False):
    """「最近 N 局战绩」卡片：跨日期取最近的有效对局，复用战报卡渲染（标题与措辞另给）。"""
    user_id = user["id"]
    rows = list(database.execute(
        "SELECT id, played_at, result, play, difficulty, strategy, rounds, kills, coins, trophies, "
        "duration_seconds, suspected_exit, bonds, bosses FROM matches "
        "WHERE user_id = %s AND NOT suspected_exit ORDER BY played_at DESC, id DESC LIMIT %s",
        (user_id, limit),
    ).fetchall())
    profile = database.execute("SELECT nickname FROM skland_profiles WHERE user_id = %s", (user_id,)).fetchone()
    nickname = profile["nickname"] if profile else None
    display_name = nickname or ("QQ 群成员" if group else user["username"])
    trophies = trophy_summary(database, user_id)
    total = trophies["trophy_total"]
    card = build(rows, 0, datetime.now(CHINA).date(), display_name, badge=trophies["trophy_badge"],
                 trophy_total=total["total"] if total else None)
    card.title = f"最近 {len(rows)} 局战绩"
    card.word = "近期"
    return card


def record_text(database, user) -> str:
    """群里「战绩」指令的文字回复：最近 10 局有效对局（排除疑似直接退出）的胜率、走势、常用盟约与策略。"""
    user_id = user["id"]
    rows = database.execute(
        "SELECT id, played_at, result, strategy, rounds, kills, coins, trophies, suspected_exit, bonds, operators "
        "FROM matches WHERE user_id = %s AND NOT suspected_exit ORDER BY played_at DESC, id DESC LIMIT %s",
        (user_id, RECORD_LIMIT),
    ).fetchall()
    profile = database.execute("SELECT nickname FROM skland_profiles WHERE user_id = %s", (user_id,)).fetchone()
    name = (profile["nickname"] if profile else None) or "你"
    if not rows:
        return f"{name}还没有有效的作战记录。"
    rows.reverse()  # 旧 → 新，走势从左往右读
    summary = stats.overview(rows, 0, "recent")
    wins, matches = summary["wins"], summary["matches"]
    lines = [
        f"{name} · 最近 {matches} 局战绩",
        f"胜率 {wins / matches:.0%}（{wins} 胜 {matches - wins} 负）",
        "走势 " + "".join("胜" if result == "win" else "负" for result in summary["recent_results"]),
    ]
    if summary["bonds"]:
        lines.append("常用盟约 " + "、".join(f"{bond['name']} {bond['count']} 局" for bond in summary["bonds"][:3]))
    if summary["strategies"]:
        lines.append("常用策略 " + "、".join(
            f"{entry['name']} {entry['count']} 局" for entry in summary["strategies"][:3]))
    extras = []
    if summary["max_layers"]:
        extras.append(f"单局最高盟约 {summary['max_layers']} 层")
    if summary["average_coins"] is not None:
        extras.append(f"场均金币 {fmt(summary['average_coins'])}")
    if extras:
        lines.append(" · ".join(extras))
    total = trophy_summary(database, user_id)["trophy_total"]
    if total:
        lines.append(f"奖杯总数 {fmt(total['total'])}")
    return "\n".join(lines)


@dataclass
class StrategyCard:
    """「胜率」卡片：全部时间有效对局按开局策略统计。entries 来自 stats.strategy_stats。"""
    username: str
    entries: list
    missing: int = 0  # 没记录策略的有效对局数，不计入统计

    @property
    def matches(self):
        return sum(entry["count"] for entry in self.entries)

    @property
    def wins(self):
        return sum(entry["wins"] for entry in self.entries)


def load_strategies(database, user, *, group: bool = False) -> StrategyCard:
    """记录里的 strategy 可能是 band id、分队干员名或策略名，先统一换成策略名再合并统计；排除疑似直接退出。"""
    user_id = user["id"]
    rows = database.execute(
        "SELECT result, strategy FROM matches WHERE user_id = %s AND NOT suspected_exit", (user_id,),
    ).fetchall()
    profile = database.execute("SELECT nickname FROM skland_profiles WHERE user_id = %s", (user_id,)).fetchone()
    nickname = profile["nickname"] if profile else None
    resolved = [{"result": row["result"], "strategy": bands.resolve(row["strategy"])[1]} for row in rows]
    entries = stats.strategy_stats(resolved)
    counted = sum(entry["count"] for entry in entries)
    return StrategyCard(nickname or ("QQ 群成员" if group else user["username"]), entries, len(rows) - counted)


def strategy_text(card: StrategyCard) -> str:
    """「胜率」卡片的文字版：服务器缺中文字体画不了图时使用。"""
    matches, wins = card.matches, card.wins
    lines = [
        f"{card.username} · 全部策略胜率",
        f"共 {matches} 局，{wins} 胜 {matches - wins} 负，总胜率 {wins / matches:.0%}",
    ]
    lines += [
        f"{entry['name']}：{entry['win_rate']:.0%}（{entry['wins']} 胜 {entry['count'] - entry['wins']} 负）"
        for entry in card.entries
    ]
    if card.missing:
        lines.append(f"另有 {card.missing} 局未记录策略，未计入。")
    return "\n".join(lines)


def trophy_summary(database, user_id) -> dict:
    """奖杯总数取最新返回的数据：成就档案快照与最近一局的「对局后奖杯」谁更新用谁，都没有再累加对局增减。"""
    link = database.execute("SELECT payload, fetched_at FROM achv_links WHERE user_id = %s", (user_id,)).fetchone()
    latest = database.execute(
        "SELECT played_at, duration_seconds, trophy_after FROM matches "
        "WHERE user_id = %s AND trophy_after IS NOT NULL ORDER BY played_at DESC, id DESC LIMIT 1", (user_id,),
    ).fetchone()
    payload = (link["payload"] if link else None) or {}
    trophy = payload.get("trophy")
    badge = {"icon": trophy.get("icon"), "level": trophy.get("level")} if trophy else None
    profile = trophy.get("total") if trophy else None
    # 对局记的是开局时间，奖杯在结算时才变，按结束时间和档案的拉取时间比较。
    ended = latest["played_at"] + timedelta(seconds=latest["duration_seconds"] or 0) if latest else None
    if latest and (profile is None or ended > link["fetched_at"]):
        total = {"total": latest["trophy_after"], "source": "match"}
    elif profile is not None:
        total = {"total": profile, "source": "profile"}
    else:
        recorded = database.execute(
            "SELECT SUM(trophies) AS total FROM matches WHERE user_id = %s", (user_id,),
        ).fetchone()["total"]
        total = {"total": max(0, int(recorded)), "source": "matches"} if recorded is not None else None
    return {"trophy_badge": badge, "trophy_total": total}


# ---------------------------------------------------------------- 绘图小工具

def fmt(value, digits=1):
    if value is None:
        return "—"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.{digits}f}"
    return f"{int(value):,}"


def compact_number(value):
    for scale, unit in ((100_000_000, "亿"), (10_000, "万")):
        if value >= scale:
            return f"{fmt(value / scale)}{unit}"
    return fmt(value)


def ellipsize(draw, text, width, face):
    if draw.textlength(text, font=face) <= width:
        return text
    while text and draw.textlength(text + "…", font=face) > width:
        text = text[:-1]
    return text + "…"


@lru_cache(maxsize=128)
def icon(filename, size):
    if filename is None:
        return None
    try:
        with Image.open(ART / filename) as source:
            result = source.convert("RGBA")
    except OSError:
        return None
    result.thumbnail((size, size), Image.Resampling.LANCZOS)
    return result


def text_middle(draw, y, face):
    """用 anchor="lm" 在 y 处画字时，汉字可见部分的垂直中心（字体的 middle 与字形中心并不重合）。"""
    _, top, _, bottom = draw.textbbox((0, y), "国", font=face, anchor="lm")
    return (top + bottom) / 2


def paste_icon(image, filename, x, cy, size, *, slot=None, gap=8):
    """按图标的可见边缘贴图：垂直中心对准 cy，左边缘贴着 x。

    给了 slot 时在 [x, x + slot] 内水平居中，返回固定的 slot + gap，让同一列的文字对齐；
    否则返回可见宽度 + gap。没有图标返回 0。
    """
    art, bounds = visible_icon(filename, size)
    if art is None or bounds is None:
        return 0
    left = x +((slot - (bounds[2] - bounds[0])) / 2 if slot else 0)
    image.paste(art, (round(left - bounds[0]), round(cy - (bounds[1] + bounds[3]) / 2)), art)
    return (slot if slot else bounds[2] - bounds[0]) + gap


@lru_cache(maxsize=128)
def visible_icon(filename, size):
    art = icon(filename, size)
    if art is None:
        return None, None
    alpha = art.getchannel("A")
    # 光晕和倒影保留在原图里，以主体的可见边缘计算对齐位置。
    bounds = alpha.point(lambda value: 255 if value >= 64 else 0).getbbox() or alpha.getbbox()
    return art, bounds


def draw_icon_value(image, draw, center, value, face, color, width, filename, icon_size):
    cx, cy = center
    art, bounds = visible_icon(filename, icon_size)
    icon_width = bounds[2] - bounds[0] + 8 if bounds else 0
    value = ellipsize(draw, value, width - icon_width, face)
    x0, y0, x1, y1 = draw.textbbox((0, 0), value, font=face, anchor="lt")
    left = cx - (icon_width + x1 - x0) / 2
    if bounds:
        icon_x = round(left - bounds[0])
        icon_y = round(cy - (bounds[1] + bounds[3]) / 2)
        image.paste(art, (icon_x, icon_y), art)
    draw.text((left + icon_width - x0, cy - (y0 + y1) / 2), value,
              font=face, fill=color, anchor="lt")


def ring(image, center, diameter, segments, *, background=RECORD_PANEL):
    segments = [(value, color) for value, color in segments if value > 0]
    total = sum(value for value, _ in segments)
    pixels = diameter * 3
    canvas = Image.new("RGB", (pixels, pixels), background)
    draw = ImageDraw.Draw(canvas)
    outer = (0, 0, pixels - 1, pixels - 1)
    width = round(pixels * (1 - 68 / 88) / 2)
    cumulative = 0
    for value, color in segments:
        start = -90 + 360 * cumulative / total
        cumulative += value
        end = -90 + 360 * cumulative / total
        gap = min(0.8, (end - start) / 4) if len(segments) > 1 else 0
        draw.arc(outer, start + gap, end - gap, fill=color, width=width)
    x, y = center
    image.paste(canvas.resize((diameter, diameter), Image.Resampling.LANCZOS),
                (x - diameter // 2, y - diameter // 2))


def record_panel(draw, top, height, title=None, note=None, *, left=PAD, right=WIDTH - PAD, fill=RECORD_PANEL):
    draw.rounded_rectangle((left, top, right, top + height), radius=RADIUS, fill=fill, outline=RECORD_LINE, width=2)
    if title:
        draw.rectangle((left + 24, top + 25, left + 28, top + 49), fill=ACCENT)
        draw.text((left + 40, top + 37), title, font=font(29, True), fill=TEXT, anchor="lm")
        if note:
            draw.text((right - 24, top + 37), note, font=font(20), fill=RECORD_MUTED, anchor="rm")
        draw.line((left + 24, top + 62, right - 24, top + 62), fill=RECORD_LINE)
    return top + 74


def chip(draw, x, y, win):
    color = WIN if win else LOSS
    draw.rounded_rectangle((x, y, x + 36, y + 30), radius=RADIUS, fill=INSET, outline=color)
    draw.text((x + 18, y + 15), "胜" if win else "负", font=font(18, True), fill=color, anchor="mm")


# ---------------------------------------------------------------- 各区块

def header(draw, top, card):
    """页头：账号名与标题；日报卡多一行日期（有疑似直接退出时一并说明）。"""
    subtitle = None
    if not card.title:
        subtitle = f"{card.day.isoformat()}  星期{WEEKDAYS[card.day.weekday()]}"
        if card.excluded and card.matches:
            subtitle += f"　·　已排除 {card.excluded} 局疑似直接退出"
    height = 142 + (38 if subtitle else 0)
    left = PAD + 36
    record_panel(draw, top, height, fill=RECORD_RAISED)
    draw.rectangle((PAD + 16, top + 26, PAD + 20, top + height - 26), fill=ACCENT)
    face = font(22, True)
    heading = ellipsize(draw, f"卫戍协议  /  {card.username}", WIDTH - 2 * PAD - 64, face)
    draw.text((left, top + 37), heading, font=face, fill=ACCENT, anchor="lm")
    title = card.title or ("昨日战报" if card.is_yesterday else "每日战报")
    draw.text((left, top + 92), title, font=font(51, True), fill=TEXT, anchor="lm")
    if subtitle:
        draw.text((left, top + 140), subtitle, font=font(22), fill=RECORD_MUTED, anchor="lm")
    return top + height + RECORD_GAP


def highlights(image, draw, top, card):
    recap, rows = card.recap, card.matches
    peak = stats.peak(rows)
    kills = [row["kills"] for row in rows if row["kills"] is not None]
    coins = [row["coins"] for row in rows if row.get("coins") is not None]
    seconds = recap.get("total_duration_seconds")
    duration = "—" if seconds is None else (f"{seconds // 3600} 小时 {seconds // 60 % 60} 分" if seconds >= 3600 else f"{seconds // 60} 分")
    peak_names = peak["names"] if peak else []
    peak_icon = next((name for name in MAJOR_BONDS if name in peak_names), next(iter(peak_names), ""))
    peak_label = peak_icon if card.title else "、".join(peak_names)
    cells = [
        ("单局最高盟约总层数", f"{fmt(max(map(stats.bond_total, rows), default=None))} 层", "", "metric-bond.png"),
        ("单项最高盟约", f"{fmt(peak['layers'])} 层" if peak else "—", peak_label, BOND_ICONS.get(peak_icon)),
        ("场均击杀", fmt(sum(kills) / len(kills) if kills else None), "", None),
        ("金币总花费", fmt(sum(coins) if coins else None), "", "metric-funds.png"),
        ("最长连胜", f"{fmt(recap.get('longest_win_streak'))} 局", "", None),
        ("游玩时长", duration, "", None),
    ]
    return highlight_grid(image, draw, top, f"{card.day_word}亮点", cells)


def highlight_grid(image, draw, top, title, cells, columns=3):
    """带边框的数据格：cells 为 (标签, 数值, 副标题, 图标[, 数值颜色])。"""
    row_height = 112
    height = 74 + -(-len(cells) // columns) * row_height + 16
    body = record_panel(draw, top, height, title)
    cell_width = (WIDTH - 2 * (PAD + 24) - (columns - 1) * 14) / columns
    label_face, value_face = font(20), font(32, True)
    for index, (label, value, sub, filename, *color) in enumerate(cells):
        x = PAD + 24 + (index % columns) * (cell_width + 14)
        y = body + (index // columns) * row_height
        center = x + cell_width / 2
        draw.rounded_rectangle((x, y, x + cell_width, y + row_height - 10), radius=RADIUS,
                               fill=RECORD_RAISED, outline=RECORD_LINE)
        draw.text((center, y + 23), label, font=label_face, fill=RECORD_MUTED, anchor="mm")
        # 策略图标是干员头像，细节多，比盟约 / 金币这类单色图标画大一点才看得清。
        icon_size = 38 if filename and filename.startswith("strategy-") else 28
        draw_icon_value(image, draw, (center, y + 57 if sub else y + 62), value, value_face,
                        color[0] if color else TEXT, cell_width - 28, filename, icon_size)
        if sub:
            sub = ellipsize(draw, sub, cell_width - 28, label_face)
            draw.text((center, y + 86), sub, font=label_face, fill=RECORD_MUTED, anchor="mm")
    return top + height + RECORD_GAP


def shown_bonds(layers):
    if len(layers) <= len(PALETTE):
        return layers
    shown = layers[:len(PALETTE) - 1]
    rest = layers[len(shown):]
    return [*shown, {"name": f"其他 {len(rest)} 种", "layers": sum(item["layers"] for item in rest)}]


def bond_distribution(image, draw, shown, center, diameter, legend_x, row_height):
    total = sum(item["layers"] for item in shown)
    muted = RECORD_MUTED
    ring(image, center, diameter, ((item["layers"], color) for item, color in zip(shown, PALETTE)),
         background=RECORD_PANEL)
    cx, cy = center
    draw.text((cx, cy - 12), compact_number(total), font=font(36, True), fill=TEXT, anchor="mm")
    draw.text((cx, cy + 23), "累计层数", font=font(19), fill=muted, anchor="mm")
    name_face, count_face, share_face = font(21), font(21, True), font(19)
    layers_x, share_x = WIDTH - PAD - 120, WIDTH - PAD - 28
    header_y = cy - len(shown) * row_height / 2 - 14
    for x, label, anchor in ((legend_x, "盟约", "lm"), (layers_x, "层数", "rm"), (share_x, "占比", "rm")):
        draw.text((x, header_y), label, font=font(18), fill=muted, anchor=anchor)
    draw.line((legend_x, header_y + 14, share_x, header_y + 14), fill=RECORD_LINE)
    name_x = legend_x + 60
    for index, (item, color) in enumerate(zip(shown, PALETTE)):
        y = cy + (index - (len(shown) - 1) / 2) * row_height
        draw.rounded_rectangle((legend_x, y - 6, legend_x + 12, y + 6), radius=RADIUS, fill=color)
        paste_icon(image, BOND_ICONS.get(item["name"]), legend_x + 24, text_middle(draw, y, name_face), 24, slot=28)
        name = ellipsize(draw, item["name"], layers_x - name_x - 76, name_face)
        draw.text((name_x, y), name, font=name_face, fill=TEXT, anchor="lm")
        draw.text((layers_x, y), f"{compact_number(item['layers'])} 层", font=count_face, fill=TEXT, anchor="rm")
        share = item["layers"] / total * 100
        draw.text((share_x, y), "<0.1%" if share < 0.1 else f"{share:.1f}%",
                  font=share_face, fill=muted, anchor="rm")


def score(image, draw, top, card):
    """左：胜率环与胜负 / 奖杯；右：盟约层数分布。"""
    height = 382
    score_right, bonds_left = PAD + 360, PAD + 386
    body = record_panel(draw, top, height, "作战表现", right=score_right)
    record_panel(draw, top, height, "盟约层数分布", left=bonds_left)

    total, wins = len(card.matches), card.wins
    losses = total - wins
    cx, cy = (PAD + score_right) // 2, body + 142
    diameter = 180
    ring(image, (cx, cy), diameter, ((wins, WIN), (losses, LOSS)), background=RECORD_PANEL)
    draw.text((cx, cy - 13), f"{wins / total:.1%}", font=font(35, True), fill=TEXT, anchor="mm")
    draw.text((cx, cy + 23), "胜率", font=font(20), fill=RECORD_MUTED, anchor="mm")

    columns = [("总局数", total, TEXT, None), ("胜场", wins, WIN, None), ("负场", losses, LOSS, None)]
    if card.trophy_change is not None:
        columns.append(("获得奖杯", card.trophy_change, ACCENT, card.trophy_icon))
    left = PAD + 16
    trophy_extra_width = 26 if card.trophy_change is not None else 0
    col_width = (score_right - 16 - left - trophy_extra_width) / len(columns)
    value_face = font(25, True)
    for label, value, color, filename in columns:
        width = col_width + (trophy_extra_width if filename else 0)
        x = left + width / 2
        draw.text((x, body + 252), label, font=font(18), fill=RECORD_MUTED, anchor="mm")
        draw_icon_value(image, draw, (x, body + 285), compact_number(value), value_face, color,
                        width - 4, filename, 30)
        left += width

    shown = shown_bonds(card.recap["bonds"])
    if shown:
        bond_distribution(image, draw, shown, (bonds_left + 112, cy), diameter, bonds_left + 225,
                          row_height=34)
    else:
        draw.text(((bonds_left + WIDTH - PAD) // 2, cy), "暂无盟约层数记录", font=font(20),
                  fill=RECORD_MUTED, anchor="mm")
    return top + height + RECORD_GAP


def key_matches(draw, top, card):
    recap = card.recap
    picks = [(recap.get("most_kills"), "最高击杀", lambda m: f"{fmt(m['kills'])} 次击杀"),
             (recap.get("most_layers"), "盟约最高", lambda m: f"{fmt(m['layers'])} 层盟约"),
             (recap.get("most_coins"), "金币最多", lambda m: f"{fmt(m['coins'])} 金币")]
    merged = {}
    for match, label, value in picks:
        if match:
            entry = merged.setdefault(match["id"], {"match": match, "labels": [], "values": []})
            entry["labels"].append(label)
            entry["values"].append(value(match))
    boss_line = None
    if recap.get("boss_matches"):
        boss_line = f"首领击破：普通 {recap.get('normal_matches', 0)} 局 · 隐藏 {recap.get('hidden_matches', 0)} 局"
    if not merged and not boss_line:
        return top
    row_height = 78
    height = 74 + len(merged) * row_height + (48 if boss_line else 0) + 14
    body = record_panel(draw, top, height, "关键对局")
    left, right = PAD + 24, WIDTH - PAD - 24
    value_face = font(23, True)
    for index, entry in enumerate(merged.values()):
        y = body + index * row_height
        match = entry["match"]
        draw.rounded_rectangle((left, y, right, y + row_height - 12), radius=RADIUS,
                               fill=RECORD_RAISED, outline=RECORD_LINE)
        draw.rectangle((left, y, left + 4, y + row_height - 12), fill=ACCENT)
        draw.text((left + 24, y + 21), " · ".join(entry["labels"]), font=font(22, True), fill=TEXT, anchor="lm")
        played = datetime.fromisoformat(match["played_at"]).astimezone(CHINA).strftime("%H:%M")
        draw.text((left + 24, y + 48), f"{played} · {match['difficulty']}", font=font(18),
                  fill=RECORD_MUTED, anchor="lm")
        value = ellipsize(draw, " · ".join(entry["values"]), 460, value_face)
        draw.text((right - 20, y + (row_height - 12) / 2), value, font=value_face, fill=ACCENT, anchor="rm")
    if boss_line:
        draw.text((left, body + len(merged) * row_height + 18), boss_line, font=font(20),
                  fill=RECORD_MUTED, anchor="lm")
    return top + height + RECORD_GAP


def chart_dashes(draw, left, right, y, color, *, dash=5, gap=4):
    for x in range(left, right, dash + gap):
        draw.line((x, y, min(x + dash - 1, right), y), fill=color)


def trend_area(image, xs, ys, top, baseline):
    left, right = xs[0], xs[-1]
    if left == right:
        return
    size = (right - left + 1, baseline - top + 1)
    mask = Image.new("L", size)
    fill = ImageDraw.Draw(mask)
    for x1, y1, x2, y2 in zip(xs, ys, xs[1:], ys[1:]):
        if y1 is not None and y2 is not None:
            a, b = x1 - left, x2 - left
            fill.polygon(((a, y1 - top), (b, y2 - top), (b, size[1] - 1), (a, size[1] - 1)), fill=255)
    fade = Image.linear_gradient("L").resize(size).point(lambda alpha: round((255 - alpha) * .22))
    image.paste(ACCENT, (left, top, right + 1, baseline + 1), ImageChops.multiply(mask, fade))


def trend(image, draw, top, card):
    points = list(stats.chart_points(card.matches[::-1], "recent"))
    layers = [point["peak"]["layers"] for point in points if point["peak"]]
    if not layers:
        height = 126
        body = record_panel(draw, top, height, "对局趋势")
        draw.text((PAD + 24, body + 14), "暂无盟约层数记录", font=font(20), fill=RECORD_MUTED, anchor="lm")
        return top + height + RECORD_GAP

    average = sum(layers) / len(layers)
    height = 419
    body = record_panel(draw, top, height, "对局趋势")
    content_left, right = PAD + 24, WIDTH - PAD - 24
    legend_face = font(19)
    for label, color, x in (("胜", WIN, right - 92), ("负", LOSS, right - 38)):
        draw.rectangle((x, top + 33, x + 8, top + 41), fill=color)
        draw.text((x + 14, top + 37), label, font=legend_face, fill=color, anchor="lm")
    metric_y = body + 17
    metric_face = font(22, True)
    icon_width = paste_icon(image, "metric-bond.png", content_left, text_middle(draw, metric_y, metric_face), 26)
    draw.text((content_left + icon_width, metric_y), "单项最高盟约层数", font=metric_face, fill=TEXT, anchor="lm")
    average_label = f"单项最高场均 {compact_number(average)} 层"
    label_left = right - round(draw.textlength(average_label, font=legend_face))
    chart_dashes(draw, label_left - 34, label_left - 10, metric_y, CHART_AVERAGE)
    draw.text((right, metric_y), average_label, font=legend_face, fill=CHART_AVERAGE, anchor="rm")

    left = PAD + 100
    base_y, plot_height = body + 218, 148
    plot_top = base_y - plot_height
    step = (max(layers) + 3) // 4
    max_layers = step * 4
    axis_face, point_face = font(18), font(20, True)
    col_width = (right - left) / len(points)
    xs = [round(left + (index + 0.5) * col_width) for index in range(len(points))]
    ys = [round(base_y - plot_height * point["peak"]["layers"] / max_layers) if point["peak"] else None
          for point in points]
    for value in range(0, max_layers + 1, step):
        y = base_y - plot_height * value / max_layers
        if value:
            chart_dashes(draw, left, right, y, RECORD_LINE, dash=4)
        else:
            draw.line((left, y, right, y), fill=RECORD_LINE)
        draw.text((left - 12, y), compact_number(value), font=axis_face, fill=RECORD_MUTED, anchor="rm")
    trend_area(image, xs, ys, plot_top, base_y)
    average_y = base_y - plot_height * average / max_layers
    chart_dashes(draw, left, right, average_y, CHART_AVERAGE)
    for x1, y1, x2, y2 in zip(xs, ys, xs[1:], ys[1:]):
        if y1 is not None and y2 is not None:
            draw.line((x1, y1, x2, y2), fill=ACCENT, width=2)
    for index, (point, x, y) in enumerate(zip(points, xs, ys), 1):
        win = point["result"] == "win"
        color = WIN if win else LOSS
        draw.text((x, base_y + 20), str(index), font=axis_face, fill=RECORD_MUTED, anchor="mm")
        draw.text((x, base_y + 45), "胜" if win else "负", font=axis_face, fill=color, anchor="mm")
        if y is None:
            continue
        draw.polygon(((x, y - 10), (x + 10, y), (x, y + 10), (x - 10, y)), fill=RECORD_PANEL)
        draw.polygon(((x, y - 7), (x + 7, y), (x, y + 7), (x - 7, y)), fill=color)
        peak = point["peak"]
        draw.text((x, y - 16), compact_number(peak["layers"]), font=point_face, fill=TEXT, anchor="mb",
                  stroke_width=2, stroke_fill=RECORD_PANEL)
        name = peak["names"][0]
        paste_icon(image, BOND_ICONS.get(name), x - 12, base_y + 73, 24, slot=24)
        name = ellipsize(draw, name, col_width - 12, axis_face)
        draw.text((x, base_y + 101), name, font=axis_face, fill=TEXT, anchor="mm")

    return top + height + RECORD_GAP


def match_list(image, draw, top, card):
    rows = card.matches[:MAX_ROWS]
    extra = len(card.matches) - len(rows)
    header_height, row_height = 44, 55
    height = 74 + header_height + len(rows) * row_height + (40 if extra else 0) + 12
    body = record_panel(draw, top, height, f"{card.day_word}对局", f"{len(card.matches)} 局")
    left, right = PAD + 24, WIDTH - PAD - 24
    columns = (("时间", 36), ("战果", 136), ("难度 / 等级", 208), ("策略", 432),
               ("回合", 685), ("击杀", 782), ("盟约层数", 879))
    draw.rectangle((left, body, right, body + header_height - 1), fill=RECORD_RAISED)
    for label, x in columns:
        draw.text((PAD + x, body + header_height // 2), label, font=font(19), fill=RECORD_MUTED, anchor="lm")
    draw.line((left, body + header_height, right, body + header_height), fill=RECORD_LINE)
    data_face = font(21)
    for index, row in enumerate(rows):
        top_y = body + header_height + index * row_height
        y = top_y + row_height // 2
        if index % 2 == 0:
            draw.rectangle((left, top_y + 1, right, top_y + row_height - 1), fill=RECORD_INSET)
        played = row["played_at"].astimezone(CHINA).strftime("%H:%M")
        draw.text((PAD + 36, y), played, font=font(21, True), fill=TEXT, anchor="lm")
        chip(draw, PAD + 136, y - 15, row["result"] == "win")
        draw.text((PAD + 208, y), ellipsize(draw, row["difficulty"], 204, data_face),
                  font=data_face, fill=TEXT, anchor="lm")
        band = row.get("strategy")
        _, strategy = bands.resolve(band)
        band_id = bands.band_id(band)
        offset = paste_icon(image, f"strategy-{band_id}.png" if band_id else None, PAD + 432,
                            text_middle(draw, y, data_face), 34, slot=34)
        draw.text((PAD + 432 + offset, y), ellipsize(draw, strategy or "—", 230 - offset, data_face),
                  font=data_face, fill=TEXT, anchor="lm")
        for x, value in ((685, row["rounds"]), (782, row["kills"]), (879, stats.bond_total(row))):
            label = compact_number(value) if value is not None else "—"
            draw.text((PAD + x, y), label, font=data_face, fill=TEXT, anchor="lm")
        if index < len(rows) - 1:
            draw.line((left, top_y + row_height, right, top_y + row_height), fill=RECORD_LINE)
    if extra:
        draw.text((left, body + header_height + len(rows) * row_height + 8),
                  f"另有 {extra} 局，完整列表请在网页查看", font=font(18), fill=RECORD_MUTED)
    return top + height + RECORD_GAP


def empty(draw, top, card):
    height = 180
    record_panel(draw, top, height)
    draw.text((WIDTH / 2, top + 70), f"{card.day_word}暂无可统计对局", font=font(30, True), fill=TEXT, anchor="mm")
    note = f"{card.excluded} 局被标记为疑似直接退出" if card.excluded else "导入或同步战绩后再来查看"
    draw.text((WIDTH / 2, top + 116), note, font=font(20), fill=RECORD_MUTED, anchor="mm")
    return top + height + RECORD_GAP


def strategy_header(draw, top, card):
    height = 180
    left = PAD + 36
    record_panel(draw, top, height, fill=RECORD_RAISED)
    draw.rectangle((PAD + 16, top + 26, PAD + 20, top + height - 26), fill=ACCENT)
    face = font(22, True)
    heading = ellipsize(draw, f"卫戍协议  /  {card.username}", WIDTH - 2 * PAD - 64, face)
    draw.text((left, top + 37), heading, font=face, fill=ACCENT, anchor="lm")
    draw.text((left, top + 92), "策略胜率", font=font(51, True), fill=TEXT, anchor="lm")
    note = f"全部时间　·　{len(card.entries)} 种开局策略　·　疑似直接退出不计入"
    draw.text((left, top + 140), note, font=font(22), fill=RECORD_MUTED, anchor="lm")
    return top + height + RECORD_GAP


def strategy_overview(image, draw, top, card):
    matches, wins = card.matches, card.wins
    favorite = card.entries[0]  # strategy_stats 已按局数排序
    cells = [
        ("总局数", compact_number(matches), "", None),
        ("胜 / 负", f"{compact_number(wins)} / {compact_number(matches - wins)}", "", None),
        ("总胜率", f"{wins / matches:.1%}", "", None, ACCENT),
        ("最常用", favorite["name"], "", strategy_icon(favorite["name"])),
    ]
    return highlight_grid(image, draw, top, "总览", cells, columns=4)


def strategy_icon(name):
    band = bands.band_id(name)
    return f"strategy-{band}.png" if band else None


def strategy_list(image, draw, top, card):
    header_height, row_height = 44, 58
    height = 74 + header_height + len(card.entries) * row_height + (44 if card.missing else 0) + 12
    body = record_panel(draw, top, height, "各策略胜率", "按局数排序")
    left, right = PAD + 24, WIDTH - PAD - 24
    rank_x, name_x, count_x = left + 22, left + 64, left + 420
    bar_left, bar_right, rate_x = left + 448, left + 720, left + 820
    draw.rectangle((left, body, right, body + header_height - 1), fill=RECORD_RAISED)
    label_face = font(19)
    for x, label, anchor in ((rank_x, "#", "mm"), (name_x, "策略", "lm"), (count_x, "局数", "rm"),
                             (bar_left, "胜负占比", "lm"), (rate_x, "胜率", "rm"), (right - 16, "胜 / 负", "rm")):
        draw.text((x, body + header_height // 2), label, font=label_face, fill=RECORD_MUTED, anchor=anchor)
    draw.line((left, body + header_height, right, body + header_height), fill=RECORD_LINE)
    data_face, rate_face = font(21), font(23, True)
    for index, entry in enumerate(card.entries):
        top_y = body + header_height + index * row_height
        y = top_y + row_height // 2
        if index % 2 == 0:
            draw.rectangle((left, top_y + 1, right, top_y + row_height - 1), fill=RECORD_INSET)
        draw.text((rank_x, y), str(index + 1), font=font(19, True),
                  fill=ACCENT if index < 3 else RECORD_MUTED, anchor="mm")
        paste_icon(image, strategy_icon(entry["name"]), name_x, text_middle(draw, y, data_face), 34, slot=34)
        offset = 42  # 自定义策略没有图标，名字也保持同一列
        name = ellipsize(draw, entry["name"], count_x - 70 - name_x - offset, data_face)
        draw.text((name_x + offset, y), name, font=data_face, fill=TEXT, anchor="lm")
        draw.text((count_x, y), compact_number(entry["count"]), font=data_face, fill=TEXT, anchor="rm")
        rate = entry["win_rate"]
        split = bar_left + round((bar_right - bar_left) * rate)
        draw.rounded_rectangle((bar_left, y - 7, bar_right, y + 7), radius=RADIUS, fill=RECORD_LOSS_BAR)
        if split > bar_left:
            draw.rounded_rectangle((bar_left, y - 7, split, y + 7), radius=RADIUS, fill=WIN)
        draw.text((rate_x, y), f"{rate:.1%}", font=rate_face, fill=WIN if rate >= 0.5 else LOSS, anchor="rm")
        losses = entry["count"] - entry["wins"]
        draw.text((right - 16, y), f"{compact_number(entry['wins'])} / {compact_number(losses)}",
                  font=data_face, fill=RECORD_MUTED, anchor="rm")
        if index < len(card.entries) - 1:
            draw.line((left, top_y + row_height, right, top_y + row_height), fill=RECORD_LINE)
    if card.missing:
        draw.text((left, body + header_height + len(card.entries) * row_height + 24),
                  f"另有 {card.missing} 局未记录开局策略，未计入统计", font=font(19), fill=RECORD_MUTED, anchor="lm")
    return top + height + RECORD_GAP


def render(card):
    stamp = datetime.now(CHINA).strftime("%Y-%m-%d %H:%M")
    # 查询和同步先完成。以整张卡的数据及页脚分钟区分内容，战绩更新时自然重新绘制。
    key = sha256(repr((stamp, card)).encode("utf-8")).digest()
    with _record_png_lock:
        png = _record_pngs.get(key)
        if png is not None:
            _record_pngs.move_to_end(key)
            return png
    png = _render_png(card, stamp)
    with _record_png_lock:
        _record_pngs[key] = png
        _record_pngs.move_to_end(key)
        if len(_record_pngs) > RECORD_PNG_CACHE_SIZE:
            _record_pngs.popitem(last=False)
    return png


def _render_png(card, stamp):
    """先在足够高的画布上排版，再裁到实际高度。"""
    canvas = 4000
    if isinstance(card, StrategyCard):
        canvas = max(canvas, 800 + len(card.entries) * 60)
    image = Image.new("RGB", (WIDTH, canvas), RECORD_BG)
    draw = ImageDraw.Draw(image)
    if isinstance(card, StrategyCard):
        y = strategy_header(draw, PAD, card)
        y = strategy_overview(image, draw, y, card)
        y = strategy_list(image, draw, y, card)
    elif card.matches:
        y = score(image, draw, header(draw, PAD, card), card)
        y = highlights(image, draw, y, card)
        # 最近 N 局看走势；单日对局多，折线挤不下，改列关键对局。
        y = trend(image, draw, y, card) if card.title else key_matches(draw, y, card)
        y = match_list(image, draw, y, card)
    else:
        y = empty(draw, header(draw, PAD, card), card)
    draw.text((PAD, y + 4), f"卫戍协议 · 作战档案　生成于 {stamp}（北京时间）", font=font(17), fill=RECORD_MUTED)
    output = io.BytesIO()
    # QQ 图片用较快的无损压缩，避免额外编码耗时且保持上传体积接近原图。
    image.crop((0, 0, WIDTH, y + 40)).save(output, format="PNG", compress_level=3)
    return output.getvalue()
