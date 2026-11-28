import io
from collections import OrderedDict
from datetime import date, datetime, timedelta
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
from PIL import Image

from logbook import bands, daily_card, stats
from logbook.records import CHINA


def has_font():
    try:
        daily_card.font_path(False)
    except daily_card.CardFontError:
        return False
    return True


needs_font = pytest.mark.skipif(not has_font(), reason="没有可用的中文字体")


def match(hour, result, **extra):
    return {
        "id": f"m{hour}", "played_at": datetime(2026, 11, 26, hour, 5, tzinfo=CHINA), "result": result,
        "play": "联合模拟", "difficulty": "绝境模拟", "strategy": "森蚺", "rounds": 12, "kills": 100 + hour,
        "coins": 80, "trophies": 5, "duration_seconds": 1500,
        "bonds": [{"name": "萨尔贡", "layers": 6}, {"name": "精准", "layers": 3}], "bosses": ["boss_1"], **extra,
    }


def test_bands_resolve_unit_id_and_strategy():
    assert bands.resolve("band_jenga") == ("但书", "条文修正")
    assert bands.resolve("但书") == ("但书", "条文修正")
    assert bands.resolve("条文修正") == ("但书", "条文修正")
    assert bands.resolve("自定义策略") == ("", "自定义策略")
    assert bands.resolve(None) == ("", "")


def test_build_sums_trophies_and_keeps_order():
    rows = [match(20, "win"), match(18, "loss", trophies=-12), match(15, "win", trophies=None)]
    card = daily_card.build(rows, excluded=1, day=date(2026, 11, 26), username="tester")
    assert card.wins == 2
    assert card.trophy_change == -7
    assert card.recap["most_kills"]["id"] == "m20"


def test_recent_highlights_show_one_name_for_tied_peak(monkeypatch):
    rows = [match(20, "win", bonds=[{"name": "叙拉古", "layers": 8}, {"name": "伊比利亚", "layers": 8}])]
    card = daily_card.build(rows, excluded=0, day=date(2026, 11, 26), username="tester")
    card.title = "最近 1 局战绩"
    rendered = []
    monkeypatch.setattr(daily_card, "highlight_grid",
                        lambda image, draw, top, title, cells: rendered.extend(cells))

    daily_card.highlights(None, None, 0, card)

    assert rendered[1] == ("单项最高盟约", "8 层", "伊比利亚", daily_card.BOND_ICONS["伊比利亚"])


def test_recent_png_reused_only_for_same_content_and_minute(monkeypatch):
    now = datetime(2026, 11, 26, 20, 0, tzinfo=CHINA)
    monkeypatch.setattr(daily_card, "datetime", SimpleNamespace(now=lambda tz: now))
    monkeypatch.setattr(daily_card, "_record_pngs", OrderedDict())
    calls = []

    def render(card, stamp):
        calls.append((card.username, stamp))
        return bytes([len(calls)])

    monkeypatch.setattr(daily_card, "_render_png", render)
    card = daily_card.build([match(20, "win")], excluded=0, day=now.date(), username="tester")
    card.title = "最近 1 局战绩"

    assert daily_card.render(card) == daily_card.render(card) == b"\x01"
    card.matches[0]["coins"] += 1
    assert daily_card.render(card) == b"\x02"
    now += timedelta(minutes=1)
    assert daily_card.render(card) == b"\x03"


def test_card_palette_matches_website_dark_theme():
    style = Path(__file__).resolve().parents[2] / "frontend" / "src" / "style.css"
    dark_theme = style.read_text(encoding="utf-8").split(":root {", 1)[1].split("}", 1)[0]
    variables = dict(re.findall(r"^\s*--([\w-]+):\s*([^;]+);", dark_theme, re.MULTILINE))
    for name in ("bg", "panel", "inset", "line", "text", "muted", "accent", "win", "loss", "chart-average"):
        assert getattr(daily_card, name.replace("-", "_").upper()) == variables[name]
    assert variables["radius"] == f"{daily_card.RADIUS}px"


@needs_font
def test_render_returns_png_with_content_height():
    rows = [match(hour, "win" if hour % 2 else "loss") for hour in range(8, 23)]
    png = daily_card.render(daily_card.build(rows, excluded=0, day=date(2026, 11, 26), username="tester"))
    image = Image.open(io.BytesIO(png))
    assert image.format == "PNG"
    assert image.width == daily_card.WIDTH
    assert 1200 < image.height < 4000


def test_render_strategy_card_and_text_fallback():
    games = ([{"result": "win", "strategy": "条文修正"}] * 3 + [{"result": "loss", "strategy": "条文修正"}]
             + [{"result": "loss", "strategy": "自定义策略"}])
    card = daily_card.StrategyCard("tester", stats.strategy_stats(games), missing=2)
    assert daily_card.strategy_text(card).splitlines() == [
        "tester · 全部策略胜率", "共 5 局，3 胜 2 负，总胜率 60%",
        "条文修正：75%（3 胜 1 负）", "自定义策略：0%（0 胜 1 负）", "另有 2 局未记录策略，未计入。",
    ]
    if has_font():
        image = Image.open(io.BytesIO(daily_card.render(card)))
        assert image.width == daily_card.WIDTH and 700 < image.height < 1400


@needs_font
def test_render_empty_day():
    png = daily_card.render(daily_card.build([], excluded=2, day=date(2026, 11, 26), username="tester"))
    image = Image.open(io.BytesIO(png))
    assert image.height < 500


def test_paste_icon_aligns_visible_edges_not_padding(tmp_path, monkeypatch):
    # 20×20 图标，可见部分只在右下角 10×6：按可见边缘对齐，透明留白不能把图标挤偏。
    art = Image.new("RGBA", (20, 20))
    art.paste((255, 255, 255, 255), (8, 12, 18, 18))
    art.save(tmp_path / "padded.png")
    monkeypatch.setattr(daily_card, "ART", tmp_path)
    daily_card.icon.cache_clear()
    daily_card.visible_icon.cache_clear()
    try:
        canvas = Image.new("RGB", (100, 100))
        assert daily_card.paste_icon(canvas, "padded.png", 30, 50, 20) == 10 + 8
        assert canvas.getbbox() == (30, 47, 40, 53)

        canvas = Image.new("RGB", (100, 100))
        assert daily_card.paste_icon(canvas, "padded.png", 30, 50, 20, slot=30) == 30 + 8
        assert canvas.getbbox() == (40, 47, 50, 53)
        assert daily_card.paste_icon(canvas, "missing.png", 30, 50, 20, slot=30) == 0
    finally:
        daily_card.icon.cache_clear()
        daily_card.visible_icon.cache_clear()
