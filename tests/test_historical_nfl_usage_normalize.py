"""NFL M6C -- targeted tests for historical_nfl/usage_normalize.py.
Synthetic fixtures, real field names -- the real-data proof is the M6C
final report's live 2025 Week 1 run."""

from historical_nfl.usage_normalize import GOAL_LINE_YARDLINE_100, RED_ZONE_YARDLINE_100, build_usage_records

SEASON, WEEK = 2025, 1
FETCHED_AT = "2026-08-31T00:00:00+00:00"


def _ws_row(gsis_id, team="PHI", opponent="DAL", position="WR", targets=5, carries=0, receptions=3, game_id="g1"):
    return {
        "player_id": gsis_id, "team": team, "opponent_team": opponent, "position": position,
        "game_id": game_id, "targets": targets, "carries": carries, "receptions": receptions,
    }


def test_target_share_computed_against_team_total():
    rows = [_ws_row("00-1", targets=6), _ws_row("00-2", targets=4)]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    by_id = {r.gsis_id: r for r in records}
    assert by_id["00-1"].target_share == 0.6
    assert by_id["00-2"].target_share == 0.4


def test_target_share_none_when_team_has_zero_total_targets():
    rows = [_ws_row("00-1", targets=0)]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    assert records[0].target_share is None


def _pbp_rush(team, rusher, kneel=0, yardline_100=50.0):
    return {"posteam": team, "rush_attempt": 1, "qb_kneel": kneel, "rusher_player_id": rusher, "receiver_player_id": None, "yardline_100": yardline_100}


def _pbp_pass(team, receiver, yardline_100=50.0):
    return {"posteam": team, "rush_attempt": 0, "qb_kneel": 0, "rusher_player_id": None, "receiver_player_id": receiver, "yardline_100": yardline_100}


def test_carry_share_excludes_kneels_from_both_numerator_and_denominator():
    rows = [_ws_row("00-1", carries=3)]  # raw stat says 3 (would include a kneel if any)
    pbp = [
        _pbp_rush("PHI", "00-1"), _pbp_rush("PHI", "00-1"),  # 2 real non-kneel carries
        _pbp_rush("PHI", "00-1", kneel=1),  # a kneel -- must not count
        _pbp_rush("PHI", "00-9"),  # a teammate's carry, part of the team denominator
    ]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], pbp, {}, {}, FETCHED_AT)
    assert records[0].carries == 3  # raw stat preserved unmodified
    assert records[0].carry_share == round(2 / 3, 4)  # PBP-derived, kneel excluded from both sides


def test_carry_share_is_real_zero_not_none_for_a_non_rusher():
    rows = [_ws_row("00-1", carries=0)]
    pbp = [_pbp_rush("PHI", "00-9")]  # a teammate carries; 00-1 never does
    records, _ = build_usage_records(SEASON, WEEK, rows, [], pbp, {}, {}, FETCHED_AT)
    assert records[0].carry_share == 0.0
    assert records[0].carry_share is not None


def test_carry_share_none_when_team_has_no_pbp_carries_at_all():
    rows = [_ws_row("00-1", carries=0)]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    assert records[0].carry_share is None


def test_red_zone_and_goal_line_use_correct_yardline_thresholds():
    assert RED_ZONE_YARDLINE_100 == 20
    assert GOAL_LINE_YARDLINE_100 == 5
    rows = [_ws_row("00-1")]
    pbp = [
        _pbp_rush("PHI", "00-1", yardline_100=18.0),  # red zone, not goal line
        _pbp_rush("PHI", "00-1", yardline_100=3.0),   # red zone AND goal line
        _pbp_rush("PHI", "00-1", yardline_100=30.0),  # neither
        _pbp_pass("PHI", "00-1", yardline_100=10.0),  # red-zone target
    ]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], pbp, {}, {}, FETCHED_AT)
    r = records[0]
    assert r.red_zone_carries == 2
    assert r.goal_line_carries == 1
    assert r.red_zone_targets == 1


def test_red_zone_fields_are_real_zero_not_none_when_player_never_touches_it():
    rows = [_ws_row("00-1")]
    pbp = [_pbp_rush("PHI", "00-9", yardline_100=10.0)]  # only a teammate touches the red zone
    records, _ = build_usage_records(SEASON, WEEK, rows, [], pbp, {}, {}, FETCHED_AT)
    r = records[0]
    assert r.red_zone_carries == 0
    assert r.goal_line_carries == 0
    assert r.red_zone_targets == 0


def test_goal_line_kneel_excluded():
    rows = [_ws_row("00-1")]
    pbp = [_pbp_rush("PHI", "00-1", kneel=1, yardline_100=2.0)]  # a kneel at the goal line -- not real usage
    records, _ = build_usage_records(SEASON, WEEK, rows, [], pbp, {}, {}, FETCHED_AT)
    assert records[0].goal_line_carries == 0


