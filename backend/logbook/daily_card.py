"""每日战报与 QQ 近期战绩的 PNG 渲染。

取数口径与网页「昨日战报」一致：北京时间按开局时间归到当天，默认排除疑似直接退出。
"""

import io
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

from . import bands, daily_review, stats
from .bond_names import BOND_NAMES
from .records import CHINA, Filters

WIDTH = 1080
PAD = 40
GAP = 20

# 与 frontend/src/style.css 的默认深色主题保持一致。
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
HUD = "#43d8bc"
TARGET = "#f2a046"
PALETTE = ["#628ef5", "#36bda3", "#a486ef", "#f5b552", "#45a9d1", "#eb7f9c", "#8593ae"]
# QQ 缩略图需要更亮的面板和文字，保留网页主题的强调色与胜负色。
RECORD_BG = "#172025"
RECORD_PANEL = "#27363b"
RECORD_RAISED = "#33474d"
RECORD_INSET = "#1e2b30"
RECORD_LINE = "#566c72"
RECORD_MUTED = "#c2d0cf"
RECORD_GAP = 26
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


def paste_icon(image, filename, x, y, size):
    art = icon(filename, size)
    if art is None:
        return 0
    image.paste(art, (int(x) + (size - art.width) // 2, int(y) + (size - art.height) // 2), art)
    return size + 8


def ring(image, center, diameter, segments, *, background=PANEL):
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


def section_title(draw, left, top, text):
    draw.rectangle((left, top + 5, left + 3, top + 28), fill=ACCENT)
    draw.text((left + 14, top), text, font=font(26, True), fill=TEXT)


def panel(draw, top, height, title=None, note=None):
    draw.rounded_rectangle((PAD, top, WIDTH - PAD, top + height), radius=RADIUS, fill=PANEL, outline=LINE)
    if title:
        section_title(draw, PAD + 24, top + 20, title)
        if note:
            face = font(18)
            draw.text((WIDTH - PAD - 24 - draw.textlength(note, font=face), top + 27), note, font=face, fill=MUTED)
    return top + (66 if title else 0)


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


def radar(draw, cx, cy):
    """页头右侧的雷达靶环，呼应网页页头的动效。"""
    for radius, color, width in ((88, "#3d2c17", 1), (62, "#6b4a22", 1), (40, TARGET, 2), (20, TARGET, 2)):
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=color, width=width)
    draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=TARGET)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        reach = 100 if dx else 72  # 纵向不超出页头面板
        draw.line((cx + dx * 28, cy + dy * 28, cx + dx * reach, cy + dy * reach), fill="#5a4120", width=1)
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        x, y = cx + sx * 120, cy + sy * 70
        draw.line((x, y, x, y - sy * 16), fill=HUD, width=2)
        draw.line((x, y, x - sx * 20, y), fill=HUD, width=2)


# ---------------------------------------------------------------- 各区块

