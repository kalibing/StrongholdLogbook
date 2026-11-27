from collections import defaultdict
from itertools import groupby

from .records import CHINA


def average(rows, field):
    values = [row[field] for row in rows if row[field] is not None]
    return round(sum(values) / len(values), 1) if values else None


def bond_total(row):
    return sum(bond["layers"] for bond in row["bonds"])


def active_bonds(rows):
    return (bond for row in rows for bond in row["bonds"] if bond["layers"] > 0)


def peak(rows):
    bonds = list(active_bonds(rows))
    if not bonds:
        return None
    layers = max(bond["layers"] for bond in bonds)
    names = sorted({bond["name"] for bond in bonds if bond["layers"] == layers})
    return {"layers": layers, "names": names}


def operator_stats(rows):
    counts = {}
    with_squad = sum(bool(row["operators"]) for row in rows)
    for row in rows:
        for operator in row["operators"]:
            uid = operator["id"]
            entry = counts.setdefault(uid, {**operator, "count": 0, "wins": 0})
            entry["name"] = operator["name"]
            entry["count"] += 1
            entry["wins"] += row["result"] == "win"
    for entry in counts.values():
        entry["losses"] = entry["count"] - entry["wins"]
        entry["usage_rate"] = entry["count"] / with_squad
        entry["win_rate"] = entry["wins"] / entry["count"]
    return with_squad, list(counts.values())


def day_key(row):
    return row["played_at"].astimezone(CHINA).date().isoformat()


def chart_points(rows, scope):
    if scope == "day":
        for day, records in groupby(rows, key=day_key):
            group = list(records)
            coins = [r["coins"] for r in group if r["coins"] is not None]
            wins = sum(r["result"] == "win" for r in group)
            yield {
                "label": day, "result": None, "wins": wins, "losses": len(group) - wins,
                "layers": max(map(bond_total, group)),
                "peak": peak(group), "average_bond_layers": average(active_bonds(group), "layers"),
                "coins": sum(coins) if coins else None,
                "average_coins": average(group, "coins"),
                "kills": average(group, "kills"), "rounds": average(group, "rounds"),
            }
        return
    for row in (rows[-10:] if scope == "recent" else rows):
        yield {
            "match_id": row.get("id"),
            "label": row["played_at"].astimezone(CHINA).isoformat(), "result": row["result"],
            "layers": bond_total(row), "peak": peak([row]),
            "average_bond_layers": average(active_bonds([row]), "layers"), "coins": row["coins"],
            "kills": row["kills"], "rounds": row["rounds"],
        }


def overview(rows, excluded, scope):
    with_squad, operators = operator_stats(rows)
    bonds = defaultdict(list)
    for bond in active_bonds(rows):
        bonds[bond["name"]].append(bond["layers"])
    bond_totals = {name: sum(layers) for name, layers in bonds.items()}
    ordered_bonds = sorted(bonds, key=lambda name: (-len(bonds[name]), -bond_totals[name], name))
    coins = [row["coins"] for row in rows if row["coins"] is not None]
    trophies = [change for row in rows if (change := row.get("trophies")) is not None]
    return {
        "matches": len(rows),
        "wins": sum(row["result"] == "win" for row in rows),
        "excluded": excluded,
        "start": day_key(rows[0]) if rows else None,
        "end": day_key(rows[-1]) if rows else None,
        "recent_results": [row["result"] for row in rows[-10:]],
        "max_layers": max(map(bond_total, rows), default=None),
        "peak": peak(rows),
        "total_coins": sum(coins) if coins else None,
        "trophy_change": sum(trophies) if trophies else None,
        "average_coins": average(rows, "coins"),
        "with_squad": with_squad,
        "operators": sorted(operators, key=lambda row: (-row["count"], row["name"]))[:6],
        "bonds": [{"name": name, "count": len(bonds[name]),
                   "average": round(bond_totals[name] / len(bonds[name]), 1)} for name in ordered_bonds[:8]],
        "bond_layers": [{"name": name, "layers": layers}
                        for name, layers in sorted(bond_totals.items(), key=lambda item: (-item[1], item[0]))],
        "points": list(chart_points(rows, scope)),
    }
