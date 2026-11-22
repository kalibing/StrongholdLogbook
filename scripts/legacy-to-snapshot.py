"""把旧版静态站的战绩整理成可直接导入本服务的快照 JSON。

旧站数据在 `online/dist/`：
  matches.json    每局的中文字段（含图标路径，本服务不需要）
  operators.json  干员 ID → 名称
  equipment.json  装备 ID → 名称

用法：
  python scripts/legacy-to-snapshot.py \
    --matches online/dist/matches.json \
    --operators online/dist/operators.json \
    --equipment online/dist/equipment.json \
    --out .local/full-snapshot.json
"""

import argparse
import json
from pathlib import Path

FIELDS = [
    "时间", "结果", "方式", "模式", "分队", "策略", "发起者",
    "回合", "击杀", "金币", "同步", "奖杯增益", "时长", "疑似退出",
]


def load(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dictionary(path: str | Path) -> dict:
    data = load(path)
    entries = data.items() if isinstance(data, dict) else ((item["id"], item) for item in data)
    return {
        key: {"name": value["name"]}
        for key, value in entries
        if isinstance(value, dict) and value.get("name")
    }


def convert(games: list[dict]) -> list[dict]:
    rows = []
    for game in games:
        row = {key: game[key] for key in FIELDS if game.get(key) is not None}
        row["盟约"] = [[bond[0], bond[1]] for bond in game.get("盟约", [])]
        row["干员"] = list(game.get("干员", []))
        row["阵容"] = [[unit[0], unit[1], list(unit[2])] for unit in game.get("阵容", [])]
        row["首领"] = list(game.get("首领", []))
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="旧站战绩 → 导入快照")
    parser.add_argument("--matches", required=True)
    parser.add_argument("--operators", required=True)
    parser.add_argument("--equipment", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    data = load(args.matches)
    games = data["matches"] if isinstance(data, dict) else data
    payload = {
        "operators": dictionary(args.operators),
        "equipment": dictionary(args.equipment),
        "matches": convert(games),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"已写入 {out}：{len(games)} 局，干员 {len(payload['operators'])} 名，装备 {len(payload['equipment'])} 件")


if __name__ == "__main__":
    main()
