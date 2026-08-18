from research.game_environment.providers.normalizer import normalize_sportsgameodds_event

RETRIEVED_AT = "2026-08-17T18:00:00+00:00"


def sample_event(**overrides):
    # Shape confirmed against a REAL live SportsGameOdds v2 response
    # (Milestone 24 live validation, 2026-08-17) -- statID/betTypeID/
    # periodID/statEntityID are the authoritative classification fields;
    # see normalizer.py's module docstring for why oddID text alone
    # (e.g. "contains -ou-") is not sufficient.
    event = {
        "eventID": "evt_123",
        "leagueID": "MLB",
        "teams": {
            "home": {"teamID": "LAD", "names": {"long": "Los Angeles Dodgers", "short": "LAD"}},
            "away": {"teamID": "SD", "names": {"long": "San Diego Padres", "short": "SD"}},
        },
        "status": {"startsAt": "2026-08-17T23:10:00Z"},
        "odds": {
            "points-home-game-ml-home": {
                "statID": "points",
                "betTypeID": "ml",
                "periodID": "game",
                "statEntityID": "home",
                "sideID": "home",
                "byBookmaker": {
                    "draftkings": {"odds": "-165", "lastUpdatedAt": "2026-08-17T17:00:00Z", "available": True},
                    "fanduel": {"odds": "-160", "available": True},
                },
            },
            "points-away-game-ml-away": {
                "statID": "points",
                "betTypeID": "ml",
                "periodID": "game",
                "statEntityID": "away",
                "sideID": "away",
                "byBookmaker": {
                    "draftkings": {"odds": "140", "available": True},
                    "fanduel": {"odds": "135", "available": True},
                },
            },
            "points-all-game-ou-over": {
                "statID": "points",
                "betTypeID": "ou",
                "periodID": "game",
                "statEntityID": "all",
                "sideID": "over",
                "byBookmaker": {
                    "draftkings": {"odds": "-110", "overUnder": "8.5", "available": True},
                    "fanduel": {"odds": "-105", "overUnder": "8.5", "available": True},
                },
            },
            "points-all-game-ou-under": {
                "statID": "points",
                "betTypeID": "ou",
                "periodID": "game",
                "statEntityID": "all",
                "sideID": "under",
                "byBookmaker": {
                    "draftkings": {"odds": "-110", "overUnder": "8.5", "available": True},
                    "fanduel": {"odds": "-115", "overUnder": "8.5", "available": True},
                },
            },
            "points-home-game-sp-home": {
                "statID": "points",
                "betTypeID": "sp",
                "periodID": "game",
                "statEntityID": "home",
                "sideID": "home",
                "byBookmaker": {
                    "draftkings": {"odds": "-110", "spread": "-1.5", "available": True},
                },
            },
            "points-away-game-sp-away": {
                "statID": "points",
                "betTypeID": "sp",
                "periodID": "game",
                "statEntityID": "away",
                "sideID": "away",
                "byBookmaker": {
                    "draftkings": {"odds": "-110", "spread": "1.5", "available": True},
                },
            },
        },
    }
    event.update(overrides)
    return event


def test_normalizes_teams_and_identity():
    result = normalize_sportsgameodds_event(sample_event(), RETRIEVED_AT)
    assert result is not None
    assert result.event_id == "evt_123"
    assert result.home_team == "LAD"
    assert result.away_team == "SD"
    assert result.league == "MLB"
    assert result.game_time_utc == "2026-08-17T23:10:00Z"
    assert result.retrieved_at == RETRIEVED_AT


def test_normalizes_moneyline_per_book():
    result = normalize_sportsgameodds_event(sample_event(), RETRIEVED_AT)
    dk = next(b for b in result.books if b.book == "draftkings")
    fd = next(b for b in result.books if b.book == "fanduel")
    assert dk.home_moneyline == -165
    assert dk.away_moneyline == 140
    assert fd.home_moneyline == -160
    assert fd.away_moneyline == 135


def test_normalizes_total_and_over_under_odds():
    result = normalize_sportsgameodds_event(sample_event(), RETRIEVED_AT)
    dk = next(b for b in result.books if b.book == "draftkings")
    assert dk.total == 8.5
    assert dk.total_over_odds == -110
    assert dk.total_under_odds == -110


def test_normalizes_run_line_only_for_books_that_have_it():
    result = normalize_sportsgameodds_event(sample_event(), RETRIEVED_AT)
    dk = next(b for b in result.books if b.book == "draftkings")
    fd = next(b for b in result.books if b.book == "fanduel")
    assert dk.home_run_line == -1.5
    assert dk.away_run_line == 1.5
    assert dk.home_run_line_odds == -110
    assert fd.home_run_line is None  # fanduel never posted a run line in the fixture


def test_last_updated_captured_when_present():
    result = normalize_sportsgameodds_event(sample_event(), RETRIEVED_AT)
    dk = next(b for b in result.books if b.book == "draftkings")
    assert dk.last_updated == "2026-08-17T17:00:00Z"


def test_missing_event_id_returns_none():
    event = sample_event()
    del event["eventID"]
    assert normalize_sportsgameodds_event(event, RETRIEVED_AT) is None


