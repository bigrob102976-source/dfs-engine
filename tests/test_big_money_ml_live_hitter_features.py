"""Milestone 32.3B -- live pregame HITTER feature construction tests.
All network fetchers are monkeypatched -- zero real HTTP calls. Mirrors
tests/test_big_money_ml_live_features.py exactly for the hitter side."""

import big_money_ml.live_hitter_features as live_hitter_features
from big_money_ml.live_features import LiveStatcastBuffer
from big_money_ml.live_hitter_features import build_live_pregame_hitter_features
from historical_models.hitter_v1.features import AFTER_LINEUP_FEATURE_COLUMNS


def _game_log_entry(date, **stat_overrides):
    stat = {
        "atBats": 4, "hits": 1, "doubles": 0, "triples": 0, "homeRuns": 0, "baseOnBalls": 0,
        "hitByPitch": 0, "sacFlies": 0, "strikeOuts": 1, "plateAppearances": 4, "stolenBases": 0,
        "runs": 0, "rbi": 0,
    }
    stat.update(stat_overrides)
    return {"date": date, "stat": stat}


def _no_person_lookup(player_id):
    return None


def test_build_live_pregame_hitter_features_never_includes_data_on_or_after_as_of_date(monkeypatch):
    log = [_game_log_entry("2026-08-10"), _game_log_entry("2026-08-15")]  # 08-15 is the target date itself

    monkeypatch.setattr(live_hitter_features, "fetch_batter_game_log", lambda player_id, season: {"stats": [{"splits": [{"date": e["date"], "stat": e["stat"]} for e in log]}]})
    monkeypatch.setattr(live_hitter_features, "fetch_person", _no_person_lookup)
    monkeypatch.setattr(live_hitter_features, "fetch_pitcher_game_log", lambda player_id, season: None)

    buffer = LiveStatcastBuffer()  # empty -- no advance_to calls, no network

    result = build_live_pregame_hitter_features(
        player_id="123", team="NYY", opponent="BOS", home_away="home",
        as_of_date="2026-08-15", venue_id=15, statcast_buffer=buffer,
        opposing_starter_id="999", batting_order_actual=3,
    )

    # Only the 08-10 game should count -- rolling_games_season must be 1, not 2.
    assert result.features["rolling_games_season"] == 1


def test_build_live_pregame_hitter_features_returns_every_feature_column(monkeypatch):
    monkeypatch.setattr(live_hitter_features, "fetch_batter_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_hitter_features, "fetch_person", _no_person_lookup)
    monkeypatch.setattr(live_hitter_features, "fetch_pitcher_game_log", lambda player_id, season: None)
    buffer = LiveStatcastBuffer()

    result = build_live_pregame_hitter_features(
        player_id="999", team="NYY", opponent="BOS", home_away="away",
        as_of_date="2026-08-22", venue_id=15, statcast_buffer=buffer,
        opposing_starter_id="111", batting_order_actual=2,
    )
    for col in AFTER_LINEUP_FEATURE_COLUMNS:
        assert col in result.features, f"missing feature column: {col}"


def test_build_live_pregame_hitter_features_weather_is_always_missing_never_fabricated(monkeypatch):
    monkeypatch.setattr(live_hitter_features, "fetch_batter_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_hitter_features, "fetch_person", _no_person_lookup)
    monkeypatch.setattr(live_hitter_features, "fetch_pitcher_game_log", lambda player_id, season: None)
    buffer = LiveStatcastBuffer()

    result = build_live_pregame_hitter_features(
        player_id="999", team="NYY", opponent="BOS", home_away="home",
        as_of_date="2026-08-22", venue_id=15, statcast_buffer=buffer,
        opposing_starter_id="111", batting_order_actual=2,
    )
    assert result.features["weather_available"] is False
    for col in ("weather_temperature_f", "weather_wind_speed_mph", "weather_wind_direction_deg", "weather_precipitation", "weather_humidity_pct"):
        assert result.features[col] is None


def test_build_live_pregame_hitter_features_batting_order_passed_through_unmodified(monkeypatch):
    monkeypatch.setattr(live_hitter_features, "fetch_batter_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_hitter_features, "fetch_person", _no_person_lookup)
    monkeypatch.setattr(live_hitter_features, "fetch_pitcher_game_log", lambda player_id, season: None)
    buffer = LiveStatcastBuffer()

    result = build_live_pregame_hitter_features(
        player_id="999", team="NYY", opponent="BOS", home_away="home",
        as_of_date="2026-08-22", venue_id=15, statcast_buffer=buffer,
        opposing_starter_id="111", batting_order_actual=7,
    )
    assert result.features["batting_order_actual"] == 7


def test_build_live_pregame_hitter_features_uses_opposing_starter_hand_and_season_rates(monkeypatch):
    monkeypatch.setattr(live_hitter_features, "fetch_batter_game_log", lambda player_id, season: None)

    def fake_person(player_id):
        if player_id == "111":  # the opposing starter
            return {"batSide": {"code": "R"}, "pitchHand": {"code": "L"}}
        return None

    monkeypatch.setattr(live_hitter_features, "fetch_person", fake_person)

    opp_log = {"stats": [{"splits": [{"date": "2026-08-01", "stat": {
        "inningsPitched": "6.0", "battersFaced": 24, "strikeOuts": 8, "baseOnBalls": 2,
        "hits": 4, "earnedRuns": 2, "homeRuns": 1, "numberOfPitches": 95,
    }}]}]}
    monkeypatch.setattr(live_hitter_features, "fetch_pitcher_game_log", lambda player_id, season: opp_log if player_id == "111" else None)

    buffer = LiveStatcastBuffer()
    result = build_live_pregame_hitter_features(
        player_id="999", team="NYY", opponent="BOS", home_away="home",
        as_of_date="2026-08-22", venue_id=15, statcast_buffer=buffer,
        opposing_starter_id="111", batting_order_actual=2,
    )
    assert result.features["opposing_starting_pitcher_hand"] == "L"
    assert result.features["opposing_pitcher_k_pct_season"] == round(8 / 24, 4)


def test_build_live_pregame_hitter_features_home_away_selects_correct_roof_team(monkeypatch):
    monkeypatch.setattr(live_hitter_features, "fetch_batter_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_hitter_features, "fetch_person", _no_person_lookup)
    monkeypatch.setattr(live_hitter_features, "fetch_pitcher_game_log", lambda player_id, season: None)
    buffer = LiveStatcastBuffer()

    away_result = build_live_pregame_hitter_features(
        player_id="999", team="NYY", opponent="TB", home_away="away",
        as_of_date="2026-08-22", venue_id=12, statcast_buffer=buffer,
        opposing_starter_id="111", batting_order_actual=2,
    )
    home_result = build_live_pregame_hitter_features(
        player_id="999", team="TB", opponent="NYY", home_away="home",
        as_of_date="2026-08-22", venue_id=12, statcast_buffer=buffer,
        opposing_starter_id="111", batting_order_actual=2,
    )
    assert away_result.features["venue_roof_type"] == home_result.features["venue_roof_type"]


def test_no_current_slate_imputation_fitting():
    """Train-time imputation statistics come only from the frozen
    artifact's own preprocessor. This module only ever COMPUTES raw
    feature values, never touches sklearn."""
    import inspect

    source = inspect.getsource(live_hitter_features)
    for forbidden in ("SimpleImputer", "fit(", "fit_transform"):
        assert forbidden not in source, f"live_hitter_features.py must never fit an imputer/model against live data: found {forbidden!r}"
