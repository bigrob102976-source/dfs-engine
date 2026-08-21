"""Milestone 32.0 -- historical_mlb/game_crosswalk.py. No network calls."""

import pytest

from historical_mlb.game_crosswalk import (
    build_game_index,
    crosswalk_row_from_schedule_game,
    fallback_key,
)


def test_fallback_key_includes_game_number():
    k1 = fallback_key("2025-06-15", "CIN", "DET", game_number=1)
    k2 = fallback_key("2025-06-15", "CIN", "DET", game_number=2)
    assert k1 != k2  # doubleheader games must never collide


def test_crosswalk_row_from_schedule_game_prefers_game_pk():
    game = {"game_pk": 777505, "game_date": "2025-06-15", "away_team": "Cincinnati Reds", "home_team": "Detroit Tigers", "game_number": 1}
    row = crosswalk_row_from_schedule_game(game)
    assert row.canonical_game_id == "777505"
    assert row.game_pk == 777505


def test_crosswalk_row_from_schedule_game_falls_back_without_game_pk():
    game = {"game_pk": None, "game_date": "2025-06-15", "away_team": "CIN", "home_team": "DET", "game_number": 2}
    row = crosswalk_row_from_schedule_game(game)
    assert row.canonical_game_id == "2025-06-15:CIN:DET:g2"


def test_build_game_index_raises_on_duplicate_game_pk():
    rows = [
        crosswalk_row_from_schedule_game({"game_pk": 1, "game_date": "2025-06-15", "away_team": "A", "home_team": "B", "game_number": 1}),
        crosswalk_row_from_schedule_game({"game_pk": 1, "game_date": "2025-06-15", "away_team": "A", "home_team": "B", "game_number": 1}),
    ]
    with pytest.raises(ValueError):
        build_game_index(rows)


def test_build_game_index_keeps_doubleheader_games_distinct():
    rows = [
        crosswalk_row_from_schedule_game({"game_pk": None, "game_date": "2025-06-15", "away_team": "A", "home_team": "B", "game_number": 1}),
        crosswalk_row_from_schedule_game({"game_pk": None, "game_date": "2025-06-15", "away_team": "A", "home_team": "B", "game_number": 2}),
    ]
    index = build_game_index(rows)
    assert len(index) == 2  # not silently merged
