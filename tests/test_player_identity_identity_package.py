from player_identity.identity_package import build_identity_package
from player_identity.models import CanonicalIdentity


def _package(pitchers=None, batters=None, games=None):
    return {
        "games": games if games is not None else [
            {"game_id": "g1", "home_team_abbr": "BOS", "away_team_abbr": "TOR"},
        ],
        "teams": [],
        "pitchers": pitchers or [],
        "batters": batters or [],
    }


def _identity(mlb_id, name, team, player_type):
    return CanonicalIdentity(
        mlb_player_id=mlb_id, canonical_name=name, normalized_name=name.lower(),
        current_team=team, player_type=player_type, last_verified_at="2026-08-23T18:00:00+00:00",
    )


def test_adds_a_hitter_not_in_the_confirmed_lineup_as_an_extra_batter_candidate():
    package = _package()
    crosswalk = {"h1": _identity("h1", "Bench Hitter", "BOS", "hitter")}
    result = build_identity_package(package, crosswalk)
    assert len(result["batters"]) == 1
    record = result["batters"][0]
    assert record["player_id"] == "h1"
    assert record["team_abbr"] == "BOS"
    assert record["game_id"] == "g1"
    assert record["opponent_abbr"] == "TOR"


def test_adds_a_reliever_not_in_probable_starters_as_an_extra_pitcher_candidate():
    package = _package()
    crosswalk = {"p1": _identity("p1", "Reliever", "TOR", "pitcher")}
    result = build_identity_package(package, crosswalk)
    assert len(result["pitchers"]) == 1
    assert result["pitchers"][0]["opponent_abbr"] == "BOS"


def test_never_duplicates_a_player_already_in_the_confirmed_package():
    package = _package(batters=[{"player_id": "h1", "name": "Starter", "team_abbr": "BOS", "opponent_abbr": "TOR", "game_id": "g1"}])
    crosswalk = {"h1": _identity("h1", "Starter", "BOS", "hitter")}
    result = build_identity_package(package, crosswalk)
    assert len(result["batters"]) == 1  # not duplicated


def test_excludes_a_player_whose_current_team_has_no_game_today():
    package = _package()
    crosswalk = {"x1": _identity("x1", "Off Day Player", "LAD", "hitter")}  # LAD not in today's games
    result = build_identity_package(package, crosswalk)
    assert result["batters"] == []
    assert result["pitchers"] == []


def test_never_mutates_the_original_package():
    package = _package()
    original_batters = package["batters"]
    crosswalk = {"h1": _identity("h1", "Bench Hitter", "BOS", "hitter")}
    build_identity_package(package, crosswalk)
    assert package["batters"] is original_batters
    assert package["batters"] == []


def test_doubleheader_first_game_wins_for_a_team_playing_twice():
    games = [
        {"game_id": "g1", "home_team_abbr": "BOS", "away_team_abbr": "TOR"},
        {"game_id": "g2", "home_team_abbr": "BOS", "away_team_abbr": "TOR"},
    ]
    package = _package(games=games)
    crosswalk = {"h1": _identity("h1", "Bench Hitter", "BOS", "hitter")}
    result = build_identity_package(package, crosswalk)
    assert result["batters"][0]["game_id"] == "g1"


def test_unknown_player_type_is_never_guessed_into_either_list():
    package = _package()
    crosswalk = {"x1": _identity("x1", "Unknown Type", "BOS", None)}
    result = build_identity_package(package, crosswalk)
    assert result["batters"] == []
    assert result["pitchers"] == []


def test_empty_crosswalk_yields_the_original_lists_unchanged():
    package = _package(
        pitchers=[{"player_id": "p1", "name": "Starter", "team_abbr": "TOR", "opponent_abbr": "BOS", "game_id": "g1"}],
        batters=[{"player_id": "h1", "name": "Starter", "team_abbr": "BOS", "opponent_abbr": "TOR", "game_id": "g1"}],
    )
    result = build_identity_package(package, {})
    assert result["pitchers"] == package["pitchers"]
    assert result["batters"] == package["batters"]
