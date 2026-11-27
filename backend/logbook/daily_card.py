"""昨日战报图片：把某一天的战绩汇总画成一张 PNG（网页下载、QQ 机器人发图共用）。

取数口径与网页「昨日战报」一致：北京时间按开局时间归到当天，默认排除疑似直接退出。
"""

import io
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from . import bands, daily_review, stats
from .records import CHINA

WIDTH = 1080
PAD = 40
GAP = 20

BG = "#0b1014"
PANEL = "#121a20"
INSET = "#0e151a"
LINE = "#25323c"
TEXT = "#eef3f6"
MUTED = "#8fa0ad"
ACCENT = "#deef81"
WIN = "#9fe0a0"
LOSS = "#ff9aa8"
HUD = "#43d8bc"
TARGET = "#f2a046"
PALETTE = ["#628ef5", "#36bda3", "#a486ef", "#f5b552", "#45a9d1", "#eb7f9c", "#8593ae"]
WEEKDAYS = "一二三四五六日"
MAX_ROWS = 12

FONT_CANDIDATES = {
    False: [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ],
    True: [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ],
}


class CardFontError(RuntimeError):
    """找不到可显示中文的字体。"""


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
    return ImageFont.truetype(font_path(bold), size)


@dataclass
class Card:
    day: date
    username: str
    matches: list
    excluded: int
    trophy_change: int | None
    recap: dict

    @property
    def wins(self):
        return sum(row["result"] == "win" for row in self.matches)

    @property
    def is_yesterday(self):
        return self.day == datetime.now(CHINA).date() - timedelta(days=1)

    @property
    def day_word(self):
        """标题与文案用「昨日」还是「当天」：传了别的日期时不该写成昨日。"""
        return "昨日" if self.is_yesterday else "当天"


def build(rows, excluded, day, username):
    """rows：当天已排除疑似直接退出的对局，按开局时间倒序。"""
    trophies = [row["trophies"] for row in rows if row.get("trophies") is not None]
    return Card(day=day, username=username, matches=list(rows), excluded=excluded,
                trophy_change=sum(trophies) if trophies else None, recap=daily_review.summarize(rows))


# ---------------------------------------------------------------- 绘图小工具

def fmt(value, digits=1):
    if value is None:
        return "—"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.{digits}f}"
    return f"{int(value):,}"


def ellipsize(draw, text, width, face):
    if draw.textlength(text, font=face) <= width:
        return text
    while text and draw.textlength(text + "…", font=face) > width:
        text = text[:-1]
    return text + "…"


def panel(draw, top, height, title=None, note=None):
    draw.rounded_rectangle((PAD, top, WIDTH - PAD, top + height), radius=6, fill=PANEL, outline=LINE)
    if title:
        draw.text((PAD + 24, top + 20), title, font=font(26, True), fill=TEXT)
        if note:
            face = font(18)
            draw.text((WIDTH - PAD - 24 - draw.textlength(note, font=face), top + 27), note, font=face, fill=MUTED)
    return top + (66 if title else 0)


