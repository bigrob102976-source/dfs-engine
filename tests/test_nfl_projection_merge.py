"""NFL M4 -- targeted tests for nfl/projection_merge.py. Matching
strategy under test: DraftKings player_id only -- the sole real,
unambiguous identity available for M4 (see that module's own docstring
for why no name-based fallback exists yet)."""

from nfl.models import NflPlayer
from nfl.projection_merge import merge_projections, validate_projections
from nfl.projection_models import BIG_MONEY_NATIVE, NflProjectionRecord

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


def _record(pid, name, position, projection, team="BUF", opponent="HOU", draft_group_id=DG_ID, provenance=BIG_MONEY_NATIVE):
    return NflProjectionRecord(
        sport="NFL", draft_group_id=draft_group_id, canonical_player_id=pid, draftkings_player_id=pid,
        draftable_ids=[f"d{pid}"], name=name, position=position, team=team, opponent=opponent,
        projection=projection, source=BIG_MONEY_NATIVE, source_provenance=provenance,
        model_name="test-model", model_version="v0", generated_at="2026-09-13T12:00:00Z",
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
    records = [_record("1", "QB One", "QB", 18.5), _record("2", "RB One", "RB", 14.2)]
    result = merge_projections(pool, records)
    assert set(result.matched) == {"1", "2"}
    assert result.unmatched_records == []
    assert sorted(result.unmatched_pool) == ["3", "4"]
    assert result.projections_by_player_id["1"].projection == 18.5


def test_unmatched_record_not_in_pool():
    pool = _pool()
    records = [_record("999", "Ghost Player", "QB", 10.0)]
    result = merge_projections(pool, records)
    assert result.matched == []
    assert result.unmatched_records == ["999"]


def test_dst_matches_by_stable_player_id_like_a_person():
    pool = _pool()
    records = [_record("4", "Team DST", "DST", 7.5)]
    result = merge_projections(pool, records)
    assert result.matched == ["4"]


def test_validate_projections_passes_on_clean_records():
    pool = _pool()
    records = [_record("1", "QB One", "QB", 18.5), _record("4", "Team DST", "DST", 7.5)]
    result = validate_projections(pool, records, DG_ID, BIG_MONEY_NATIVE)
    assert result.passed is True
    assert result.total_pool_players == 4
    assert result.projected_players == 2
    assert result.missing_players == 2
    assert result.match_rate == 0.5
    assert result.position_projected_counts == {"QB": 1, "DST": 1}


def test_validate_rejects_nan_projection():
    pool = _pool()
    records = [_record("1", "QB One", "QB", float("nan"))]
    result = validate_projections(pool, records, DG_ID, BIG_MONEY_NATIVE)
    assert result.passed is False
    assert any("NaN" in f.message for f in result.findings)


def test_validate_rejects_infinite_projection():
    pool = _pool()
    records = [_record("1", "QB One", "QB", float("inf"))]
    result = validate_projections(pool, records, DG_ID, BIG_MONEY_NATIVE)
    assert result.passed is False
    assert any("infinite" in f.message for f in result.findings)


def test_validate_rejects_negative_projection():
    pool = _pool()
    records = [_record("1", "QB One", "QB", -5.0)]
    result = validate_projections(pool, records, DG_ID, BIG_MONEY_NATIVE)
    assert result.passed is False
    assert any("negative" in f.message.lower() for f in result.findings)


def test_none_projection_never_flagged_as_invalid():
    """A record with projection=None (not yet scored) is not a
    validation error -- missing is a legitimate, explicit state."""
    pool = _pool()
    records = [_record("1", "QB One", "QB", None)]
    result = validate_projections(pool, records, DG_ID, BIG_MONEY_NATIVE)
    assert result.passed is True


def test_validate_rejects_wrong_position():
    pool = _pool()
    records = [_record("1", "QB One", "RB", 10.0)]  # pool has this player as QB
    result = validate_projections(pool, records, DG_ID, BIG_MONEY_NATIVE)
    assert result.passed is False
    assert any("position" in f.message for f in result.findings)


def test_validate_rejects_wrong_draft_group():
    pool = _pool()
    records = [_record("1", "QB One", "QB", 10.0, draft_group_id=999)]
    result = validate_projections(pool, records, DG_ID, BIG_MONEY_NATIVE)
    assert result.passed is False
    assert any("draft_group_id" in f.message for f in result.findings)


def test_validate_rejects_wrong_provenance():
    pool = _pool()
    records = [_record("1", "QB One", "QB", 10.0, provenance="SOMETHING_ELSE")]
    result = validate_projections(pool, records, DG_ID, BIG_MONEY_NATIVE)
    assert result.passed is False
    assert any("source_provenance" in f.message for f in result.findings)


def test_validate_rejects_duplicate_player_source_version():
    pool = _pool()
    r1 = _record("1", "QB One", "QB", 10.0)
    r2 = _record("1", "QB One", "QB", 12.0)  # same player, source, version -- duplicate
    result = validate_projections(pool, [r1, r2], DG_ID, BIG_MONEY_NATIVE)
    assert result.passed is False
    assert any("duplicate" in f.message.lower() for f in result.findings)
