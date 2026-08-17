from research.game_environment.providers.normalizer import normalize_sportsgameodds_event

RETRIEVED_AT = "2026-08-17T18:00:00+00:00"


def sample_event(**overrides):
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
                "sideID": "home",
                "byBookmaker": {
                    "draftkings": {"odds": "-165", "lastUpdatedAt": "2026-08-17T17:00:00Z"},
                    "fanduel": {"odds": "-160"},
                },
            },
            "points-away-game-ml-away": {
                "sideID": "away",
                "byBookmaker": {
                    "draftkings": {"odds": "140"},
                    "fanduel": {"odds": "135"},
                },
            },
            "points-all-game-ou-over": {
                "sideID": "over",
                "byBookmaker": {
                    "draftkings": {"odds": "-110", "overUnder": "8.5"},
                    "fanduel": {"odds": "-105", "overUnder": "8.5"},
                },
            },
            "points-all-game-ou-under": {
                "sideID": "under",
                "byBookmaker": {
                    "draftkings": {"odds": "-110", "overUnder": "8.5"},
                    "fanduel": {"odds": "-115", "overUnder": "8.5"},
                },
            },
            "points-home-game-sp-home": {
                "sideID": "home",
                "byBookmaker": {
                    "draftkings": {"odds": "-110", "spread": "-1.5"},
                },
            },
            "points-away-game-sp-away": {
                "sideID": "away",
                "byBookmaker": {
                    "draftkings": {"odds": "-110", "spread": "1.5"},
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
                "sideID": "home",
                "bookOdds": {"betmgm": {"odds": "-155"}},
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
                "sideID": "home",
                "byBookmaker": {"draftkings": {"odds": "-110"}},
            },
        }
    )
    result = normalize_sportsgameodds_event(event, RETRIEVED_AT)
    assert result is not None
    assert result.books == []