def header(draw, top, card):
    if card.title:
        return recent_header(draw, top, card)
    height = 170
    draw.rounded_rectangle((PAD, top, WIDTH - PAD, top + height), radius=6, fill="#0f1a1d", outline="#21353a")
    draw.rectangle((PAD, top, PAD + 90, top + 3), fill=ACCENT)
    radar(draw, WIDTH - PAD - 190, top + height // 2)
    heading = ellipsize(draw, f"卫戍协议  /  {card.username}", 650, font(20, True))
    draw.text((PAD + 32, top + 28), heading, font=font(20, True), fill=ACCENT)
    draw.text((PAD + 30, top + 58), "昨日战报" if card.is_yesterday else "每日战报",
              font=font(56, True), fill=TEXT)
    weekday = WEEKDAYS[card.day.weekday()]
    draw.text((PAD + 32, top + 128), f"{card.day.isoformat()}  星期{weekday}", font=font(22), fill=MUTED)
    return top + height + GAP


def recent_header(draw, top, card):
    height = 142
    left = PAD + 36
    record_panel(draw, top, height, fill=RECORD_RAISED)
    draw.rectangle((PAD + 16, top + 26, PAD + 20, top + height - 26), fill=ACCENT)
    face = font(22, True)
    heading = ellipsize(draw, f"卫戍协议  /  {card.username}", WIDTH - 2 * PAD - 64, face)
    draw.text((left, top + 37), heading, font=face, fill=ACCENT, anchor="lm")
    draw.text((left, top + 92), card.title, font=font(51, True), fill=TEXT, anchor="lm")
    return top + height + RECORD_GAP


def score(image, draw, top, card):
    total, wins = len(card.matches), card.wins
    rate = wins / total if total else 0
    body = panel(draw, top, 200, "作战表现", f"已排除 {card.excluded} 局疑似直接退出" if card.excluded else None)
    draw.text((PAD + 24, body + 4), "胜率", font=font(18), fill=MUTED)
    draw.text((PAD + 20, body + 26), f"{rate * 100:.1f}%", font=font(64, True), fill=ACCENT)
    columns = [("总对局", fmt(total), TEXT, None), ("胜场", fmt(wins), WIN, None),
               ("负场", fmt(total - wins), LOSS, None)]
    if card.trophy_change is not None:
        # 奖杯只在联合模拟通关时获得、不会扣减：显示当天获得数，不带正负号。
        columns.append(("获得奖杯", fmt(card.trophy_change), ACCENT, card.trophy_icon))
    x = PAD + 330
    for label, value, color, filename in columns:
        draw.text((x, body + 10), label, font=font(18), fill=MUTED)
        offset = paste_icon(image, filename, x, body + 43, 34)
        face = font(38, True)
        width = min(144, WIDTH - PAD - 24 - x) - offset
        draw.text((x + offset, body + 36), ellipsize(draw, value, width, face), font=face, fill=color)
        x += 160
    bar_top, left, right = body + 108, PAD + 24, WIDTH - PAD - 24
    draw.rectangle((left, bar_top, right, bar_top + 6), fill="#4a2e35")
    draw.rectangle((left, bar_top, left + int((right - left) * rate), bar_top + 6), fill=WIN)
    return top + 200 + GAP


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
    if card.title:
        return recent_highlights(image, draw, top, cells)

    row_height = 92
    height = 66 + 2 * row_height + 10
    body = panel(draw, top, height, f"{card.day_word}亮点")
    cell_width = (WIDTH - 2 * PAD - 48) / 3
    label_face, value_face = font(18), font(30, True)
    for index, (label, value, sub, filename) in enumerate(cells):
        x = PAD + 24 + (index % 3) * cell_width
        y = body + (index // 3) * row_height
        draw.line((x, y, x + cell_width - 20, y), fill=LINE)
        draw.text((x, y + 10), label, font=label_face, fill=MUTED)
        offset = paste_icon(image, filename, x, y + 42, 28)
        value = ellipsize(draw, value, cell_width - 24 - offset, value_face)
        draw.text((x + offset, y + 38), value, font=value_face, fill=TEXT)
        if sub:
            left = x + offset + draw.textlength(value, font=value_face) + 12
            remaining = x + cell_width - 24 - left
            if remaining >= 24:
                draw.text((left, y + 48), ellipsize(draw, sub, remaining, label_face), font=label_face, fill=MUTED)
    return top + height + GAP


def recent_highlights(image, draw, top, cells):
    height, row_height = 314, 112
    body = record_panel(draw, top, height, "近期亮点")
    cell_width = (WIDTH - 2 * (PAD + 24) - 2 * 14) / 3
    label_face, value_face = font(20), font(32, True)
    for index, (label, value, sub, filename) in enumerate(cells):
        x = PAD + 24 + (index % 3) * (cell_width + 14)
        y = body + (index // 3) * row_height
        center = x + cell_width / 2
        draw.rounded_rectangle((x, y, x + cell_width, y + row_height - 10), radius=RADIUS,
                               fill=RECORD_RAISED, outline=RECORD_LINE)
        draw.text((center, y + 23), label, font=label_face, fill=RECORD_MUTED, anchor="mm")
        icon_size = 28
        offset = icon_size + 8 if icon(filename, icon_size) is not None else 0
        value = ellipsize(draw, value, cell_width - 28 - offset, value_face)
        left = center - (offset + draw.textlength(value, font=value_face)) / 2
        value_y = y + 58
        if offset:
            paste_icon(image, filename, left, value_y - icon_size // 2, icon_size)
        draw.text((left + offset, value_y), value, font=value_face, fill=TEXT, anchor="lm")
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


def bond_distribution(image, draw, shown, center, diameter, legend_x, row_height, *, legend_header=False):
    total = sum(item["layers"] for item in shown)
    background, muted = (RECORD_PANEL, RECORD_MUTED) if legend_header else (PANEL, MUTED)
    ring(image, center, diameter, ((item["layers"], color) for item, color in zip(shown, PALETTE)),
         background=background)
    cx, cy = center
    draw.text((cx, cy - 12), compact_number(total), font=font(36, True), fill=TEXT, anchor="mm")
    draw.text((cx, cy + 23), "累计层数", font=font(19), fill=muted, anchor="mm")
    name_face, count_face, share_face = font(21), font(21, True), font(19)
    layers_x, share_x = WIDTH - PAD - 120, WIDTH - PAD - 28
    if legend_header:
        header_y = cy - len(shown) * row_height / 2 - 14
        for x, label, anchor in ((legend_x, "盟约", "lm"), (layers_x, "层数", "rm"), (share_x, "占比", "rm")):
            draw.text((x, header_y), label, font=font(18), fill=muted, anchor=anchor)
        draw.line((legend_x, header_y + 14, share_x, header_y + 14), fill=RECORD_LINE)
    name_x = legend_x + 60
    for index, (item, color) in enumerate(zip(shown, PALETTE)):
        y = cy + (index - (len(shown) - 1) / 2) * row_height
        draw.rounded_rectangle((legend_x, y - 6, legend_x + 12, y + 6), radius=RADIUS, fill=color)
        paste_icon(image, BOND_ICONS.get(item["name"]), legend_x + 28, y - 12, 24)
        name = ellipsize(draw, item["name"], layers_x - name_x - 76, name_face)
        draw.text((name_x, y), name, font=name_face, fill=TEXT, anchor="lm")
        draw.text((layers_x, y), f"{compact_number(item['layers'])} 层", font=count_face, fill=TEXT, anchor="rm")
        share = item["layers"] / total * 100
        draw.text((share_x, y), "<0.1%" if share < 0.1 else f"{share:.1f}%",
                  font=share_face, fill=muted, anchor="rm")


def bonds(image, draw, top, card):
    shown = shown_bonds(card.recap["bonds"])
    if not shown:
        return top
    diameter, row_height = 224, 38
    content_height = max(diameter, len(shown) * row_height)
    height = 66 + content_height + 22
    body = panel(draw, top, height, "盟约层数分布")
    center = (PAD + 180, body + content_height // 2)
    bond_distribution(image, draw, shown, center, diameter, PAD + 346, row_height)
    return top + height + GAP


def recent_score(image, draw, top, card):
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
    col_width = (score_right - 16 - left) / len(columns)
    value_face = font(25, True)
    for index, (label, value, color, filename) in enumerate(columns):
        x = left + (index + 0.5) * col_width
        draw.text((x, body + 252), label, font=font(18), fill=RECORD_MUTED, anchor="mm")
        size = 18
        offset = size + 8 if icon(filename, size) is not None else 0
        value = ellipsize(draw, compact_number(value), col_width - 4 - offset, value_face)
        start = x - (draw.textlength(value, font=value_face) + offset) / 2
        if offset:
            paste_icon(image, filename, start, body + 276, size)
        draw.text((start + offset, body + 285), value, font=value_face, fill=color, anchor="lm")

    shown = shown_bonds(card.recap["bonds"])
    if shown:
        bond_distribution(image, draw, shown, (bonds_left + 112, cy), diameter, bonds_left + 225,
                          row_height=34, legend_header=True)
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
    height = 66 + len(merged) * 64 + (44 if boss_line else 0) + 8
    body = panel(draw, top, height, "关键对局")
    for index, entry in enumerate(merged.values()):
        y = body + index * 64
        match = entry["match"]
        draw.rounded_rectangle((PAD + 24, y, WIDTH - PAD - 24, y + 54), radius=4, fill=INSET, outline=LINE)
        draw.text((PAD + 40, y + 4), " · ".join(entry["labels"]), font=font(20, True), fill=TEXT)
        played = datetime.fromisoformat(match["played_at"]).astimezone(CHINA).strftime("%H:%M")
        draw.text((PAD + 40, y + 31), f"{played} · {match['difficulty']}", font=font(16), fill=MUTED)
        value = " · ".join(entry["values"])
        draw.text((WIDTH - PAD - 44 - draw.textlength(value, font=font(21, True)), y + 15), value, font=font(21, True), fill=ACCENT)
    if boss_line:
        draw.text((PAD + 24, body + len(merged) * 64 + 8), boss_line, font=font(19), fill=MUTED)
    return top + height + GAP


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
    icon_width = paste_icon(image, "metric-bond.png", content_left, metric_y - 12, 24)
    draw.text((content_left + icon_width, metric_y), "单项最高盟约层数",
              font=font(22, True), fill=TEXT, anchor="lm")
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
        paste_icon(image, BOND_ICONS.get(name), x - 12, base_y + 61, 24)
        name = ellipsize(draw, name, col_width - 12, axis_face)
        draw.text((x, base_y + 101), name, font=axis_face, fill=TEXT, anchor="mm")

    return top + height + RECORD_GAP


def match_list(image, draw, top, card):
    rows = card.matches[:MAX_ROWS]
    extra = len(card.matches) - len(rows)
    recent = bool(card.title)
    panel_fn, gap = (record_panel, RECORD_GAP) if recent else (panel, GAP)
    title_height, header_height, row_height = (74, 44, 55) if recent else (66, 40, 50)
    height = title_height + header_height + len(rows) * row_height + (40 if extra else 0) + 12
    body = panel_fn(draw, top, height, f"{card.day_word}对局", f"{len(card.matches)} 局")
    left, right = PAD + 24, WIDTH - PAD - 24
    columns = (("时间", 36), ("战果", 136), ("难度 / 等级", 208), ("策略", 432),
               ("回合", 685), ("击杀", 782), ("盟约层数", 879))
    if recent:
        draw.rectangle((left, body, right, body + header_height - 1), fill=RECORD_RAISED)
    for label, x in columns:
        draw.text((PAD + x, body + header_height // 2), label, font=font(19 if recent else 17),
                  fill=RECORD_MUTED if recent else MUTED, anchor="lm")
    draw.line((left, body + header_height, right, body + header_height), fill=RECORD_LINE if recent else LINE)
    data_face = font(21 if recent else 20)
    for index, row in enumerate(rows):
        top_y = body + header_height + index * row_height
        y = top_y + row_height // 2
        if recent and index % 2 == 0:
            draw.rectangle((left, top_y + 1, right, top_y + row_height - 1), fill=RECORD_INSET)
        played = row["played_at"].astimezone(CHINA).strftime("%H:%M")
        draw.text((PAD + 36, y), played, font=font(21, True), fill=TEXT, anchor="lm")
        chip(draw, PAD + 136, y - 15, row["result"] == "win")
        draw.text((PAD + 208, y), ellipsize(draw, row["difficulty"], 204, data_face),
                  font=data_face, fill=TEXT, anchor="lm")
        band = row.get("strategy")
        _, strategy = bands.resolve(band)
        band_id = bands.band_id(band)
        offset = paste_icon(image, f"strategy-{band_id}.png" if band_id else None, PAD + 432, y - 17, 34)
        draw.text((PAD + 432 + offset, y), ellipsize(draw, strategy or "—", 230 - offset, data_face),
                  font=data_face, fill=TEXT, anchor="lm")
        for x, value in ((685, row["rounds"]), (782, row["kills"]), (879, stats.bond_total(row))):
            label = compact_number(value) if value is not None else "—"
            draw.text((PAD + x, y), label, font=data_face, fill=TEXT, anchor="lm")
        if index < len(rows) - 1:
            draw.line((left, top_y + row_height, right, top_y + row_height), fill=RECORD_LINE if recent else LINE)
    if extra:
        draw.text((left, body + header_height + len(rows) * row_height + 8),
                  f"另有 {extra} 局，完整列表请在网页查看", font=font(18), fill=RECORD_MUTED if recent else MUTED)
    return top + height + gap


def empty(draw, top, card):
    height = 180
    (record_panel if card.title else panel)(draw, top, height)
    draw.text((WIDTH / 2, top + 70), f"{card.day_word}暂无可统计对局", font=font(30, True), fill=TEXT, anchor="mm")
    note = f"{card.excluded} 局被标记为疑似直接退出" if card.excluded else "导入或同步战绩后再来查看"
    draw.text((WIDTH / 2, top + 116), note, font=font(20),
              fill=RECORD_MUTED if card.title else MUTED, anchor="mm")
    return top + height + (RECORD_GAP if card.title else GAP)


def render(card):
    """先在足够高的画布上排版，再裁到实际高度。"""
    image = Image.new("RGB", (WIDTH, 4000), RECORD_BG if card.title else BG)
    draw = ImageDraw.Draw(image)
    y = header(draw, PAD, card)
    if card.matches:
        y = recent_score(image, draw, y, card) if card.title else score(image, draw, y, card)
        y = highlights(image, draw, y, card)
        if card.title:
            y = trend(image, draw, y, card)
        else:
            y = bonds(image, draw, y, card)
            y = key_matches(draw, y, card)
        y = match_list(image, draw, y, card)
    else:
        y = empty(draw, y, card)
    stamp = datetime.now(CHINA).strftime("%Y-%m-%d %H:%M")
    draw.text((PAD, y + 4), f"卫戍协议 · 作战档案　生成于 {stamp}（北京时间）",
              font=font(17 if card.title else 16), fill=RECORD_MUTED if card.title else MUTED)
    output = io.BytesIO()
    # 保持 PNG 无损，避开 optimize=True 带来的额外编码耗时。
    image.crop((0, 0, WIDTH, y + 40)).save(output, format="PNG")
    return output.getvalue()
