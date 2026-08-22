"""Milestone 32.1, Part 19 -- venues.py. No network calls."""

from historical_mlb.game_universe import GameUniverseRow
from historical_mlb.venues import build_venue_crosswalk


def _game(venue_id, home_team, venue_name="Test Park"):
    return GameUniverseRow(
        season=2025, game_date="2025-06-15", game_pk=1, game_number=1,
        away_team="BOS", home_team=home_team, away_team_id=1, home_team_id=2,
        venue_id=venue_id, venue_name=venue_name, scheduled_start=None, final_status="Final",
        double_header="N", away_probable_pitcher_id=None, home_probable_pitcher_id=None,
    )


def test_build_venue_crosswalk_uses_real_team_coordinates():
    games = [_game(2394, "DET", "Comerica Park")]
    venues = build_venue_crosswalk(games)
    assert len(venues) == 1
    v = venues[0]
    assert v.venue_id == 2394
    assert v.venue_name == "Comerica Park"
    assert v.latitude is not None  # from TEAM_LOCATIONS["DET"]
    assert v.primary_team == "DET"


def test_build_venue_crosswalk_never_invents_park_factor():
    games = [_game(2394, "DET")]
    venues = build_venue_crosswalk(games)
    assert venues[0].park_factor is None


def test_build_venue_crosswalk_dedupes_by_venue_id():
    games = [_game(2394, "DET"), _game(2394, "DET"), _game(2394, "DET")]
    venues = build_venue_crosswalk(games)
    assert len(venues) == 1


def test_build_venue_crosswalk_shared_venue_picks_most_common_home_team():
    games = [_game(9999, "ATH", "Shared Park"), _game(9999, "ATH", "Shared Park"), _game(9999, "OAK", "Shared Park")]
    venues = build_venue_crosswalk(games)
    assert venues[0].primary_team == "ATH"  # 2 games vs 1


def test_build_venue_crosswalk_empty_input():
    assert build_venue_crosswalk([]) == []
