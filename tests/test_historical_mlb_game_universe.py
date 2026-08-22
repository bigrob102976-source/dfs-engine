"""Milestone 32.1, Part 1/7 -- game_universe.py. No network calls."""

from historical_mlb.game_universe import build_game_universe, games_for_date

SCHEDULE_FIXTURE = {
    "dates": [
        {
            "date": "2025-03-20",
            "games": [
                {  # spring training -- must be excluded
                    "gamePk": 1, "gameType": "S", "season": 2025, "officialDate": "2025-03-20", "gameNumber": 1,
                    "status": {"abstractGameState": "Final", "detailedState": "Final"},
                    "teams": {
                        "away": {"team": {"id": 1, "name": "A", "abbreviation": "AAA"}},
                        "home": {"team": {"id": 2, "name": "B", "abbreviation": "BBB"}},
                    },
                    "venue": {"id": 10, "name": "Spring Park"},
                },
            ],
        },
        {
            "date": "2025-06-15",
            "games": [
                {  # regular season, Final -- included
                    "gamePk": 2, "gameType": "R", "season": 2025, "officialDate": "2025-06-15", "gameNumber": 1,
                    "status": {"abstractGameState": "Final", "detailedState": "Final"},
                    "teams": {
                        "away": {"team": {"id": 3, "name": "Cincinnati Reds", "abbreviation": "CIN"}},
                        "home": {"team": {"id": 4, "name": "Detroit Tigers", "abbreviation": "DET"}},
                    },
                    "venue": {"id": 20, "name": "Comerica Park"},
                    "gameDate": "2025-06-15T22:40:00Z",
                    "doubleHeader": "N",
                },
                {  # regular season, postponed -- must be excluded (unsafe outcome)
                    "gamePk": 3, "gameType": "R", "season": 2025, "officialDate": "2025-06-15", "gameNumber": 1,
                    "status": {"abstractGameState": "Preview", "detailedState": "Postponed"},
                    "teams": {
                        "away": {"team": {"id": 5, "name": "C", "abbreviation": "CCC"}},
                        "home": {"team": {"id": 6, "name": "D", "abbreviation": "DDD"}},
                    },
                    "venue": {"id": 30, "name": "Rain Park"},
                },
                {  # doubleheader game 1
                    "gamePk": 4, "gameType": "R", "season": 2025, "officialDate": "2025-06-15", "gameNumber": 1,
                    "status": {"abstractGameState": "Final", "detailedState": "Final"},
                    "teams": {
                        "away": {"team": {"id": 7, "name": "E", "abbreviation": "EEE"}},
                        "home": {"team": {"id": 8, "name": "F", "abbreviation": "FFF"}},
                    },
                    "venue": {"id": 40, "name": "DH Park"},
                    "doubleHeader": "Y",
                },
                {  # doubleheader game 2 -- same date/teams, different gameNumber
                    "gamePk": 5, "gameType": "R", "season": 2025, "officialDate": "2025-06-15", "gameNumber": 2,
                    "status": {"abstractGameState": "Final", "detailedState": "Final"},
                    "teams": {
                        "away": {"team": {"id": 7, "name": "E", "abbreviation": "EEE"}},
                        "home": {"team": {"id": 8, "name": "F", "abbreviation": "FFF"}},
                    },
                    "venue": {"id": 40, "name": "DH Park"},
                    "doubleHeader": "Y",
                },
            ],
        },
        {
            "date": "2025-10-05",
            "games": [
                {  # postseason -- must be excluded
                    "gamePk": 6, "gameType": "F", "season": 2025, "officialDate": "2025-10-05", "gameNumber": 1,
                    "status": {"abstractGameState": "Final", "detailedState": "Final"},
                    "teams": {
                        "away": {"team": {"id": 1, "name": "A", "abbreviation": "AAA"}},
                        "home": {"team": {"id": 2, "name": "B", "abbreviation": "BBB"}},
                    },
                    "venue": {"id": 10, "name": "Playoff Park"},
                },
            ],
        },
    ],
}


def test_build_game_universe_excludes_spring_training(monkeypatch):
    monkeypatch.setattr("historical_mlb.game_universe.fetch_schedule_range", lambda s, e: SCHEDULE_FIXTURE)
    rows = build_game_universe("2025-03-01", "2025-10-31")
    assert all(r.game_pk != 1 for r in rows)


def test_build_game_universe_excludes_postponed(monkeypatch):
    monkeypatch.setattr("historical_mlb.game_universe.fetch_schedule_range", lambda s, e: SCHEDULE_FIXTURE)
    rows = build_game_universe("2025-03-01", "2025-10-31")
    assert all(r.game_pk != 3 for r in rows)


