from dfs.models import DKSalaryRow
from dfs.player_pool import build_dfs_players, build_match_report
from dfs.player_resolver import build_canonical_by_id, build_canonical_index, resolve_all
from dfs.slate_validation import validate_slate


def _package():
    return {
        "games": [{"game_id": "g1", "home_team_abbr": "BOS", "away_team_abbr": "NYY"}],
        "pitchers": [
            {"player_id": "1001", "name": "Home Ace", "team_abbr": "BOS", "opponent_abbr": "NYY", "game_id": "g1",
             "throws": "R", "status": "probable"},
        ],
        "batters": [
            {"player_id": "2001", "name": "Aaron Judge", "team_abbr": "NYY", "opponent_abbr": "BOS", "game_id": "g1"},
        ],
    }


def _dk_row(dk_id, name, team, positions, salary, game_info="NYY@BOS 07:05PM ET", avg_pts=None):
    return DKSalaryRow(dk_player_id=dk_id, name=name, team_abbrev=team, dk_positions=list(positions),
                        salary=salary, game_info=game_info, avg_points_per_game=avg_pts)


def _pitcher_snapshot():
    return {
        "model_version": "0.6.0",
        "generated_at_utc": "2026-08-11T18:00:00+00:00",
        "generated_at_local": "2026-08-11T13:00:00-05:00",
        "pitchers": [{
            "player_id": "1001", "name": "Home Ace", "team": "BOS", "opponent": "NYY", "game_id": "g1",
            "projection": 20.0, "ceiling": 28.0, "floor": 12.0, "overall_score": 75.0, "risk_score": 20.0,
            "confidence": 90.0, "tags": ["swing_and_miss"], "reasons": ["good K rate"],
            "season_metrics": {"innings": 120.0}, "recent_metrics": {"innings": 18.0},
        }],
    }


def _batter_snapshot():
    return {
        "model_version": "0.1.0",
        "generated_at_utc": "2026-08-11T18:00:00+00:00",
        "generated_at_local": "2026-08-11T13:00:00-05:00",
        "hitters": [{
            "player_id": "2001", "name": "Aaron Judge", "team": "NYY", "opponent": "BOS", "game_id": "g1",
            "batting_order": 2, "batting_hand": "R",
            "projection": 8.5, "ceiling": 16.0, "floor": 4.0, "overall_score": 70.0, "risk_score": 25.0,
            "confidence": 100.0, "tags": ["elite_power"], "reasons": ["barrel rate"],
            "season_metrics": {"plate_appearances": 400}, "recent_metrics": {"plate_appearances": 55},
        }],
    }


def _build(dk_rows, package, pitcher_snapshot, batter_snapshot):
    index = build_canonical_index(package)
    canonical_by_id = build_canonical_by_id(index)
    matches = resolve_all(dk_rows, package)
    slate_validation = validate_slate(dk_rows, package)
    pitcher_raw_by_id = {str(r["player_id"]): r for r in package["pitchers"]}
    players = build_dfs_players(
        dk_rows, matches, canonical_by_id, slate_validation.dk_game_matches, pitcher_raw_by_id,
        pitcher_snapshot, batter_snapshot, pitcher_snapshot_path="predictions/2026-08-11/pitcher_board_x.json",
        batter_snapshot_path="predictions/2026-08-11/batter_board_x.json",
    )
    report = build_match_report(dk_rows, matches, players, slate_validation)
    return players, report


def test_matched_pitcher_is_active_with_full_provenance():
    dk_rows = [_dk_row("d1", "Home Ace", "BOS", ["P"], 9000, avg_pts=20.0)]
    players, _ = _build(dk_rows, _package(), _pitcher_snapshot(), _batter_snapshot())
    p = players[0]
    assert p.lineup_status == "active"
    assert p.match_status == "matched"
    assert p.mlb_player_id == "1001"
    assert p.projection == 20.0
    assert p.throwing_hand == "R"
    assert p.season_sample_size == 120.0
    assert p.recent_sample_size == 18.0
    assert p.source_model_type == "pitcher"
    assert p.source_model_version == "0.6.0"
    assert p.prediction_generated_at_utc == "2026-08-11T18:00:00+00:00"
    assert p.prediction_snapshot_path == "predictions/2026-08-11/pitcher_board_x.json"
    assert p.avg_points_per_game_dk == 20.0  # preserved, but never used as our projection
    assert p.dk_positions == ["P"]
    assert p.salary == 9000


def test_matched_hitter_is_active_with_batting_order_and_sample_size():
    dk_rows = [_dk_row("d2", "Aaron Judge", "NYY", ["OF"], 6800)]
    players, _ = _build(dk_rows, _package(), _pitcher_snapshot(), _batter_snapshot())
    h = players[0]
    assert h.lineup_status == "active"
    assert h.batting_order == 2
    assert h.batting_hand == "R"
    assert h.season_sample_size == 400
    assert h.recent_sample_size == 55
    assert h.source_model_type == "batter"
    assert h.source_model_version == "0.1.0"


