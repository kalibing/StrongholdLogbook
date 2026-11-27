from datetime import date, datetime

from logbook import profile
from logbook.records import CHINA


def row(day, result, play="联合模拟", difficulty="标准模拟", **extra):
    return {
        "played_at": datetime.fromisoformat(f"{day}T20:00:00").replace(tzinfo=CHINA),
        "play": play, "difficulty": difficulty, "result": result,
        "strategy": extra.get("strategy"), "kills": extra.get("kills"),
        "duration_seconds": extra.get("duration"), "bonds": extra.get("bonds", []),
        "operators": extra.get("operators", []),
    }


def test_best_clears_only_count_wins():
    rows = [
        row("2026-11-01", "win", difficulty="险境模拟"),
        row("2026-11-02", "loss", difficulty="终极模拟"),
        row("2026-11-03", "win", play="独立模拟", difficulty="规程等级 7"),
        row("2026-11-04", "win", play="独立模拟", difficulty="规程等级12"),
        row("2026-11-05", "loss", play="独立模拟", difficulty="规程等级 18"),
    ]
    assert profile.best_clears(rows) == {"union": "险境模拟", "solo": "规程等级 12"}


def test_streaks_track_best_and_current_run():
    results = ["win", "win", "loss", "win", "win", "win", "loss", "loss"]
    rows = [row(f"2026-11-{index + 1:02d}", result) for index, result in enumerate(results)]
    assert profile.streaks(rows) == {"best_win": 3, "current": {"result": "loss", "count": 2}}
    assert profile.streaks([]) == {"best_win": 0, "current": None}


def test_summarize_career_and_heatmap():
    rows = [
        row("2026-11-20", "win", kills=100, duration=600, strategy="条文修正",
            bonds=[{"name": "炎", "layers": 6}], operators=[{"id": "char_1", "name": "陈"}]),
        row("2026-11-20", "loss", kills=40, duration=300, strategy="条文修正",
            operators=[{"id": "char_1", "name": "陈"}]),
        row("2026-11-26", "win", play="独立模拟", difficulty="规程等级 3", kills=None),
    ]
    summary = profile.summarize(rows, excluded=1, today=date(2026, 11, 27))
    career = summary["career"]
    assert (career["matches"], career["wins"], career["losses"], career["excluded"]) == (3, 2, 1, 1)
    assert career["active_days"] == 2 and career["play_seconds"] == 900
    assert (career["total_kills"], career["max_kills"], career["max_layers"]) == (140, 100, 6)
    days = summary["activity"]["days"]
    assert len(days) == 7 * (profile.HEATMAP_WEEKS - 1) + 5  # 从 HEATMAP_WEEKS 周前的周一到今天（周五）
    assert date.fromisoformat(days[0]["day"]).weekday() == 0
    assert {entry["day"]: entry["count"] for entry in days if entry["count"]} == {"2026-11-20": 2, "2026-11-26": 1}


def test_summarize_empty():
    summary = profile.summarize([], excluded=0, today=date(2026, 11, 27))
    assert summary["career"]["matches"] == 0 and summary["career"]["win_rate"] is None
    assert summary["best"] == {"union": None, "solo": None} and summary["streaks"]["current"] is None
