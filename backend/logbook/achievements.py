"""把 playerSummary 原始 JSON 归一化成网站用的成就档案。

只依赖 ``data`` 里的字段，缺字段一律降级为 None / 空列表，不抛异常：
同一个接口在不同赛季可能少字段，页面不应该因此整块白屏。

字段语义来自 H5 的 i18n 包（``act1autochess_i18n.*.js``）：
``achievement.BOND``=盟约理解、``seasonBest.coinCost``=单局最多消耗资金 等。
"""

from __future__ import annotations

from datetime import datetime, timezone

DIMENSIONS = (
    ("BOND", "盟约理解"),
    ("KILL", "补救能力"),
    ("CHAR", "人力调度"),
    ("EQUIP", "装备活用"),
    ("COIN", "资金管理"),
    ("DAMAGE", "领袖挑战"),
)
DIMENSION_NAME = dict(DIMENSIONS)

BEST_FIELDS = (
    ("coinCost", "单局最多消耗资金"),
    ("sync", "单局最多晋级次数"),
    ("defeat", "单局最多击败敌方"),
    ("winStreak", "最高连胜"),
    ("help", "单局最多联防击退"),
    ("dmg", "单局最多对领袖伤害"),
)

# 分队里「特殊策略标识」的两种形态：master = 达成精通后挂上的 mark_pro 角标，base = 只有底图。
BADGE_VARIANTS = {
    "master": "精通标识（带 pro 角标）",
    "base": "基础标识（未精通）",
}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _time(value):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def titles_of(data: dict) -> list[dict]:
    season = data.get("season") or {}
    definitions = season.get("titles") or {}
    titles = data.get("title") or {}
    rows = []
    for group, key in (("overview", "list"), ("special", "specialList")):
        for item in titles.get(key) or []:
            identifier = item.get("id") or ""
            definition = definitions.get(identifier) or {}
            kind = definition.get("type") or ""
            rows.append({
                "id": identifier,
                "name": definition.get("txt") or identifier,
                "type": kind,
                "type_name": DIMENSION_NAME.get(kind, kind),
                "rank": _int(definition.get("rank")),
                "group": group,
                "value": _int(item.get("value")),
                "pic_id": definition.get("picId"),
            })
    return rows


def dimensions_of(data: dict, titles: list[dict]) -> list[dict]:
    scores = (data.get("title") or {}).get("achievements") or {}
    result = []
    for key, name in DIMENSIONS:
        owned = [row for row in titles if row["type"] == key]
        result.append({
            "key": key,
            "name": name,
            "score": max(0, min(100, _int(scores.get(key)))),
            "titles": sorted(owned, key=lambda row: (row["rank"], row["id"])),
        })
    return result


def social_of(data: dict) -> dict:
    teammate = data.get("teammate") or {}
    players = data.get("teammatePlayers") or {}
    friend = data.get("friend") or {}
    play = teammate.get("maxPlay") or {}
    win = teammate.get("maxWin") or {}
    teammates: dict[str, dict] = {}
    for metric, record in (("plays", play), ("wins", win)):
        uid = str(record.get("uid") or "")
        if not uid:
            continue
        if uid not in teammates:
            node = players.get(uid) or {}
            teammates[uid] = {
                "uid": uid,
                "nickname": node.get("nickname"),
                "nick_number": node.get("nickNumber"),
                "level": node.get("level"),
                "avatar": node.get("avatar"),
                "name_card": node.get("nameCard"),
                "plays": None,
                "wins": None,
            }
        teammates[uid][metric] = _int(record.get("value"))

    # 游戏内是两张卡：一张「最常共同游玩」、一张「最多胜场」；同一人也要各占一张
    cards: list[dict] = []
    play_uid_str = str(play.get("uid") or "")
    win_uid_str = str(win.get("uid") or "")
    if play_uid_str and play_uid_str in teammates:
        card = dict(teammates[play_uid_str])
        card["wins"] = None
        cards.append(card)
    if win_uid_str and win_uid_str in teammates:
        card = dict(teammates[win_uid_str])
        card["plays"] = None
        cards.append(card)
    return {
        "likes": _int(data.get("beLike")),
        "friends": len(friend.get("friendList") or []),
        "star_friends": [str(uid) for uid in (friend.get("starFriendList") or [])],
        "best_teammate": teammates.get(str(play.get("uid") or "")),
        "top_teammates": cards,
        "others": 0,
    }


