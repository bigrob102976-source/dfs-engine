"""Milestone 31.1: tests for dfs/availability_filter.py -- the DK
Status/AvgPointsPerGame exclusion pass layered on top of
dfs/eligibility.py's confirmed-starter classification."""

from dfs.availability_filter import apply_availability_filters
from dfs.models import DFSPlayer


def _player(dk_id, name="X", team="BOS", optimizer_eligible=True, dk_status=None, avg_points=5.0, tags=None):
    return DFSPlayer(
        dk_player_id=dk_id, name=name, team=team, player_type="hitter", dk_positions=["OF"], salary=4000,
        optimizer_eligible=optimizer_eligible, dk_status=dk_status, avg_points_per_game_dk=avg_points,
        tags=list(tags or []),
    )


def test_excludes_il_status_by_default():
    p = _player("1", dk_status="IL")
    result = apply_availability_filters([p])
    assert p.optimizer_eligible is False
    assert result.dropped_count == 1
    assert result.excluded[0].reason == "DK Status = IL"


def test_flags_but_does_not_exclude_dtd():
    p = _player("1", dk_status="DTD")
    result = apply_availability_filters([p])
    assert p.optimizer_eligible is True
    assert "DTD" in p.tags
    assert result.dropped_count == 0


def test_excludes_zero_avg_points_by_default():
    p = _player("1", avg_points=0.0)
    result = apply_availability_filters([p])
    assert p.optimizer_eligible is False
    assert result.excluded[0].reason == "AvgPointsPerGame = 0.0"


def test_nonzero_avg_points_never_excluded():
    p = _player("1", avg_points=0.1)
    result = apply_availability_filters([p])
    assert p.optimizer_eligible is True
    assert result.dropped_count == 0


def test_none_avg_points_never_excluded_by_zero_rule():
    # avg_points_per_game_dk=None means "DK didn't report a value" --
    # distinct from a genuine 0.0, and must never be treated the same.
    p = _player("1", avg_points=None)
    result = apply_availability_filters([p])
    assert p.optimizer_eligible is True
    assert result.dropped_count == 0


def test_il_rule_independently_toggleable():
    p = _player("1", dk_status="IL")
    result = apply_availability_filters([p], exclude_il=False)
    assert p.optimizer_eligible is True
    assert result.dropped_count == 0


def test_zero_avg_points_rule_independently_toggleable():
    p = _player("1", avg_points=0.0)
    result = apply_availability_filters([p], exclude_zero_avg_points=False)
    assert p.optimizer_eligible is True
    assert result.dropped_count == 0


def test_applies_to_every_row_regardless_of_prior_eligibility_and_logs_it():
    # A player already ineligible for an unrelated reason (e.g. bench/
    # relief) is still a real, logged IL exclusion if DK says so --
    # "269 raw rows -> ~211 kept" is counted against the FULL pool, not
    # just the subset dfs/eligibility.py already considered eligible.
    p = _player("1", optimizer_eligible=False, dk_status="IL")
    result = apply_availability_filters([p])
    assert p.optimizer_eligible is False
    assert result.dropped_count == 1
    assert result.excluded[0].dk_player_id == "1"


def test_never_removes_a_row_only_narrows_eligibility():
    players = [_player("1", dk_status="IL"), _player("2")]
    apply_availability_filters(players)
    assert len(players) == 2  # both rows still present


def test_kept_and_dropped_counts_sum_to_total_players():
    players = [
        _player("1", dk_status="IL"),
        _player("2", avg_points=0.0),
        _player("3", dk_status="DTD"),
        _player("4"),
    ]
    result = apply_availability_filters(players)
    assert result.dropped_count == 2
    assert result.kept_count == 2
    assert result.kept_count + result.dropped_count == len(players)


def test_il_and_zero_avg_points_overlap_only_counted_once():
    p = _player("1", dk_status="IL", avg_points=0.0)
    result = apply_availability_filters([p])
    assert result.dropped_count == 1
    assert result.excluded[0].reason == "DK Status = IL"  # IL checked first, not double-logged


def test_exclusion_record_carries_name_id_team_reason():
    p = _player("42", name="Some Guy", team="NYY", dk_status="IL")
    result = apply_availability_filters([p])
    record = result.excluded[0].to_dict()
    assert record == {"dk_player_id": "42", "name": "Some Guy", "team": "NYY", "reason": "DK Status = IL"}


def test_empty_pool_returns_zero_counts():
    result = apply_availability_filters([])
    assert result.kept_count == 0
    assert result.dropped_count == 0
    assert result.excluded == []
