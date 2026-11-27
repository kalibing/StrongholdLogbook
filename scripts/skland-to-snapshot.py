"""把森空岛 100 局与小黑盒 14 局合成一份导入快照（含精锐 / 精二信息）。

数据来源：
  skland_history.json        森空岛 history-log 最近 100 局（含 bondInfo / chessSquad / acBossInfo）
  detail_14/*.json           小黑盒详情 14 局（缺少的补录，含 bonds / bosses / chess.golden）
  online/dist/*.json         旧站字典：盟约 / 首领 / 策略 的 ID→中文名，干员与装备名称

用法：
  python scripts/skland-to-snapshot.py --out .local/skland-snapshot.json
"""

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHINA = timezone(timedelta(hours=8))


def load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_maps(legacy_matches: Path, operators: Path, equipment: Path):
    games = load(legacy_matches)
    games = games["matches"] if isinstance(games, dict) else games

    bonds, bosses, strategies = {}, {}, {}
    for game in games:
        for name, _layers, icon in game.get("盟约", []):
            match = re.search(r"bond-([A-Za-z0-9]+?)Ship\.png", icon or "")
            if match:
                bonds.setdefault(match.group(1), name)
        for name, icon in zip(game.get("首领", []), game.get("首领图") or []):
            match = re.search(r"boss-(boss_\d+)\.png", icon or "")
            if match:
                bosses.setdefault(match.group(1), name)
        match = re.search(r"strategy-(band_[A-Za-z0-9]+)\.png", game.get("策略图") or "")
        if match and game.get("策略"):
            strategies.setdefault(match.group(1), game["策略"])

    operator_names = {key: value.get("name", key) for key, value in load(operators).items()}
    equipment_names = {}
    for key, value in load(equipment).items():
        name = value.get("name") if isinstance(value, dict) else None
        if name:
            equipment_names.setdefault(key.split("_e_")[0], name)
            equipment_names.setdefault(key, name)
    return bonds, bosses, strategies, operator_names, equipment_names


def bond_name(bond_id: str, bonds: dict) -> str:
    return bonds.get(bond_id.replace("Ship", ""), bond_id)


def equip_name(equip_id: str, equipment_names: dict) -> str:
    return equipment_names.get(equip_id) or equipment_names.get(equip_id.split("_e_")[0]) or equip_id


def unit(char_id: str, name: str, items: list[str], elite: bool | None, evolve) -> dict:
    entry = {"id": char_id, "name": name, "items": items, "elite": elite}
    if isinstance(evolve, int):
        entry["evolve"] = evolve
    return entry


def convert_skland(game: dict, maps) -> dict:
    bonds_map, bosses_map, strategies, operator_names, equipment_names = maps
    start = datetime.fromtimestamp(int(game["gameStartTs"]), CHINA)
    end = datetime.fromtimestamp(int(game["gameEndTs"]), CHINA)

    squad, operators = [], {}
    for row in game.get("chessSquad", []):
        info = row.get("chessInfo") or {}
        char_id = info.get("charId")
        if not char_id:
            continue
        name = info.get("charName") or operator_names.get(char_id, char_id)
        items = [equip_name(equip["equipId"], equipment_names) for equip in row.get("equips", []) if equip.get("equipId")]
        chess_id = row.get("chessId") or info.get("id")
        golden_id = info.get("goldenChessId")
        golden = chess_id == golden_id if chess_id and golden_id else None
        squad.append(unit(char_id, name, items, golden, info.get("evolvePhase")))
        operators[char_id] = {"id": char_id, "name": name}

    bonds = [
        {"name": bond_name(bond["bondId"], bonds_map), "layers": bond["layer"]}
        for bond in game.get("bondInfo", []) if bond.get("layer")
    ]
    bosses = []
    for boss in game.get("acBossInfo", []):
        name = bosses_map.get(boss["bossId"], boss["bossId"]).replace("（隐藏）", "")
        bosses.append(name + ("（隐藏）" if boss.get("isHidden") else ""))

    record = {
        "external_id": game["id"],
        "played_at": start.isoformat(),
        "protocol": game.get("versionId") or "V3_1",
        "play": "联合模拟" if game.get("modeType") == "MULTI" else "独立模拟",
        "difficulty": game.get("mode") or "",
        "result": "win" if game.get("completeState") == 1 else "loss",
        "strategy": strategies.get(game.get("bandId") or ""),
        "initiator": None,
        "rounds": game.get("passRound"),
        "kills": game.get("killCnt"),
        "coins": game.get("coinCost"),
        "sync_count": game.get("syncCnt"),
        "trophies": (game.get("trophyAfter") or 0) - (game.get("trophyBefore") or 0),
        "duration_seconds": int((end - start).total_seconds()),
        "bonds": bonds,
        "squad": squad,
        "operators": list(operators.values()),
        "bosses": bosses,
    }
    if not (record["rounds"] or record["kills"] or record["coins"]):
        record["suspected_exit"] = True
    return record