def chip(draw, x, y, win):
    color = WIN if win else LOSS
    draw.rounded_rectangle((x, y, x + 36, y + 30), radius=4, fill=INSET, outline=color)
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
    height = 170
    draw.rounded_rectangle((PAD, top, WIDTH - PAD, top + height), radius=6, fill="#0f1a1d", outline="#21353a")
    draw.rectangle((PAD, top, PAD + 90, top + 3), fill=ACCENT)
    radar(draw, WIDTH - PAD - 190, top + height // 2)
    draw.text((PAD + 32, top + 28), f"卫戍协议  /  {card.username}", font=font(20, True), fill=ACCENT)
    draw.text((PAD + 30, top + 58), "昨日战报" if card.is_yesterday else "每日战报", font=font(56, True), fill=TEXT)
    weekday = WEEKDAYS[card.day.weekday()]
    draw.text((PAD + 32, top + 128), f"{card.day.isoformat()}  星期{weekday}", font=font(22), fill=MUTED)
    return top + height + GAP


def score(draw, top, card):
    total, wins = len(card.matches), card.wins
    rate = wins / total if total else 0
    body = panel(draw, top, 200, "作战表现", f"已排除 {card.excluded} 局疑似直接退出" if card.excluded else None)
    draw.text((PAD + 24, body + 4), "胜率", font=font(18), fill=MUTED)
    draw.text((PAD + 20, body + 26), f"{rate * 100:.1f}%", font=font(64, True), fill=ACCENT)
    columns = [("总对局", fmt(total), TEXT), ("胜场", fmt(wins), WIN), ("负场", fmt(total - wins), LOSS)]
    if card.trophy_change is not None:
        # 奖杯只在联合模拟通关时获得、不会扣减：显示当天获得数，不带正负号。
        columns.append(("获得奖杯", fmt(card.trophy_change), ACCENT))
    x = PAD + 330
    for label, value, color in columns:
        draw.text((x, body + 10), label, font=font(18), fill=MUTED)
        draw.text((x, body + 36), value, font=font(38, True), fill=color)
        x += 160
    bar_top, left, right = body + 108, PAD + 24, WIDTH - PAD - 24
    draw.rectangle((left, bar_top, right, bar_top + 6), fill="#4a2e35")
    draw.rectangle((left, bar_top, left + int((right - left) * rate), bar_top + 6), fill=WIN)
    return top + 200 + GAP


def highlights(draw, top, card):
    recap, rows = card.recap, card.matches
    peak = stats.peak(rows)
    kills = [row["kills"] for row in rows if row["kills"] is not None]
    coins = [row["coins"] for row in rows if row.get("coins") is not None]
    seconds = recap.get("total_duration_seconds")
    duration = "—" if seconds is None else (f"{seconds // 3600} 小时 {seconds // 60 % 60} 分" if seconds >= 3600 else f"{seconds // 60} 分")
    # 单项最高盟约：层数放大，并列的盟约名放到小字副行，避免被截断。
    cells = [
        ("单局最高盟约总层数", f"{fmt(max(map(stats.bond_total, rows), default=None))} 层"),
        ("单项最高盟约", (f"{peak['layers']} 层", "、".join(peak["names"])) if peak else "—"),
        ("场均击杀", fmt(sum(kills) / len(kills) if kills else None)),
        ("金币总花费", fmt(sum(coins) if coins else None)),
        ("最长连胜", f"{fmt(recap.get('longest_win_streak'))} 局"),
        ("已记录用时", duration),
    ]
    height = 66 + 2 * 92 + 10
    body = panel(draw, top, height, f"{card.day_word}亮点")
    cell_width = (WIDTH - 2 * PAD - 48) / 3
    for index, (label, value) in enumerate(cells):
        x = PAD + 24 + (index % 3) * cell_width
        y = body + (index // 3) * 92
        draw.line((x, y, x + cell_width - 20, y), fill=LINE)
        sub = None
        if isinstance(value, tuple):
            value, sub = value
        draw.text((x, y + 10), label, font=font(18), fill=MUTED)
        draw.text((x, y + 38), ellipsize(draw, value, cell_width - 24, font(30, True)), font=font(30, True), fill=TEXT)
        if sub:
            left = x + draw.textlength(value, font=font(30, True)) + 12
            draw.text((left, y + 48), ellipsize(draw, sub, x + cell_width - 24 - left, font(18)), font=font(18), fill=MUTED)
    return top + height + GAP


def bonds(draw, top, card):
    layers = card.recap.get("bonds") or []
    if not layers:
        return top
    total = sum(item["layers"] for item in layers)
    shown = layers[:6]
    rest = layers[6:]
    if rest:
        shown = shown + [{"name": f"其他 {len(rest)} 种", "layers": sum(item["layers"] for item in rest)}]
    height = 66 + len(shown) * 40 + 14
    body = panel(draw, top, height, "盟约层数分布", f"累计 {fmt(total)} 层")
    longest = max(item["layers"] for item in shown)
    for index, item in enumerate(shown):
        y = body + index * 40
        color = PALETTE[index % len(PALETTE)]
        draw.rectangle((PAD + 24, y + 9, PAD + 34, y + 19), fill=color)
        draw.text((PAD + 46, y), item["name"], font=font(21), fill=TEXT)
        left, right = PAD + 230, WIDTH - PAD - 170
        draw.rounded_rectangle((left, y + 8, right, y + 20), radius=3, fill=INSET)
        draw.rounded_rectangle((left, y + 8, left + max(6, int((right - left) * item["layers"] / longest)), y + 20), radius=3, fill=color)
        draw.text((WIDTH - PAD - 150, y), f"{fmt(item['layers'])} 层", font=font(21, True), fill=TEXT)
        share = f"{item['layers'] / total * 100:.1f}%"
        draw.text((WIDTH - PAD - 24 - draw.textlength(share, font=font(19)), y + 2), share, font=font(19), fill=MUTED)
    return top + height + GAP


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


def match_list(draw, top, card):
    rows = card.matches[:MAX_ROWS]
    extra = len(card.matches) - len(rows)
    height = 66 + 40 + len(rows) * 50 + (40 if extra else 0) + 8
    body = panel(draw, top, height, f"{card.day_word}对局", f"{len(card.matches)} 局")
    columns = [("时间", 24), ("战果", 116), ("难度 / 等级", 186), ("策略", 410), ("回合", 690), ("击杀", 790), ("盟约层数", 890)]
    for label, x in columns:
        draw.text((PAD + x, body), label, font=font(17), fill=MUTED)
    draw.line((PAD + 24, body + 32, WIDTH - PAD - 24, body + 32), fill=LINE)
    for index, row in enumerate(rows):
        y = body + 40 + index * 50
        played = row["played_at"].astimezone(CHINA).strftime("%H:%M")
        draw.text((PAD + 24, y + 10), played, font=font(21, True), fill=TEXT)
        chip(draw, PAD + 116, y + 6, row["result"] == "win")
        draw.text((PAD + 186, y + 10), ellipsize(draw, row["difficulty"], 210, font(20)), font=font(20), fill=TEXT)
        unit, strategy = bands.resolve(row.get("strategy"))
        draw.text((PAD + 410, y + 10), ellipsize(draw, strategy or "—", 260, font(20)), font=font(20), fill=TEXT)
        draw.text((PAD + 690, y + 10), fmt(row["rounds"]), font=font(20), fill=TEXT)
        draw.text((PAD + 790, y + 10), fmt(row["kills"]), font=font(20), fill=TEXT)
        draw.text((PAD + 890, y + 10), fmt(stats.bond_total(row)), font=font(20), fill=TEXT)
        if index < len(rows) - 1:
            draw.line((PAD + 24, y + 46, WIDTH - PAD - 24, y + 46), fill="#1b252d")
    if extra:
        draw.text((PAD + 24, body + 40 + len(rows) * 50 + 8), f"另有 {extra} 局，完整列表请在网页查看", font=font(18), fill=MUTED)
    return top + height + GAP


def empty(draw, top, card):
    height = 180
    panel(draw, top, height)
    draw.text((WIDTH / 2, top + 70), f"{card.day_word}暂无可统计对局", font=font(30, True), fill=TEXT, anchor="mm")
    note = f"{card.excluded} 局被标记为疑似直接退出" if card.excluded else "导入或同步战绩后再来查看"
    draw.text((WIDTH / 2, top + 116), note, font=font(20), fill=MUTED, anchor="mm")
    return top + height + GAP


def render(card):
    """先在足够高的画布上排版，再裁到实际高度。"""
    image = Image.new("RGB", (WIDTH, 4000), BG)
    draw = ImageDraw.Draw(image)
    y = header(draw, PAD, card)
    if card.matches:
        for section in (score, highlights, bonds, key_matches, match_list):
            y = section(draw, y, card)
    else:
        y = empty(draw, y, card)
    stamp = datetime.now(CHINA).strftime("%Y-%m-%d %H:%M")
    draw.text((PAD, y + 4), f"卫戍协议 · 作战档案　生成于 {stamp}（北京时间）", font=font(16), fill="#5d6b76")
    output = io.BytesIO()
    image.crop((0, 0, WIDTH, y + 40)).save(output, format="PNG", optimize=True)
    return output.getvalue()
