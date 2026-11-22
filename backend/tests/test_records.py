from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from logbook.records import MatchInput, read_snapshot


def test_modern_snapshot_keeps_every_field(sample_snapshot):
    rows = read_snapshot(sample_snapshot)
    assert [row.external_id.rsplit("-", 1)[-1] for row in rows] == [
        "1794132482", "1794134656", "1794137001", "1794140944", "1794143208", "1794146622",
    ]
    first = rows[0]
    assert first.result == "win"
    assert first.protocol == "V3_1"
    assert first.scenario == "维多利亚分队"
    assert first.bonds[0].name == "维多利亚"
    assert first.bonds[0].layers == 6
    assert first.squad[0].items == ["锋锐之矛", "共振核心"]
    assert first.suspected_exit is False


def test_suspected_exit_is_inferred_from_empty_match(sample_snapshot):
    rows = read_snapshot(sample_snapshot)
    empty = next(row for row in rows if row.external_id.endswith("1794140944"))
    assert empty.suspected_exit is True
    assert empty.rounds == empty.kills == empty.coins == 0


def test_operators_fall_back_to_squad_and_are_deduplicated(sample_snapshot):
    rows = read_snapshot(sample_snapshot)
    first = rows[0]
    assert {operator.id for operator in first.operators} == {unit.id for unit in first.squad}
    assert len(first.operators) == len({operator.id for operator in first.operators})


def test_explicit_operators_win_over_squad(sample_snapshot):
    rows = read_snapshot(sample_snapshot)
    no_squad = next(row for row in rows if row.external_id.endswith("1794143208"))
    assert no_squad.squad == []
    assert [operator.name for operator in no_squad.operators] == ["令", "阿米娅", "安洁莉娜"]


def test_legacy_snapshot_is_upgraded(fixtures):
    import json

    raw = json.loads((fixtures / "legacy-snapshot.json").read_text(encoding="utf-8"))
    rows = read_snapshot(raw)
    assert len(rows) == 2
    won, lost = rows
    assert (won.result, won.play, won.difficulty) == ("win", "独立模拟", "规程等级 5")
    assert won.external_id.startswith("archive-")
    assert won.played_at.utcoffset().total_seconds() == 8 * 3600
    assert won.squad[0].items == ["锋锐之矛"]
    assert won.operators[0].name == "浊心斯卡蒂"
    assert lost.suspected_exit is True
    assert lost.strategy is None and lost.initiator is None
    assert lost.trophies == 0 and lost.duration_seconds is None


def test_legacy_external_id_is_stable(fixtures):
    import json

    raw = json.loads((fixtures / "legacy-snapshot.json").read_text(encoding="utf-8"))
    first = read_snapshot(raw)[0].external_id
    second = read_snapshot(raw)[0].external_id
    assert first == second


def test_top_level_list_is_accepted(sample_snapshot):
    assert len(read_snapshot(sample_snapshot["matches"])) == 6


@pytest.mark.parametrize("payload", [{}, {"matches": []}, {"matches": "x"}, [], [{}], {"matches": [{"时间": "nope"}]}])
def test_invalid_payloads_are_rejected(payload):
    with pytest.raises(ValueError):
        read_snapshot(payload)


def test_duplicate_external_ids_are_rejected(sample_snapshot):
    payload = {"matches": [sample_snapshot["matches"][0], sample_snapshot["matches"][0]]}
    with pytest.raises(ValueError, match="重复"):
        read_snapshot(payload)


def test_dictionary_shape_is_validated():
    with pytest.raises(ValueError, match="字典"):
        read_snapshot({"operators": [], "matches": [{"external_id": "x"}]})


def test_played_at_requires_timezone():
    with pytest.raises(ValidationError):
        MatchInput(
            external_id="e1", played_at=datetime(2026, 11, 1, 8, 0),
            play="独立模拟", difficulty="规程等级 1", result="win",
        )


def test_played_at_accepts_offset():
    row = MatchInput(
        external_id="e1", played_at=datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc),
        play="独立模拟", difficulty="规程等级 1", result="loss",
    )
    assert row.protocol == "V3_1"
    assert row.suspected_exit is False


def test_result_and_limits_are_enforced():
    with pytest.raises(ValidationError):
        MatchInput(
            external_id="e1", played_at=datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc),
            play="独立模拟", difficulty="规程等级 1", result="draw",
        )
    with pytest.raises(ValidationError):
        MatchInput(
            external_id="e1", played_at=datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc),
            play="独立模拟", difficulty="规程等级 1", result="win", kills=-1,
        )