def _snap_row(pfr_id, offense_snaps=50.0, offense_pct=0.8, defense_snaps=0.0, st_snaps=5.0):
    return {"pfr_player_id": pfr_id, "offense_snaps": offense_snaps, "offense_pct": offense_pct, "defense_snaps": defense_snaps, "st_snaps": st_snaps}


def test_snap_fields_populated_via_real_pfr_gsis_bridge():
    rows = [_ws_row("00-1")]
    snaps = [_snap_row("SmitJo00")]
    bridge = {"SmitJo00": "00-1"}
    records, _ = build_usage_records(SEASON, WEEK, rows, snaps, [], bridge, {}, FETCHED_AT)
    r = records[0]
    assert r.offensive_snaps == 50.0
    assert r.snap_share == 0.8  # sourced from PFR's own offense_pct, not derived


def test_snap_fields_stay_none_when_bridge_cannot_resolve_the_player():
    """Unresolved snap identity is a real, honest limitation (~19% of
    real 2025 rows in the M6C audit) -- never guessed via name matching."""
    rows = [_ws_row("00-1")]
    snaps = [_snap_row("UnknownPfr00")]
    records, _ = build_usage_records(SEASON, WEEK, rows, snaps, [], {}, {}, FETCHED_AT)
    assert records[0].offensive_snaps is None
    assert records[0].snap_share is None


def test_canonical_player_id_resolved_through_crosswalk():
    rows = [_ws_row("00-1")]
    gsis_to_canonical = {"00-1": "gsis:00-1"}
    records, unresolved = build_usage_records(SEASON, WEEK, rows, [], [], {}, gsis_to_canonical, FETCHED_AT)
    assert records[0].canonical_player_id == "gsis:00-1"
    assert unresolved == []


def test_unresolved_gsis_reported_never_discarded():
    """Phase 5: historical data with no current DK mapping is still
    persisted, just reported as unresolved."""
    rows = [_ws_row("00-1")]
    records, unresolved = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    assert len(records) == 1  # never discarded


# --- NFL M8 -- box-score passthroughs + reception_share ---

def _qb_ws_row(gsis_id, team="PHI", attempts=30, completions=20, passing_yards=250, passing_tds=2,
               carries=2, rushing_yards=10, rushing_tds=0):
    return {
        "player_id": gsis_id, "team": team, "opponent_team": "DAL", "position": "QB", "game_id": "g1",
        "targets": 0, "receptions": 0, "carries": carries,
        "attempts": attempts, "completions": completions, "passing_yards": passing_yards, "passing_tds": passing_tds,
        "rushing_yards": rushing_yards, "rushing_tds": rushing_tds,
        "receiving_yards": 0, "receiving_tds": 0,
    }


def test_box_score_fields_are_direct_passthroughs():
    rows = [_qb_ws_row("00-1")]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    r = records[0]
    assert r.pass_attempts == 30
    assert r.completions == 20
    assert r.passing_yards == 250
    assert r.passing_tds == 2
    assert r.rushing_yards == 10
    assert r.rushing_tds == 0


def test_receiving_box_score_fields_passthrough():
    rows = [_ws_row("00-1", targets=8, receptions=6)]
    rows[0]["receiving_yards"] = 80
    rows[0]["receiving_tds"] = 1
    records, _ = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    r = records[0]
    assert r.receiving_yards == 80
    assert r.receiving_tds == 1


def test_reception_share_computed_against_team_total():
    rows = [_ws_row("00-1", receptions=6), _ws_row("00-2", receptions=4)]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    by_id = {r.gsis_id: r for r in records}
    assert by_id["00-1"].reception_share == 0.6
    assert by_id["00-2"].reception_share == 0.4


def test_reception_share_none_when_team_has_zero_total_receptions():
    rows = [_ws_row("00-1", receptions=0)]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    assert records[0].reception_share is None


def test_box_score_fields_none_when_source_omits_them():
    """A row missing a box-score key entirely (e.g. a defensive-only
    stat line with no offensive columns) leaves the field None, never 0."""
    rows = [{"player_id": "00-1", "team": "PHI", "opponent_team": "DAL", "position": "QB", "game_id": "g1"}]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    r = records[0]
    assert r.pass_attempts is None
    assert r.passing_yards is None
    assert r.receiving_yards is None


def test_row_with_no_gsis_identity_is_skipped_entirely():
    rows = [_ws_row(None)]
    records, unresolved = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    assert records == []
    assert unresolved == []


def test_temporal_metadata_never_fabricates_available_at():
    rows = [_ws_row("00-1")]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    r = records[0]
    assert r.available_at is None
    assert r.ingested_at == FETCHED_AT
    assert r.event_time is None


def test_source_provenance_lists_all_three_real_sources():
    rows = [_ws_row("00-1")]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    prov = records[0].source_provenance
    assert "weekly_player_stats" in prov
    assert "snap_counts" in prov
    assert "play_by_play" in prov


def test_routes_and_route_participation_never_populated():
    rows = [_ws_row("00-1")]
    records, _ = build_usage_records(SEASON, WEEK, rows, [], [], {}, {}, FETCHED_AT)
    assert records[0].routes is None
    assert records[0].route_participation is None