def test_bench_hitter_without_posted_lineup_is_excluded_but_preserved():
    dk_rows = [_dk_row("d3", "Bench Guy", "NYY", ["1B"], 3000)]
    players, report = _build(dk_rows, _package(), _pitcher_snapshot(), _batter_snapshot())
    h = players[0]
    assert h.lineup_status == "lineup_not_confirmed"
    assert h.match_status == "unmatched"
    assert h.projection is None
    assert report["hitters_excluded_lineup_not_posted"] == 1
    # Never silently dropped -- still present in the pool with salary/position intact.
    assert h.salary == 3000
    assert h.dk_positions == ["1B"]


def test_non_probable_pitcher_marked_not_in_starting_lineup():
    dk_rows = [_dk_row("d4", "Random Reliever", "BOS", ["P"], 3500)]
    players, _ = _build(dk_rows, _package(), _pitcher_snapshot(), _batter_snapshot())
    assert players[0].lineup_status == "not_in_starting_lineup"


def test_player_whose_game_is_not_on_dk_slate_is_flagged():
    dk_rows = [_dk_row("d5", "Off Slate Guy", "LAA", ["OF"], 3000, game_info="LAA@SEA 10:10PM ET")]
    players, _ = _build(dk_rows, _package(), _pitcher_snapshot(), _batter_snapshot())
    assert players[0].lineup_status == "game_not_on_research_slate"
    assert players[0].game_id is None


def test_matched_player_missing_from_snapshot_is_missing_projection():
    package = _package()
    package["batters"].append(
        {"player_id": "2002", "name": "Ghost Player", "team_abbr": "NYY", "opponent_abbr": "BOS", "game_id": "g1"}
    )
    dk_rows = [_dk_row("d6", "Ghost Player", "NYY", ["3B"], 4000)]
    players, report = _build(dk_rows, package, _pitcher_snapshot(), _batter_snapshot())
    assert players[0].match_status == "matched"
    assert players[0].lineup_status == "missing_projection"
    assert players[0].projection is None
    assert report["missing_projection"] == 1


def test_missing_salary_or_snapshot_never_invents_a_projection():
    dk_rows = [_dk_row("d7", "Aaron Judge", "NYY", ["OF"], 6800)]
    players, _ = _build(dk_rows, _package(), None, None)
    h = players[0]
    assert h.match_status == "matched"
    assert h.lineup_status == "missing_projection"
    assert h.projection is None
    assert h.overall_score is None


def test_match_report_aggregates_full_scenario():
    dk_rows = [
        _dk_row("d1", "Home Ace", "BOS", ["P"], 9000),
        _dk_row("d2", "Aaron Judge", "NYY", ["OF"], 6800),
        _dk_row("d3", "Bench Guy", "NYY", ["1B"], 3000),
        _dk_row("d4", "Random Reliever", "BOS", ["P"], 3500),
        _dk_row("d5", "Off Slate Guy", "LAA", ["OF"], 3000, game_info="LAA@SEA 10:10PM ET"),
    ]
    players, report = _build(dk_rows, _package(), _pitcher_snapshot(), _batter_snapshot())
    assert report["dk_entries"] == 5
    assert report["matched_to_mlb"] == 2
    assert report["pitchers_active"] == 1
    assert report["hitters_active"] == 1
    assert report["hitters_excluded_lineup_not_posted"] == 1
    assert report["unmatched_count"] == 3
    assert report["ambiguous_count"] == 0
    assert report["dk_games_total"] == 2
    assert report["dk_games_matched_to_research"] == 1
    assert report["salary_min"] == 3000
    assert report["salary_max"] == 9000


def test_dk_position_eligibility_is_authoritative_not_inferred_from_mlb():
    # Even though the research package has no positional data at all
    # beyond identity, DK's own multi-position eligibility passes through untouched.
    dk_rows = [_dk_row("d8", "Aaron Judge", "NYY", ["1B", "OF"], 6800)]
    players, _ = _build(dk_rows, _package(), _pitcher_snapshot(), _batter_snapshot())
    assert players[0].dk_positions == ["1B", "OF"]


def test_never_silently_drops_a_player():
    dk_rows = [
        _dk_row("d1", "Home Ace", "BOS", ["P"], 9000),
        _dk_row("d3", "Bench Guy", "NYY", ["1B"], 3000),
        _dk_row("d5", "Off Slate Guy", "LAA", ["OF"], 3000, game_info="LAA@SEA 10:10PM ET"),
    ]
    players, _ = _build(dk_rows, _package(), _pitcher_snapshot(), _batter_snapshot())
    assert len(players) == 3
