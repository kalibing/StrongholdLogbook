from datetime import datetime, timedelta, timezone

from logbook import stats
from logbook.records import CHINA, Filters, read_snapshot


def records(sample_snapshot):
    rows = [row.model_dump() for row in read_snapshot(sample_snapshot)]
    return sorted(rows, key=lambda item: item["played_at"])


def row(when, result="win", coins=None, kills=None, rounds=None, bonds=None, operators=None):
    return {
        "played_at": when, "result": result, "coins": coins, "kills": kills, "rounds": rounds,
        "suspected_exit": False, "bonds": bonds or [], "operators": operators or [],
    }


def test_bond_total_sums_layers():
    assert stats.bond_total({"bonds": [{"name": "维多利亚", "layers": 4}, {"name": "奥术", "layers": 2}]}) == 6
    assert stats.bond_total({"bonds": []}) == 0


def test_peak_keeps_tied_names_sorted():
    rows = [
        {"bonds": [{"name": "奥术", "layers": 5}, {"name": "维多利亚", "layers": 5}]},
        {"bonds": [{"name": "伊比利亚", "layers": 2}]},
    ]
    assert stats.peak(rows) == {"layers": 5, "names": ["奥术", "维多利亚"]}
    assert stats.peak([{"bonds": []}]) is None


def test_operator_stats_counts_unique_matches():
    rows = [
        row(datetime(2026, 11, 1, tzinfo=CHINA), "win", operators=[{"id": "a", "name": "阿米娅"}, {"id": "b", "name": "斯卡蒂"}]),
        row(datetime(2026, 11, 2, tzinfo=CHINA), "loss", operators=[{"id": "a", "name": "阿米娅"}]),
        row(datetime(2026, 11, 3, tzinfo=CHINA), "win"),
    ]
    with_squad, entries = stats.operator_stats(rows)
    assert with_squad == 2
    by_id = {entry["id"]: entry for entry in entries}
    assert by_id["a"]["count"] == 2
    assert by_id["a"]["wins"] == 1
    assert by_id["a"]["losses"] == 1
    assert by_id["a"]["win_rate"] == 0.5
    assert by_id["a"]["usage_rate"] == 1.0
    assert by_id["b"]["usage_rate"] == 0.5


def test_operator_stats_without_squads_is_empty():
    assert stats.operator_stats([row(datetime(2026, 11, 3, tzinfo=CHINA), "win")]) == (0, [])


def test_overview_totals(sample_snapshot):
    rows = records(sample_snapshot)
    summary = stats.overview(rows, excluded=1, scope="all")
    assert summary["matches"] == 6
    assert summary["wins"] == 3
    assert summary["excluded"] == 1
    assert summary["start"] == "2026-11-16"
    assert summary["end"] == "2026-11-20"
    assert summary["max_layers"] == 11
    assert summary["total_coins"] == 451
    assert summary["trophy_change"] == 70
    assert summary["average_coins"] == 75.2
    assert summary["peak"]["layers"] == 7
    assert summary["peak"]["names"] == ["奥术"]
    assert summary["recent_results"] == ["loss", "win", "loss", "win", "win", "loss"]
    assert [bond["name"] for bond in summary["bonds"]] == ["奥术", "维多利亚", "伊比利亚", "不屈"]
    assert summary["bond_layers"] == [
        {"name": "奥术", "layers": 14}, {"name": "维多利亚", "layers": 11},
        {"name": "伊比利亚", "layers": 10}, {"name": "不屈", "layers": 3},
    ]
    assert len(summary["points"]) == 6


def test_overview_day_scope_groups_by_china_date(sample_snapshot):
    rows = records(sample_snapshot)
    summary = stats.overview(rows, excluded=0, scope="day")
    points = summary["points"]
    assert [point["label"] for point in points] == [
        "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20",
    ]
    last = points[-1]
    assert last["coins"] == 170
    assert last["average_coins"] == 85.0
    assert last["layers"] == 11
    assert last["kills"] == 112.5
    assert last["result"] is None
    assert (last["wins"], last["losses"]) == (1, 1)


def test_overview_recent_scope_limits_points(sample_snapshot):
    rows = records(sample_snapshot)
    summary = stats.overview(rows, excluded=0, scope="recent")
    assert len(summary["points"]) == 6
    many = [row(datetime(2026, 11, 1, tzinfo=CHINA) + timedelta(days=index), "win", coins=10) for index in range(15)]
    assert len(stats.overview(many, 0, "recent")["points"]) == 10


def test_overview_without_matches():
    summary = stats.overview([], 0, "all")
    assert summary["matches"] == 0
    assert summary["start"] is None and summary["end"] is None
    assert summary["max_layers"] is None
    assert summary["total_coins"] is None
    assert summary["trophy_change"] is None
    assert summary["bond_layers"] == []
    assert summary["points"] == []


def test_trend_averages_active_bonds_and_leaves_missing_points_empty():
    moment = datetime(2026, 11, 1, tzinfo=CHINA)
    rows = [
        row(moment, bonds=[{"name": "精准", "layers": 8}, {"name": "灵巧", "layers": 4}, {"name": "坚守", "layers": 0}]),
        row(moment, bonds=[{"name": "炎", "layers": 9}]),
        row(moment),
    ]
    matches = list(stats.chart_points(rows, "recent"))
    assert [match["average_bond_layers"] for match in matches] == [6, 9, None]
    assert list(stats.chart_points(rows, "day"))[0]["average_bond_layers"] == 7


def test_day_key_uses_shanghai_timezone():
    moment = datetime(2026, 11, 20, 17, 30, tzinfo=timezone.utc)
    assert stats.day_key({"played_at": moment}) == "2026-11-21"


def test_filters_render_sql():
    filters = Filters(protocol="V3_1", play="独立模拟", start=datetime(2026, 11, 1).date(), include_exits=True)
    sql, params = filters.sql("role-1")
    assert "user_id = %s" in sql
    assert "protocol = %s" in sql and "play = %s" in sql
    assert "NOT suspected_exit" not in sql
    assert params[0] == "role-1"
    assert params[-1].utcoffset() == timedelta(hours=8)
