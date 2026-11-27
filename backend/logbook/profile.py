"""战绩总览「生涯档案」：把筛选范围内的对局汇总成最高通关、连胜、生涯纪录与活跃度。"""

from datetime import date, timedelta
import re

from . import stats
from .records import CHINA

UNION_ORDER = ("标准模拟", "险境模拟", "绝境模拟", "终极模拟")
HEATMAP_WEEKS = 53


def _level(difficulty: str) -> int | None:
    match = re.fullmatch(r"规程等级\s*(\d{1,2})", difficulty or "")
    return int(match[1]) if match else None


def best_clears(rows) -> dict:
    """联合模拟取通关过的最高难度，独立模拟取通关过的最高规程等级。"""
    wins = [row for row in rows if row["result"] == "win"]
    union = [UNION_ORDER.index(row["difficulty"]) for row in wins
             if row["play"] == "联合模拟" and row["difficulty"] in UNION_ORDER]
    levels = [level for row in wins if row["play"] == "独立模拟" and (level := _level(row["difficulty"])) is not None]
    return {
        "union": UNION_ORDER[max(union)] if union else None,
        "solo": f"规程等级 {max(levels)}" if levels else None,
    }


def streaks(rows) -> dict:
    """rows 按时间正序：最长连胜，以及当前（最近一局起）的连续胜 / 负。"""
    best = run = 0
    for row in rows:
        run = run + 1 if row["result"] == "win" else 0
        best = max(best, run)
    current = None
    if rows:
        last = rows[-1]["result"]
        count = 0
        for row in reversed(rows):
            if row["result"] != last:
                break
            count += 1
        current = {"result": last, "count": count}
    return {"best_win": best, "current": current}


def heatmap(rows, today: date) -> dict:
    """最近 HEATMAP_WEEKS 周的每日局数；从那一周的周一开始，到 today 为止。"""
    start = today - timedelta(days=today.weekday() + 7 * (HEATMAP_WEEKS - 1))
    counts: dict[str, int] = {}
    for row in rows:
        day = row["played_at"].astimezone(CHINA).date()
        if start <= day <= today:
            counts[day.isoformat()] = counts.get(day.isoformat(), 0) + 1
    days = [(start + timedelta(days=offset)) for offset in range((today - start).days + 1)]
    return {"start": start.isoformat(), "end": today.isoformat(),
            "days": [{"day": day.isoformat(), "count": counts.get(day.isoformat(), 0)} for day in days]}


def summarize(rows, excluded: int, today: date) -> dict:
    """rows：未被排除的对局，按 played_at 正序。"""
    wins = sum(row["result"] == "win" for row in rows)
    durations = [row["duration_seconds"] for row in rows if row["duration_seconds"] is not None]
    kills = [row["kills"] for row in rows if row["kills"] is not None]
    days = {stats.day_key(row) for row in rows}
    return {
        "career": {
            "matches": len(rows),
            "wins": wins,
            "losses": len(rows) - wins,
            "win_rate": wins / len(rows) if rows else None,
            "excluded": excluded,
            "first_day": stats.day_key(rows[0]) if rows else None,
            "last_day": stats.day_key(rows[-1]) if rows else None,
            "active_days": len(days),
            "play_seconds": sum(durations) if durations else None,
            "total_kills": sum(kills) if kills else None,
            "max_kills": max(kills, default=None),
            "max_layers": max(map(stats.bond_total, rows), default=None),
        },
        "streaks": streaks(rows),
        "best": best_clears(rows),
        "activity": heatmap(rows, today),
    }
