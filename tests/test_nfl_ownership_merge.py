"""NFL M12 -- targeted tests for nfl/ownership_merge.py. Matching
strategy under test: DraftKings player_id only -- mirrors
tests/test_nfl_projection_merge.py's own discipline for why no name
fallback exists."""

from nfl.models import NflPlayer
from nfl.ownership_merge import merge_ownership
from nfl.ownership_models import NflOwnershipRecord

DG_ID = 151307
DATE = "2026-09-13"


def _player(pid, name, position, team="BUF", opponent="HOU"):
    return NflPlayer(
        draftkings_player_id=pid, draftkings_dk_id=f"dk{pid}", draftable_ids=[f"d{pid}"], name=name,
        first_name=name, last_name=None, is_team_entity=(position == "DST"), position=position,
        roster_slots=[position] if position in ("QB", "DST") else [position, "FLEX"],
        team=team, opponent=opponent, game_id="100", game_description=f"{opponent} @ {team}",
        game_start_time="2026-09-13T17:00:00Z", salary=6000, status="None", injury_status=None,
        draft_group_id=DG_ID, slate_date=DATE, slate_name="Featured", source="draftkings_unofficial",
        source_provenance="DRAFTKINGS_UNOFFICIAL_LIVE",
    )


def _record(pid, name, position, ownership, team="BUF", opponent="HOU"):
    return NflOwnershipRecord(
        sport="NFL", draft_group_id=DG_ID, slate_date=DATE, draftkings_player_id=pid, canonical_player_id=pid,
        name=name, position=position, team=team, opponent=opponent, ownership_projection=ownership, ownership_rank=1,
        source="BIG_MONEY_NATIVE_OWNERSHIP_V1", source_provenance="TEST_PROVENANCE",
        method="deterministic_estimator", model_version="nfl_ownership_v1", generated_at="2026-09-13T12:00:00Z",
    )


def _pool():
    return [
        _player("1", "QB One", "QB"),
        _player("2", "RB One", "RB"),
        _player("3", "WR One", "WR"),
        _player("4", "Team DST", "DST"),
    ]


def test_matched_by_draftkings_player_id():
    pool = _pool()
    records = [_record("1", "QB One", "QB", 88.0), _record("2", "RB One", "RB", 40.0)]
    result = merge_ownership(pool, records)
    assert set(result.matched) == {"1", "2"}
    assert result.unmatched_records == []
    assert sorted(result.unmatched_pool) == ["3", "4"]
    assert result.ownership_by_player_id["1"].ownership_projection == 88.0


def test_unmatched_record_reported_never_silently_dropped():
    pool = _pool()
    records = [_record("999", "Ghost Player", "QB", 50.0)]
    result = merge_ownership(pool, records)
    assert result.matched == []
    assert result.unmatched_records == ["999"]


def test_pool_player_with_no_ownership_record_is_unmatched_not_zero():
    """A pool player with no usable projection never gets an ownership
    record built for them (nfl/ownership_model.py's contract) -- merge
    reports them as unmatched_pool, and the caller must render that as
    null/missing, never coerce to 0%."""
    pool = _pool()
    records = [_record("1", "QB One", "QB", 88.0)]
    result = merge_ownership(pool, records)
    assert "2" in result.unmatched_pool
    assert "2" not in result.ownership_by_player_id


def test_same_name_different_ids_never_cross_matched():
    """Two different real players can share a display name -- the join
    must never fall back to name, only DraftKings' own stable id."""
    pool = [_player("1", "John Smith", "WR"), _player("2", "John Smith", "RB")]
    records = [_record("1", "John Smith", "WR", 12.0)]
    result = merge_ownership(pool, records)
    assert result.matched == ["1"]
    assert "2" in result.unmatched_pool
    assert result.ownership_by_player_id["1"].position == "WR"