def best_of(data: dict) -> list[dict]:
    stats = data.get("max") or {}
    streak = max(_int(stats.get("singleWin")), _int(stats.get("multiWin")))
    rows = []
    for key, label in BEST_FIELDS:
        value = streak if key == "winStreak" else _int(stats.get(key))
        rows.append({"key": key, "label": label, "value": value})
    return rows


def bands_of(data: dict) -> dict:
    band = data.get("band") or {}
    season = data.get("season") or {}
    catalogue = season.get("bands") or {}
    top = []
    for node in band.get("top") or []:
        identifier = node.get("id") or ""
        meta = catalogue.get(identifier) or {}
        top.append({
            "id": identifier,
            "name": node.get("name") or meta.get("name"),
            "effect": meta.get("effectName"),
            "value": _int(node.get("value")),
            "winning_rate": node.get("winningRate"),
            "type": meta.get("type"),
        })
    badges = []
    for node in band.get("pass") or []:
        identifier = node.get("id") or ""
        meta = catalogue.get(identifier) or {}
        mastered = bool(node.get("masterVictor"))
        badges.append({
            "id": identifier,
            "name": node.get("name") or meta.get("name"),
            "effect": meta.get("effectName"),
            "type": meta.get("type"),
            "variant": "master" if mastered else "base",
            "variant_name": BADGE_VARIANTS["master" if mastered else "base"],
            "obtained": mastered,
            "icon": ((meta.get("image") or {}).get("icon")),
        })
    return {
        "top": top,
        "badges": badges,
        "variants": BADGE_VARIANTS,
        "summary": {
            "total": len(badges),
            "mastered": sum(1 for row in badges if row["obtained"]),
            "pending": sum(1 for row in badges if not row["obtained"]),
        },
    }


def season_of(data: dict) -> dict:
    info = ((data.get("season") or {}).get("versionInfo")) or {}
    return {
        "activity": info.get("activityId"),
        "version": info.get("versionId"),
        "name": info.get("seasonName"),
        "year": info.get("seasonYear"),
        "start": _time(info.get("startTime")),
        "end": _time(info.get("endTime")),
        "offseason": bool(info.get("isOffseason")),
    }


def modes_of(data: dict) -> dict:
    mode = data.get("mode") or {}
    single = mode.get("single") or {}
    multi = mode.get("multi") or {}
    return {
        "single": {
            "battle": _int(single.get("battle")),
            "win": _int(single.get("win")),
            "hard_mode": single.get("hardModeName"),
            "hard_win": _int(single.get("hardWin")),
        },
        "multi": {
            "battle": _int(multi.get("battle")),
            "win": _int(multi.get("win")),
            "hard_win": _int(multi.get("hardWin")),
            "second_hard_win": _int(multi.get("secondHardWin")),
        },
    }


def normalize(data: dict, fetched_at: str | None = None) -> dict:
    """原始 playerSummary.data → 网站用档案。"""
    player = data.get("player") or {}
    trophy = data.get("trophy")
    level = data.get("trophyLevel")
    career = ((data.get("careerTrophy") or {}).get("act3autochess")) or {}
    titles = titles_of(data)
    return {
        "player": {
            "uid": str(player.get("uid") or ""),
            "nickname": player.get("nickname"),
            "nick_number": player.get("nickNumber"),
            "level": player.get("level"),
            "avatar": player.get("avatar"),
            "name_card": player.get("nameCard"),
        },
        "trophy": {
            "total": _int(trophy),
            "level": _int(level),
            "icon": career.get("iconId"),
        },
        "likes": _int(data.get("beLike")),
        "dimensions": dimensions_of(data, titles),
        "titles": titles,
        "social": social_of(data),
        "modes": modes_of(data),
        "best": best_of(data),
        "bands": bands_of(data),
        "season": season_of(data),
        "fetched_at": fetched_at or datetime.now(timezone.utc).isoformat(),
    }