def test_build_game_universe_excludes_postseason(monkeypatch):
    monkeypatch.setattr("historical_mlb.game_universe.fetch_schedule_range", lambda s, e: SCHEDULE_FIXTURE)
    rows = build_game_universe("2025-03-01", "2025-10-31")
    assert all(r.game_pk != 6 for r in rows)


def test_build_game_universe_includes_regular_season_final(monkeypatch):
    monkeypatch.setattr("historical_mlb.game_universe.fetch_schedule_range", lambda s, e: SCHEDULE_FIXTURE)
    rows = build_game_universe("2025-03-01", "2025-10-31")
    game = next(r for r in rows if r.game_pk == 2)
    assert game.away_team == "CIN"
    assert game.home_team == "DET"
    assert game.venue_id == 20


def test_build_game_universe_keeps_doubleheader_games_distinct(monkeypatch):
    monkeypatch.setattr("historical_mlb.game_universe.fetch_schedule_range", lambda s, e: SCHEDULE_FIXTURE)
    rows = build_game_universe("2025-03-01", "2025-10-31")
    dh_games = [r for r in rows if r.game_pk in (4, 5)]
    assert len(dh_games) == 2
    assert {g.game_number for g in dh_games} == {1, 2}
    assert len({g.game_pk for g in dh_games}) == 2  # never merged into one row


def test_games_for_date_filters_correctly(monkeypatch):
    monkeypatch.setattr("historical_mlb.game_universe.fetch_schedule_range", lambda s, e: SCHEDULE_FIXTURE)
    rows = build_game_universe("2025-03-01", "2025-10-31")
    june15 = games_for_date(rows, "2025-06-15")
    assert {g.game_pk for g in june15} == {2, 4, 5}  # game 3 postponed, excluded upstream already


def _dh_game(pk, game_number, matchup_date="2024-04-04"):
    return {
        "gamePk": pk, "gameType": "R", "season": 2024, "officialDate": matchup_date, "gameNumber": game_number,
        "status": {"abstractGameState": "Final", "detailedState": "Final"},
        "teams": {
            "away": {"team": {"id": 1, "name": "Detroit Tigers", "abbreviation": "DET"}},
            "home": {"team": {"id": 2, "name": "New York Mets", "abbreviation": "NYM"}},
        },
        "venue": {"id": 30, "name": "Citi Field"},
        "gameDate": f"{matchup_date}T16:10:00Z",
        "doubleHeader": "Y",
    }


def test_build_game_universe_repairs_ambiguous_makeup_doubleheader_gamenumber(monkeypatch):
    """Regression guard for a real bug caught live during Milestone
    32.1's full warehouse build: MLB Stats API reports an AMBIGUOUS
    (both gameNumber=1) result for a postponement-MAKEUP doubleheader
    when queried via a wide startDate/endDate range, but the correct,
    distinct 1/2 when queried for that single day alone. This mock
    simulates exactly that: the wide-range call (s != e) returns the
    ambiguous pair; the narrow single-day repair call (s == e) returns
    the correct pair."""
    wide_range_fixture = {"dates": [{"date": "2024-04-04", "games": [_dh_game(100, 1), _dh_game(101, 1)]}]}
    narrow_repair_fixture = {"dates": [{"date": "2024-04-04", "games": [_dh_game(100, 1), _dh_game(101, 2)]}]}

    def fake_fetch(s, e):
        return narrow_repair_fixture if s == e else wide_range_fixture

    monkeypatch.setattr("historical_mlb.game_universe.fetch_schedule_range", fake_fetch)
    rows = build_game_universe("2024-04-01", "2024-04-10")
    dh = games_for_date(rows, "2024-04-04")
    assert len(dh) == 2
    assert {g.game_number for g in dh} == {1, 2}  # repaired -- no longer both 1
    assert {g.game_pk for g in dh} == {100, 101}  # game_pk (the true canonical id) is untouched by the repair


def test_build_game_universe_does_not_repair_already_distinct_doubleheaders(monkeypatch):
    """A genuinely correct doubleheader (already distinct gameNumber in
    the wide-range response) must never trigger a narrow re-fetch."""
    calls = []

    def fake_fetch(s, e):
        calls.append((s, e))
        return {"dates": [{"date": "2024-04-04", "games": [_dh_game(100, 1), _dh_game(101, 2)]}]}

    monkeypatch.setattr("historical_mlb.game_universe.fetch_schedule_range", fake_fetch)
    build_game_universe("2024-04-01", "2024-04-10")
    assert len(calls) == 1  # only the one wide-range call -- no repair re-fetch triggered
