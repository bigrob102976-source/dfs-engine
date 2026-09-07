"""NFL M5 -- targeted tests for nfl/game_context_models.py."""

import pytest

from nfl.game_context_models import DERIVED_FROM_SPREAD_AND_TOTAL, NflGameContext, derive_implied_totals, team_view

DG_ID = 151307
DATE = "2026-09-13"


def _game(spread=-3.0, total=47.5, home="PHI", away="DAL"):
    home_implied, away_implied, derivation = derive_implied_totals(spread, total)
    return NflGameContext(
        sport="NFL", draft_group_id=DG_ID, slate_date=DATE, canonical_game_id="100", draftkings_game_id="100",
        home_team=home, away_team=away, game_start_time="2026-09-13T17:00:00Z",
        spread=spread, total=total, home_moneyline=-160, away_moneyline=140,
        home_implied_total=home_implied, away_implied_total=away_implied, implied_total_derivation=derivation,
        source="sportsgameodds", source_provenance="sportsgameodds",
    )


def test_missing_odds_fields_stay_none():
    game = NflGameContext(sport="NFL", draft_group_id=DG_ID, slate_date=DATE, canonical_game_id="100", draftkings_game_id="100", home_team="PHI", away_team="DAL")
    assert game.spread is None
    assert game.total is None
    assert game.home_implied_total is None
    assert game.implied_total_derivation is None


def test_derive_implied_totals_requires_both_spread_and_total():
    assert derive_implied_totals(None, 47.5) == (None, None, None)
    assert derive_implied_totals(-3.0, None) == (None, None, None)
    assert derive_implied_totals(None, None) == (None, None, None)


def test_derive_implied_totals_is_labeled_derived():
    home, away, derivation = derive_implied_totals(-3.0, 47.5)
    assert home == 25.25
    assert away == 22.25
    assert derivation == DERIVED_FROM_SPREAD_AND_TOTAL


def test_implied_totals_sum_to_real_total():
    home, away, _ = derive_implied_totals(-3.0, 47.5)
    assert home + away == 47.5


def test_team_view_home():
    game = _game()
    view = team_view(game, "PHI")
    assert view["home_away"] == "home"
    assert view["opponent"] == "DAL"
    assert view["spread"] == -3.0
    assert view["implied_team_total"] == game.home_implied_total


def test_team_view_away_spread_is_inverted():
    game = _game()
    view = team_view(game, "DAL")
    assert view["home_away"] == "away"
    assert view["opponent"] == "PHI"
    assert view["spread"] == 3.0  # inverted from home's -3.0
    assert view["implied_team_total"] == game.away_implied_total


def test_team_view_unknown_team_raises():
    game = _game()
    with pytest.raises(ValueError):
        team_view(game, "SEA")
