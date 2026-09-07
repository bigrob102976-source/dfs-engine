"""NFL M6B -- targeted tests for historical_nfl/identity_resolve.py.
Uses minimal real-shaped NflPlayer fixtures (mirrors tests/test_nfl_
player_research_join.py's fixture style)."""

from nfl.models import NflPlayer
from historical_nfl.identity_models import STATUS_MATCHED, STATUS_UNMATCHED
from historical_nfl.identity_resolve import (
    build_offense_crosswalk_rows,
    classify_history_availability,
    resolve_dst_pool,
    resolve_offense_pool,
    summarize_by_position,
)

DG_ID = 151307
DATE = "2026-09-13"


def _player(pid, name, position, team, draftable_id="d1"):
    return NflPlayer(
        draftkings_player_id=pid, draftkings_dk_id=f"dk{pid}", draftable_ids=[draftable_id], name=name,
        first_name=name.split()[0], last_name=name.split()[-1], is_team_entity=(position == "DST"),
        position=position, roster_slots=[position], team=team, opponent="OPP", game_id="g1",
        game_description="OPP @ " + team, game_start_time="2026-09-13T17:00:00Z", salary=6000,
        status="None", injury_status=None, draft_group_id=DG_ID, slate_date=DATE, slate_name="Featured",
        source="draftkings_unofficial", source_provenance="DRAFTKINGS_UNOFFICIAL_LIVE",
    )


def test_resolve_offense_pool_skips_dst():
    players = [_player("1", "Josh Allen", "QB", "BUF"), _player("2", "Eagles", "DST", "PHI")]
    roster_rows = [{"gsis_id": "00-0001", "full_name": "Josh Allen", "team": "BUF", "position": "QB"}]
    results = resolve_offense_pool(players, {}, roster_rows)
    assert len(results) == 1
    assert results[0].dk_position == "QB"


def test_resolve_dst_pool_only_dst_uses_team_identity():
    players = [_player("1", "Josh Allen", "QB", "BUF"), _player("2", "Eagles", "DST", "PHI")]
    rows = resolve_dst_pool(players, {})
    assert len(rows) == 1
    assert rows[0].canonical_player_id == "dst:PHI"
    assert rows[0].is_team_entity is True


def test_build_offense_crosswalk_rows_wires_through():
    players = [_player("1", "Josh Allen", "QB", "BUF")]
    roster_rows = [{"gsis_id": "00-0001", "full_name": "Josh Allen", "team": "BUF", "position": "QB"}]
    results = resolve_offense_pool(players, {}, roster_rows)
    rows = build_offense_crosswalk_rows(results, {})
    assert rows[0].canonical_player_id == "gsis:00-0001"
    assert rows[0].draftkings_player_id == "1"


def test_summarize_by_position_counts_and_match_rate():
    players = [
        _player("1", "Josh Allen", "QB", "BUF"),
        _player("2", "Nobody Real", "QB", "BUF"),
    ]
    roster_rows = [{"gsis_id": "00-0001", "full_name": "Josh Allen", "team": "BUF", "position": "QB"}]
    results = resolve_offense_pool(players, {}, roster_rows)
    summary = summarize_by_position(results, {})
    assert summary["QB"]["total"] == 2
    assert summary["QB"]["matched"] == 1
    assert summary["QB"]["unmatched"] == 1
    assert summary["QB"]["match_rate"] == 50.0


def test_classify_history_availability_splits_matched_players():
    players = [_player("1", "Josh Allen", "QB", "BUF"), _player("2", "New Rookie", "QB", "BUF")]
    roster_rows = [
        {"gsis_id": "00-0001", "full_name": "Josh Allen", "team": "BUF", "position": "QB"},
        {"gsis_id": "00-0099", "full_name": "New Rookie", "team": "BUF", "position": "QB"},
    ]
    results = resolve_offense_pool(players, {}, roster_rows)
    assert all(r.status == STATUS_MATCHED for r in results)
    hist = classify_history_availability(results, historical_gsis_ids={"00-0001"})
    assert hist == {"identity_found_with_history": 1, "identity_found_no_history": 1}


def test_classify_history_availability_ignores_unmatched_players():
    players = [_player("1", "Totally Unknown", "QB", "BUF")]
    results = resolve_offense_pool(players, {}, [])
    assert results[0].status == STATUS_UNMATCHED
    hist = classify_history_availability(results, historical_gsis_ids={"00-0001"})
    assert hist == {"identity_found_with_history": 0, "identity_found_no_history": 0}
