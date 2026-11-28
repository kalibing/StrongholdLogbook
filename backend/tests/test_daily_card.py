import io
from datetime import date, datetime
from pathlib import Path
import re

import pytest
from PIL import Image

from logbook import bands, daily_card
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
    monkeypatch.setattr(daily_card, "recent_highlights", lambda image, draw, top, cells: rendered.extend(cells))

    daily_card.highlights(None, None, 0, card)

    assert rendered[1] == ("单项最高盟约", "8 层", "伊比利亚", daily_card.BOND_ICONS["伊比利亚"])


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


@needs_font
def test_render_empty_day():
    png = daily_card.render(daily_card.build([], excluded=2, day=date(2026, 11, 26), username="tester"))
    image = Image.open(io.BytesIO(png))
    assert image.height < 500