def test_missing_teams_returns_none():
    event = sample_event()
    event["teams"] = {}
    assert normalize_sportsgameodds_event(event, RETRIEVED_AT) is None


def test_non_dict_event_returns_none():
    assert normalize_sportsgameodds_event(None, RETRIEVED_AT) is None
    assert normalize_sportsgameodds_event("not a dict", RETRIEVED_AT) is None


def test_event_with_no_odds_object_still_normalizes_identity():
    event = sample_event()
    event["odds"] = {}
    result = normalize_sportsgameodds_event(event, RETRIEVED_AT)
    assert result is not None
    assert result.books == []
    assert len(result.parse_warnings) > 0


def test_alternate_bookmaker_key_name_bookOdds():
    event = sample_event(
        odds={
            "points-home-game-ml-home": {
                "statID": "points",
                "betTypeID": "ml",
                "periodID": "game",
                "statEntityID": "home",
                "sideID": "home",
                "bookOdds": {"betmgm": {"odds": "-155", "available": True}},
            },
        }
    )
    result = normalize_sportsgameodds_event(event, RETRIEVED_AT)
    assert len(result.books) == 1
    assert result.books[0].book == "betmgm"
    assert result.books[0].home_moneyline == -155


def test_team_abbreviation_normalization_via_dk_crosswalk():
    event = sample_event(
        teams={
            "home": {"teamID": "ARI", "names": {"short": "ARI"}},
            "away": {"teamID": "OAK", "names": {"short": "OAK"}},
        }
    )
    result = normalize_sportsgameodds_event(event, RETRIEVED_AT)
    # normalize_dk_team_abbr maps ARI->AZ and OAK->ATH to match this
    # project's research-package abbreviations.
    assert result.home_team == "AZ"
    assert result.away_team == "ATH"


def test_unrecognized_market_type_is_skipped_not_crashed():
    event = sample_event(
        odds={
            "points-home-game-xyz-home": {
                "statID": "points",
                "betTypeID": "xyz",
                "periodID": "game",
                "statEntityID": "home",
                "sideID": "home",
                "byBookmaker": {"draftkings": {"odds": "-110", "available": True}},
            },
        }
    )
    result = normalize_sportsgameodds_event(event, RETRIEVED_AT)
    assert result is not None
    assert result.books == []


def test_team_run_total_does_not_contaminate_the_game_total():
    # Confirmed real-world bug (Milestone 24 live validation): a team-level
    # run total ("<Team> Runs Over/Under") has betTypeID "ou" and an oddID
    # containing "-ou-" too, but statEntityID is "home"/"away", not "all" --
    # it must never be mistaken for the game total.
    event = sample_event()
    event["odds"]["points-away-game-ou-over"] = {
        "statID": "points",
        "betTypeID": "ou",
        "periodID": "game",
        "statEntityID": "away",  # team total, NOT the game total
        "sideID": "over",
        "byBookmaker": {"draftkings": {"odds": "+225", "overUnder": "4.5", "available": True}},
    }
    result = normalize_sportsgameodds_event(event, RETRIEVED_AT)
    dk = next(b for b in result.books if b.book == "draftkings")
    assert dk.total == 8.5  # unchanged by the team total's 4.5


def test_inning_level_moneyline_prop_does_not_contaminate_the_game_moneyline():
    # betTypeID "ml" with periodID "1i" (1st inning) must not overwrite the
    # full-game moneyline captured from periodID "game".
    event = sample_event()
    event["odds"]["points-home-1i-ml-home"] = {
        "statID": "points",
        "betTypeID": "ml",
        "periodID": "1i",
        "statEntityID": "home",
        "sideID": "home",
        "byBookmaker": {"draftkings": {"odds": "-500", "available": True}},
    }
    result = normalize_sportsgameodds_event(event, RETRIEVED_AT)
    dk = next(b for b in result.books if b.book == "draftkings")
    assert dk.home_moneyline == -165  # unchanged by the 1st-inning prop's -500


def test_first_to_score_prop_does_not_contaminate_the_game_moneyline():
    # firstToScore has betTypeID "ml" and home/away sides too, but statID
    # is "firstToScore", not "points" -- must be excluded.
    event = sample_event()
    event["odds"]["firstToScore-home-game-ml-home"] = {
        "statID": "firstToScore",
        "betTypeID": "ml",
        "periodID": "game",
        "statEntityID": "home",
        "sideID": "home",
        "byBookmaker": {"draftkings": {"odds": "+120", "available": True}},
    }
    result = normalize_sportsgameodds_event(event, RETRIEVED_AT)
    dk = next(b for b in result.books if b.book == "draftkings")
    assert dk.home_moneyline == -165  # unchanged by the firstToScore prop's +120


def test_book_entry_marked_unavailable_is_excluded():
    event = sample_event()
    event["odds"]["points-home-game-ml-home"]["byBookmaker"]["betmgm"] = {"odds": "-999", "available": False}
    result = normalize_sportsgameodds_event(event, RETRIEVED_AT)
    assert all(b.book != "betmgm" for b in result.books)
