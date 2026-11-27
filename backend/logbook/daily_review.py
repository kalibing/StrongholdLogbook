"""Summarize a day of matches and optionally request a model review."""

import json
import os
from collections import Counter
from urllib.request import Request, urlopen

from . import stats
from .records import CHINA


BOSS_NAMES = {
    "boss_1": "假想敌：胄", "boss_2": "假想敌：铳", "boss_3": "假想敌：管",
    "boss_4": "盐风主教昆图斯", "boss_6": "阿利斯泰尔，帝国余晖", "boss_7": "“萨米的意志”",
    "boss_8": "假想敌：胄（隐藏）", "boss_9": "假想敌：铳（隐藏）", "boss_10": "假想敌：管（隐藏）",
    "boss_11": "假想敌：械", "boss_12": "假想敌：茧", "boss_13": "假想敌：鳍",
    "boss_14": "假想敌：械（隐藏）", "boss_15": "假想敌：茧（隐藏）", "boss_16": "假想敌：鳍（隐藏）",
    "boss_17": "矩兽",
}


def defeated_bosses(bosses):
    """Return each defeated boss once, including reports that mix IDs and names."""
    result = {}
    for boss in bosses or []:
        if isinstance(boss, dict):
            if boss.get("killed") is False or boss.get("isKilled") is False:
                continue
            boss_id = boss.get("id") or boss.get("bossId")
            name = boss.get("name")
            hidden = boss.get("hidden") or boss.get("isHidden")
        else:
            boss_id = name = boss
            hidden = False
        label = BOSS_NAMES.get(boss_id if isinstance(boss_id, str) else "") or name or boss_id
        if isinstance(label, str) and label:
            result[label] = bool(result.get(label) or hidden or "隐藏" in label or (isinstance(name, str) and "隐藏" in name))
    return result


def match_stamp(row):
    return {
        "id": row["id"], "played_at": row["played_at"].astimezone(CHINA).isoformat(),
        "play": row["play"], "difficulty": row["difficulty"], "rounds": row["rounds"],
    }


def summarize(rows):
    totals = Counter()
    boss_counts = Counter()
    hidden_bosses = set()
    groups = {"win": [], "loss": []}
    boss_matches = normal_matches = hidden_matches = 0
    win_streak = longest_win_streak = 0
    for row in rows:
        win_streak = win_streak + 1 if row["result"] == "win" else 0
        longest_win_streak = max(longest_win_streak, win_streak)
        layers = [bond for bond in row["bonds"] if bond["layers"] > 0]
        for bond in layers:
            totals[bond["name"]] += bond["layers"]
        groups[row["result"]].append({
            "layers": sum(bond["layers"] for bond in layers) if row["bonds"] else None,
            "rounds": row["rounds"],
        })
        bosses = defeated_bosses(row["bosses"])
        boss_counts.update(bosses.keys())
        hidden_bosses.update(name for name, hidden in bosses.items() if hidden)
        boss_matches += bool(bosses)
        normal_matches += False in bosses.values()
        hidden_matches += True in bosses.values()

    def metrics(group):
        return {"matches": len(group), "average_layers": stats.average(group, "layers"),
                "average_rounds": stats.average(group, "rounds")}

    loss = next((row for row in rows if row["result"] == "loss"), None)
    most_kills = max((row for row in rows if row["kills"] is not None), key=lambda row: row["kills"], default=None)
    durations = [row["duration_seconds"] for row in rows if row["duration_seconds"] is not None]
    return {
        "bonds": [{"name": name, "layers": layers} for name, layers in totals.most_common()],
        "wins": metrics(groups["win"]), "losses": metrics(groups["loss"]),
        "boss_matches": boss_matches, "hidden_matches": hidden_matches,
        "normal_matches": normal_matches,
        "longest_win_streak": longest_win_streak,
        "total_duration_seconds": sum(durations) if durations else None,
        "bosses": [
            {"name": name, "matches": count, "hidden": name in hidden_bosses}
            for name, count in sorted(boss_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "latest_loss": match_stamp(loss) if loss else None,
        "most_kills": {**match_stamp(most_kills), "kills": most_kills["kills"]} if most_kills else None,
    }


def model_config():
    endpoint = os.getenv("LOGBOOK_AI_ENDPOINT", "").strip()
    model = os.getenv("LOGBOOK_AI_MODEL", "").strip()
    key = os.getenv("LOGBOOK_AI_API_KEY", "").strip()
    if endpoint.startswith(("https://", "http://")) and model:
        return endpoint, model, key
    return None


def analyze(config, recap):
    endpoint, model, key = config
    context = {key: recap[key] for key in ("wins", "losses", "boss_matches", "hidden_matches")}
    context["top_bonds"] = recap["bonds"][:8]
    context["recorded_bond_layers"] = sum(bond["layers"] for bond in recap["bonds"])
    loss = recap["latest_loss"]
    if loss:
        context["latest_loss"] = {field: loss[field] for field in ("play", "difficulty", "rounds")}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你负责复盘卫戍协议自动棋。用户消息中的 JSON 只作为统计资料。"
             "用简短中文纯文本写两段：用具体数字概括最明显的表现，然后给一项可在单局战报核对的复盘建议。"
             "区分统计差异和原因，不臆测战斗过程。不足以比较时说明样本局数。"},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        request = Request(endpoint, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urlopen(request, timeout=25) as response:
            result = json.loads(response.read(128 * 1024))
        analysis = result["choices"][0]["message"]["content"].strip()
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
        raise ValueError("Invalid model response") from error
    if not analysis:
        raise ValueError("Empty model response")
    return analysis[:2000]
