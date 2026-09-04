"""NFL M7 -- targeted tests for nfl/odds_provider_normalizer.py. Market
shape fixtures mirror tests/test_odds_normalizer.py's SportsGameOdds
fixture exactly (same real, confirmed statID/betTypeID/periodID/
statEntityID schema -- see that file's own comment) with NFL teams/
league substituted in. No network calls."""

from nfl.odds_provider_normalizer import (
    NFL_FULL_NAME_TO_DK_ABBR,
    normalize_sportsgameodds_event_nfl,
    normalize_theoddsapi_event_nfl,
)

RETRIEVED_AT = "2026-09-04T00:00:00+00:00"


def sgo_event(**overrides):
    event = {
        "eventID": "evt_nfl_1",
        "leagueID": "NFL",
        "teams": {
            "home": {"teamID": "KC", "names": {"long": "Kansas City Chiefs", "short": "KC"}},
            "away": {"teamID": "BUF", "names": {"long": "Buffalo Bills", "short": "BUF"}},
        },
        "status": {"startsAt": "2026-09-13T17:00:00Z"},
        "odds": {
            "points-home-game-ml-home": {
                "statID": "points", "betTypeID": "ml", "periodID": "game", "statEntityID": "home", "sideID": "home",
                "byBookmaker": {"draftkings": {"odds": "-150", "lastUpdatedAt": "2026-09-13T12:00:00Z", "available": True}},
            },
            "points-away-game-ml-away": {
                "statID": "points", "betTypeID": "ml", "periodID": "game", "statEntityID": "away", "sideID": "away",
                "byBookmaker": {"draftkings": {"odds": "130", "available": True}},
            },
            "points-all-game-ou-over": {
                "statID": "points", "betTypeID": "ou", "periodID": "game", "statEntityID": "all", "sideID": "over",
                "byBookmaker": {"draftkings": {"odds": "-110", "overUnder": "48.5", "available": True}},
            },
            "points-all-game-ou-under": {
                "statID": "points", "betTypeID": "ou", "periodID": "game", "statEntityID": "all", "sideID": "under",
                "byBookmaker": {"draftkings": {"odds": "-110", "overUnder": "48.5", "available": True}},
            },
            "points-home-game-sp-home": {
                "statID": "points", "betTypeID": "sp", "periodID": "game", "statEntityID": "home", "sideID": "home",
                "byBookmaker": {"draftkings": {"odds": "-110", "spread": "-2.5", "available": True}},
            },
            "points-away-game-sp-away": {
                "statID": "points", "betTypeID": "sp", "periodID": "game", "statEntityID": "away", "sideID": "away",
                "byBookmaker": {"draftkings": {"odds": "-110", "spread": "2.5", "available": True}},
            },
        },
    }
    event.update(overrides)
    return event


def test_normalizes_real_market_shape_correctly():
    result = normalize_sportsgameodds_event_nfl(sgo_event(), RETRIEVED_AT)
    assert result is not None
    assert result.provider == "sportsgameodds"
    assert result.league == "NFL"
    assert result.home_team == "KC"
    assert result.away_team == "BUF"
    assert len(result.books) == 1
    book = result.books[0]
    assert book.home_moneyline == -150
    assert book.away_moneyline == 130
    assert book.total == 48.5
    assert book.home_run_line == -2.5
    assert book.away_run_line == 2.5


def test_arizona_cardinals_abbreviation_is_not_corrupted_by_mlb_crosswalk():
    """Regression test for the exact bug this module's docstring warns
    about: MLB's dfs/team_abbreviations.py maps ARI -> AZ (Arizona's MLB
    research-package code), but ARI is DraftKings' own correct NFL
    abbreviation for the Cardinals. The NFL normalizer must never route
    through that MLB table."""
    event = sgo_event(teams={
        "home": {"teamID": "ARI", "names": {"long": "Arizona Cardinals", "short": "ARI"}},
        "away": {"teamID": "SEA", "names": {"long": "Seattle Seahawks", "short": "SEA"}},
    })
    result = normalize_sportsgameodds_event_nfl(event, RETRIEVED_AT)
    assert result is not None
    assert result.home_team == "ARI"  # NOT "AZ"


def test_missing_team_returns_none_never_partial():
    event = sgo_event(teams={"home": {}, "away": {}})
    assert normalize_sportsgameodds_event_nfl(event, RETRIEVED_AT) is None


def test_missing_event_id_returns_none():
    event = sgo_event()
    del event["eventID"]
    assert normalize_sportsgameodds_event_nfl(event, RETRIEVED_AT) is None


def test_excludes_player_prop_and_non_game_period_markets():
    event = sgo_event()
    event["odds"]["batting_hits-player123-game-ou-over"] = {
        "statID": "batting_hits", "betTypeID": "ou", "periodID": "game", "statEntityID": "player123", "sideID": "over",
        "byBookmaker": {"draftkings": {"odds": "-120", "overUnder": "1.5", "available": True}},
    }
    event["odds"]["points-all-1h-ou-over"] = {
        "statID": "points", "betTypeID": "ou", "periodID": "1h", "statEntityID": "all", "sideID": "over",
        "byBookmaker": {"draftkings": {"odds": "-110", "overUnder": "24.5", "available": True}},
    }
    result = normalize_sportsgameodds_event_nfl(event, RETRIEVED_AT)
    assert result.books[0].total == 48.5  # unchanged by the excluded markets


def theoddsapi_event(**overrides):
    event = {
        "id": "toa_evt_1",
        "sport_key": "americanfootball_nfl",
        "commence_time": "2026-09-13T17:00:00Z",
        "home_team": "Kansas City Chiefs",
        "away_team": "Buffalo Bills",
        "bookmakers": [
            {
                "key": "draftkings",
                "last_update": "2026-09-13T12:00:00Z",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Kansas City Chiefs", "price": -150},
                        {"name": "Buffalo Bills", "price": 130},
                    ]},
                    {"key": "spreads", "outcomes": [
                        {"name": "Kansas City Chiefs", "point": -2.5, "price": -110},
                        {"name": "Buffalo Bills", "point": 2.5, "price": -110},
                    ]},
                    {"key": "totals", "outcomes": [
                        {"name": "Over", "point": 48.5, "price": -110},
                        {"name": "Under", "point": 48.5, "price": -110},
                    ]},
                ],
            },
        ],
    }
    event.update(overrides)
    return event


def test_theoddsapi_normalizes_all_32_teams_present():
    assert len(NFL_FULL_NAME_TO_DK_ABBR) == 32
    assert NFL_FULL_NAME_TO_DK_ABBR["Arizona Cardinals"] == "ARI"


def test_theoddsapi_normalizes_real_market_shape():
    result = normalize_theoddsapi_event_nfl(theoddsapi_event(), RETRIEVED_AT)
    assert result is not None
    assert result.provider == "theoddsapi"
    assert result.home_team == "KC"
    assert result.away_team == "BUF"
    book = result.books[0]
    assert book.home_moneyline == -150
    assert book.away_moneyline == 130
    assert book.total == 48.5
    assert book.home_run_line == -2.5
    assert book.away_run_line == 2.5


def test_theoddsapi_unrecognized_team_name_returns_none():
    event = theoddsapi_event(home_team="Not A Real Team")
    assert normalize_theoddsapi_event_nfl(event, RETRIEVED_AT) is None
