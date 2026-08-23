from bluecollar.player_matcher import match_bluecollar_players
from external_projections.models import ExternalProjectionPlayer


def _pitcher_record(player_id, name, team_abbr, game_id="g1", opponent="TOR"):
    return {"player_id": player_id, "name": name, "team_id": "1", "team_abbr": team_abbr,
            "opponent_team_id": "2", "opponent_abbr": opponent, "game_id": game_id, "status": "probable"}


def _batter_record(player_id, name, team_abbr, game_id="g1", opponent="TOR"):
    return {"player_id": player_id, "name": name, "team_id": "1", "team_abbr": team_abbr,
            "opponent_team_id": "2", "opponent_abbr": opponent, "game_id": game_id,
            "batting_order": 1, "status": "starting_lineup"}


def _package(pitchers=None, batters=None):
    return {"games": [], "teams": [], "pitchers": pitchers or [], "batters": batters or []}


def _bc_player(name, team, position, opponent=None, projection=None, salary=None):
    return ExternalProjectionPlayer(
        external_player_id=f"{name.lower()}|{team.lower()}|{position.lower()}", name=name, team=team, position=position,
        projection=projection or 0.0, provider_name="BlueCollar DFS", updated_at="12:00:00 ET", slate_id="bc-slate",
        opponent=opponent, salary=salary,
    )


def test_matches_hitter_by_exact_name_and_team():
    package = _package(batters=[_batter_record("h1", "Freddie Freeman", "LAD")])
    players = [_bc_player("Freddie Freeman", "LAD", "1B")]
    results = match_bluecollar_players(players, package)
    assert results[0].match_status == "matched"
    assert results[0].mlb_player_id == "h1"
    assert results[0].match_confidence == "name_team_exact"


def test_matches_pitcher_by_exact_name_and_team():
    package = _package(pitchers=[_pitcher_record("p1", "Zac Gallen", "AZ")])
    players = [_bc_player("Zac Gallen", "AZ", "P")]
    results = match_bluecollar_players(players, package)
    assert results[0].match_status == "matched"
    assert results[0].mlb_player_id == "p1"


def test_unmatched_player_preserved_not_dropped():
    package = _package()
    players = [_bc_player("Nobody Real", "ZZZ", "OF")]
    results = match_bluecollar_players(players, package)
    assert len(results) == 1
    assert results[0].match_status == "unmatched"
    assert results[0].mlb_player_id is None


def test_same_name_collision_across_teams_marked_ambiguous_not_guessed():
    """Two research-known players share a normalized name across
    DIFFERENT teams -- must come back "ambiguous" rather than guessing,
    matching the milestone's explicit collision-safety requirement."""
    package = _package(batters=[
        _batter_record("h1", "Jose Fermin", "LAA"),
        _batter_record("h2", "Jose Fermin", "STL"),
    ])
    players = [_bc_player("Jose Fermin", "ZZZ", "SS")]  # team doesn't line up with either -- falls to name-only tier
    results = match_bluecollar_players(players, package)
    assert results[0].match_status == "ambiguous"
    assert set(results[0].candidate_mlb_ids) == {"h1", "h2"}


def test_same_name_different_team_resolves_each_correctly():
    package = _package(
        pitchers=[_pitcher_record("p_a", "Max Muncy", "ATH", game_id="gameA")],
        batters=[_batter_record("h_b", "Max Muncy", "LAD", game_id="gameB")],
    )
    players = [_bc_player("Max Muncy", "ATH", "P"), _bc_player("Max Muncy", "LAD", "3B")]
    results = match_bluecollar_players(players, package)
    ath_result = next(r for r in results if r.team == "ATH")
    lad_result = next(r for r in results if r.team == "LAD")
    assert ath_result.mlb_player_id == "p_a"
    assert lad_result.mlb_player_id == "h_b"
    assert ath_result.mlb_player_id != lad_result.mlb_player_id


def test_pitcher_positions_normalized_to_p_for_matching():
    package = _package(pitchers=[_pitcher_record("p1", "Some Reliever", "NYY")])
    players = [_bc_player("Some Reliever", "NYY", "RP")]
    results = match_bluecollar_players(players, package)
    assert results[0].match_status == "matched"


def test_raw_projection_carried_through_verbatim():
    package = _package(batters=[_batter_record("h1", "Freddie Freeman", "LAD")])
    players = [_bc_player("Freddie Freeman", "LAD", "1B", projection=12.4)]
    results = match_bluecollar_players(players, package)
    assert results[0].raw_projection == 12.4
    assert results[0].usable_projection is None  # zero-value handling happens in bluecollar/build.py, not here


def test_empty_player_list_returns_empty():
    assert match_bluecollar_players([], _package()) == []


def test_preserves_input_order_for_746_style_full_slate():
    """A large, realistic slate (many players, most unmatched since only
    a handful of research-known starters exist) -- confirms ordering and
    scale both hold, mirroring the live 746-player Main slate."""
    package = _package(pitchers=[_pitcher_record(f"p{i}", f"Pitcher {i}", "NYY") for i in range(15)])
    players = [_bc_player(f"Pitcher {i}", "NYY", "P") for i in range(15)] + [_bc_player(f"Bench Player {i}", "BOS", "OF") for i in range(731)]
    results = match_bluecollar_players(players, package)
    assert len(results) == 746
    assert [r.name for r in results[:3]] == ["Pitcher 0", "Pitcher 1", "Pitcher 2"]
    assert sum(1 for r in results if r.match_status == "matched") == 15
    assert sum(1 for r in results if r.match_status == "unmatched") == 731
