"""Milestone 32.0 -- historical_mlb/sources/*.py PARSING logic only. No
live network calls -- every fixture below is a small, hand-written
payload shaped exactly like the real API response this audit's live
testing confirmed (see M32.0's final report)."""

from historical_mlb.sources.mlb_stats import (
    extract_all_boxscore_players,
    games_from_schedule,
    person_handedness,
)
from historical_mlb.sources.odds import parse_historical_odds_csv
from historical_mlb.sources.salaries import parse_historical_salary_csv
from historical_mlb.sources.statcast import parse_statcast_csv

SCHEDULE_FIXTURE = {
    "dates": [{
        "date": "2025-06-15",
        "games": [
            {
                "gamePk": 777505, "gameNumber": 1, "doubleHeader": "N",
                "status": {"detailedState": "Final"},
                "teams": {
                    "away": {"team": {"id": 113, "name": "Cincinnati Reds"}, "probablePitcher": {"id": 489119, "fullName": "Wade Miley"}},
                    "home": {"team": {"id": 116, "name": "Detroit Tigers"}, "probablePitcher": {"id": 592791, "fullName": "Tarik Skubal"}},
                },
                "venue": {"name": "Comerica Park"},
            },
        ],
    }],
}

BOXSCORE_FIXTURE = {
    "teams": {
        "away": {
            "team": {"abbreviation": "CIN"},
            "players": {
                "ID656941": {"person": {"fullName": "Test Pitcher"}, "stats": {"pitching": {"inningsPitched": "6.0", "strikeOuts": 5}}},
                "ID000001": {"person": {"fullName": "No Stats Player"}, "stats": {}},  # never appeared -- must be skipped entirely
            },
        },
        "home": {
            "team": {"abbreviation": "DET"},
            "players": {
                "ID656716": {"person": {"fullName": "Test Hitter"}, "stats": {"batting": {"hits": 2, "atBats": 4}}},
                "ID656717": {"person": {"fullName": "Two-Way Player"}, "stats": {"batting": {"hits": 1}, "pitching": {"inningsPitched": "1.0"}}},
            },
        },
    },
}


def test_games_from_schedule_flattens_and_preserves_doubleheader_fields():
    games = games_from_schedule(SCHEDULE_FIXTURE)
    assert len(games) == 1
    g = games[0]
    assert g["game_pk"] == 777505
    assert g["game_number"] == 1
    assert g["away_team"] == "Cincinnati Reds"
    assert g["home_team"] == "Detroit Tigers"
    assert g["away_probable_pitcher_id"] == 489119
    assert g["status"] == "Final"


def test_extract_all_boxscore_players_splits_pitchers_and_hitters():
    pitchers, hitters = extract_all_boxscore_players(BOXSCORE_FIXTURE)
    pitcher_ids = {p["player_id"] for p in pitchers}
    hitter_ids = {h["player_id"] for h in hitters}
    assert "656941" in pitcher_ids
    assert "656716" in hitter_ids
    assert "000001" not in pitcher_ids and "000001" not in hitter_ids  # never appeared -- correctly skipped


def test_extract_all_boxscore_players_handles_two_way_player_in_both_lists():
    pitchers, hitters = extract_all_boxscore_players(BOXSCORE_FIXTURE)
    assert "656717" in {p["player_id"] for p in pitchers}
    assert "656717" in {h["player_id"] for h in hitters}


def test_extract_all_boxscore_players_carries_team_abbreviation():
    pitchers, _ = extract_all_boxscore_players(BOXSCORE_FIXTURE)
    away_pitcher = next(p for p in pitchers if p["player_id"] == "656941")
    assert away_pitcher["team"] == "CIN"


def test_person_handedness_from_already_unwrapped_fetch_person_result():
    # research.collector.fetch_person() already unwraps the {"people":
    # [...]} envelope -- this fixture matches that ALREADY-UNWRAPPED
    # shape (regression guard for the bug found during this milestone's
    # own live POC run).
    person = {"batSide": {"code": "L"}, "pitchHand": {"code": "R"}, "primaryPosition": {"abbreviation": "OF"}}
    hand = person_handedness(person)
    assert hand == {"bat_side": "L", "throw_hand": "R", "primary_position": "OF"}


def test_person_handedness_none_input_returns_all_none_not_crash():
    hand = person_handedness(None)
    assert hand == {"bat_side": None, "throw_hand": None, "primary_position": None}


def test_parse_statcast_csv():
    csv_text = "game_date,batter,pitcher,launch_speed,launch_angle\r\n2025-06-15,592450,543135,98.5,27\r\n"
    rows = parse_statcast_csv(csv_text)
    assert len(rows) == 1
    assert rows[0]["batter"] == "592450"
    assert rows[0]["launch_speed"] == "98.5"


def test_parse_statcast_csv_handles_bom():
    csv_text = "﻿game_date,batter\r\n2025-06-15,592450\r\n"
    rows = parse_statcast_csv(csv_text)
    assert rows[0]["batter"] == "592450"


def test_parse_historical_salary_csv_rotoguru_style_columns():
    csv_text = "GID,Name,Team,Oppt,DKSlot,DKSal\n1,Aaron Judge,NYY,BOS,OF,6200\n"
    rows = parse_historical_salary_csv(csv_text)
    assert rows[0]["player"] == "Aaron Judge"
    assert rows[0]["team"] == "NYY"
    assert rows[0]["salary"] == 6200


def test_parse_historical_salary_csv_plain_columns_with_date_fallback():
    csv_text = "player,team,position,salary\nShohei Ohtani,LAD,SP,10500\n"
    rows = parse_historical_salary_csv(csv_text, date="2025-06-15")
    assert rows[0]["date"] == "2025-06-15"  # date fallback used since no date column
    assert rows[0]["salary"] == 10500


def test_parse_historical_salary_csv_bad_salary_value_is_none_not_crash():
    csv_text = "player,team,position,salary\nSome Player,NYY,OF,N/A\n"
    rows = parse_historical_salary_csv(csv_text)
    assert rows[0]["salary"] is None


def test_parse_historical_odds_csv():
    csv_text = "date,away_team,home_team,away_ml,home_ml,total\n2025-06-15,CIN,DET,150,-170,8.5\n"
    rows = parse_historical_odds_csv(csv_text)
    assert rows[0]["away_team"] == "CIN"
    assert rows[0]["total"] == "8.5"


def test_parse_historical_odds_csv_unrecognized_columns_ignored_not_error():
    csv_text = "some_weird_column,date\nxyz,2025-06-15\n"
    rows = parse_historical_odds_csv(csv_text)
    assert rows[0]["date"] == "2025-06-15"
    assert rows[0]["away_team"] is None