def convert_heybox(detail: dict, maps) -> dict:
    _bonds_map, _bosses_map, _strategies, operator_names, equipment_names = maps
    summary = detail.get("summary") or {}
    mode = summary.get("mode") or {}
    strategy = summary.get("strategy") or {}
    start = datetime.fromtimestamp(int(summary["start_time"]), CHINA)
    end = datetime.fromtimestamp(int(summary["end_time"]), CHINA)

    squad, operators = [], {}
    for row in detail.get("chess", []):
        char_id = row.get("char_id")
        if not char_id:
            continue
        name = operator_names.get(char_id, char_id)
        items = [equip_name(equip, equipment_names) for equip in row.get("equips", []) if isinstance(equip, str)]
        squad.append(unit(char_id, name, items, row.get("golden"), row.get("evolve_phase")))
        operators[char_id] = {"id": char_id, "name": name}

    bonds = [
        {"name": bond.get("name") or bond_name(bond.get("id", ""), maps[0]), "layers": bond.get("layer", 0)}
        for bond in summary.get("bonds", []) if bond.get("layer")
    ]
    bosses = []
    for boss in summary.get("bosses", []):
        name = (boss.get("name") or boss.get("id", "")).replace("（隐藏）", "")
        bosses.append(name + ("（隐藏）" if boss.get("hidden") else ""))

    record = {
        "external_id": summary["id"],
        "played_at": start.isoformat(),
        "protocol": "V3_1",
        "play": mode.get("group") or "联合模拟",
        "difficulty": mode.get("name") or "",
        "result": "win" if summary.get("complete") else "loss",
        "strategy": strategy.get("name"),
        "initiator": strategy.get("initiator"),
        "rounds": summary.get("pass_round"),
        "kills": detail.get("kill_cnt"),
        "coins": detail.get("coin_cost"),
        "sync_count": detail.get("sync_cnt"),
        "trophies": summary.get("trophy_gain"),
        "duration_seconds": int((end - start).total_seconds()),
        "bonds": bonds,
        "squad": squad,
        "operators": list(operators.values()),
        "bosses": bosses,
    }
    if not (record["rounds"] or record["kills"] or record["coins"]):
        record["suspected_exit"] = True
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="森空岛 + 小黑盒 → 导入快照")
    parser.add_argument("--history", default="skland_history.json")
    parser.add_argument("--details", default="detail_14")
    parser.add_argument("--legacy-matches", default="online/dist/matches.json")
    parser.add_argument("--operators", default="online/dist/operators.json")
    parser.add_argument("--equipment", default="online/dist/equipment.json")
    parser.add_argument("--out", default=".local/skland-snapshot.json")
    args = parser.parse_args()

    maps = build_maps(Path(args.legacy_matches), Path(args.operators), Path(args.equipment))
    records = {record["external_id"]: record for record in
               (convert_skland(game, maps) for game in load(Path(args.history)))}

    added = 0
    for path in sorted(Path(args.details).glob("*.json")):
        data = load(path)
        detail = data.get("result") or data
        record = convert_heybox(detail, maps)
        if record["external_id"] not in records:
            records[record["external_id"]] = record
            added += 1

    ordered = sorted(records.values(), key=lambda item: item["played_at"])
    payload = {
        "operators": {key: {"name": value} for key, value in maps[3].items()},
        "equipment": {key: {"name": value} for key, value in maps[4].items()},
        "matches": ordered,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    wins = sum(1 for record in ordered if record["result"] == "win")
    elite = sum(unit["elite"] is True for record in ordered for unit in record["squad"])
    print(f"已写入 {out}：{len(ordered)} 局（{wins} 胜，小黑盒补 {added} 局），精锐单位 {elite} 个")


if __name__ == "__main__":
    main()
