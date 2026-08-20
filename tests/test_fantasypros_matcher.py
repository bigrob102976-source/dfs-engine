from fantasypros.matcher import match_fantasypros_players
from fantasypros.models import FantasyProsRawPlayer


def _pitcher_record(player_id, name, team_abbr, game_id="g1", opponent="TOR"):
    return {"player_id": player_id, "name": name, "team_id": "1", "team_abbr": team_abbr,
            "opponent_team_id": "2", "opponent_abbr": opponent, "game_id": game_id, "status": "probable"}


def _batter_record(player_id, name, team_abbr, game_id="g1", opponent="TOR"):
    return {"player_id": player_id, "name": name, "team_id": "1", "team_abbr": team_abbr,
            "opponent_team_id": "2", "opponent_abbr": opponent, "game_id": game_id,
            "batting_order": 1, "status": "starting_lineup"}


def _package(pitchers=None, batters=None):
    return {"games": [], "teams": [], "pitchers": pitchers or [], "batters": batters or []}


def _fp_player(fpid, name, team, player_type, stats=None):
    return FantasyProsRawPlayer(fpid=fpid, player_id=fpid, name=name, team_id=team, player_type=player_type, stats=stats or {})


def test_matches_hitter_by_exact_name_and_team():
    package = _package(batters=[_batter_record("h1", "Freddie Freeman", "LAD")])
    players = [_fp_player("3365", "Freddie Freeman", "LAD", "hitter")]
    results = match_fantasypros_players(players, package)
    assert len(results) == 1
    assert results[0].match_status == "matched"
    assert results[0].mlb_player_id == "h1"
    assert results[0].match_confidence == "name_team_exact"


def test_matches_pitcher_by_exact_name_and_team():
    package = _package(pitchers=[_pitcher_record("p1", "Aroldis Chapman", "BOS")])
    players = [_fp_player("3068", "Aroldis Chapman", "BOS", "pitcher")]
    results = match_fantasypros_players(players, package)
    assert results[0].match_status == "matched"
    assert results[0].mlb_player_id == "p1"


def test_unmatched_player_preserved_not_dropped():
    package = _package()
    players = [_fp_player("999", "Nobody Real", "ZZZ", "hitter")]
    results = match_fantasypros_players(players, package)
    assert len(results) == 1
    assert results[0].match_status == "unmatched"
    assert results[0].mlb_player_id is None


def test_duplicate_name_protection_ambiguous_within_fantasypros_batch():
    """Two research-known players share a normalized name across
    DIFFERENT teams -- the FantasyPros row cannot be safely disambiguated
    by name alone and must come back "ambiguous", never guessed."""
    package = _package(batters=[
        _batter_record("h1", "Jose Fermin", "LAA"),
        _batter_record("h2", "Jose Fermin", "STL"),
    ])
    # No team match for the FP row itself (simulating FantasyPros' own
    # team_id not lining up cleanly) -- falls through to the name-only
    # tier, which must refuse to guess given two DIFFERENT teams share it.
    players = [_fp_player("1", "Jose Fermin", "ZZZ", "hitter")]
    results = match_fantasypros_players(players, package)
    assert results[0].match_status == "ambiguous"
    assert set(results[0].candidate_mlb_ids) == {"h1", "h2"}


def test_same_name_different_game_never_bleeds_across_games():
    """Two real players share a name but are on different teams/games --
    exact team match must resolve each to its OWN correct identity, never
    the other's."""
    package = _package(pitchers=[
        _pitcher_record("p_a", "Max Muncy", "ATH", game_id="gameA"),
    ], batters=[
        _batter_record("h_b", "Max Muncy", "LAD", game_id="gameB"),
    ])
    players = [
        _fp_player("1", "Max Muncy", "ATH", "pitcher"),
        _fp_player("2", "Max Muncy", "LAD", "hitter"),
    ]
    results = match_fantasypros_players(players, package)
    ath_result = next(r for r in results if r.team == "ATH")
    lad_result = next(r for r in results if r.team == "LAD")
    assert ath_result.mlb_player_id == "p_a"
    assert lad_result.mlb_player_id == "h_b"
    assert ath_result.mlb_player_id != lad_result.mlb_player_id


def test_raw_stats_and_dk_points_placeholder_carried_through():
    package = _package(batters=[_batter_record("h1", "Freddie Freeman", "LAD")])
    players = [_fp_player("3365", "Freddie Freeman", "LAD", "hitter", stats={"hrs": 0.09, "1b": 1.06})]
    results = match_fantasypros_players(players, package)
    assert results[0].raw_stats == {"hrs": 0.09, "1b": 1.06}
    assert results[0].dk_points is None  # scoring happens separately, in fantasypros/build.py


def test_empty_player_list_returns_empty():
    assert match_fantasypros_players([], _package()) == []


def test_preserves_input_order():
    package = _package(batters=[_batter_record("h1", "A Player", "LAD"), _batter_record("h2", "B Player", "LAD")])
    players = [_fp_player("1", "B Player", "LAD", "hitter"), _fp_player("2", "A Player", "LAD", "hitter")]
    results = match_fantasypros_players(players, package)
    assert [r.name for r in results] == ["B Player", "A Player"]
