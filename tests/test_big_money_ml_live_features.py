"""Milestone 32.2B -- live pregame feature construction tests. All
network fetchers are monkeypatched -- zero real HTTP calls. Proves the
SAME rolling/statcast aggregation math training used produces sane,
leakage-safe values from live-shaped inputs, and that nothing on/after
as_of_date ever enters a feature."""

import big_money_ml.live_features as live_features
from big_money_ml.live_features import (
    LiveStatcastBuffer,
    _person_handedness,
    _previous_start,
    _unwrap_game_log,
    build_live_pregame_pitcher_features,
)
from historical_models.pitcher_v1.features import FEATURE_COLUMNS


def _game_log_entry(date, **stat_overrides):
    stat = {
        "inningsPitched": "6.0", "battersFaced": 24, "strikeOuts": 7, "baseOnBalls": 2,
        "hits": 5, "earnedRuns": 2, "homeRuns": 1, "numberOfPitches": 95,
    }
    stat.update(stat_overrides)
    return {"date": date, "stat": stat}


def test_unwrap_game_log_flattens_mlb_stats_api_envelope():
    raw = {"stats": [{"splits": [{"date": "2026-08-01", "stat": {"strikeOuts": 5}}]}]}
    assert _unwrap_game_log(raw) == [{"date": "2026-08-01", "stat": {"strikeOuts": 5}}]


def test_unwrap_game_log_handles_none_and_empty_gracefully():
    assert _unwrap_game_log(None) == []
    assert _unwrap_game_log({}) == []
    assert _unwrap_game_log({"stats": []}) == []


def test_person_handedness_extracts_bat_and_throw_side():
    person = {"batSide": {"code": "L"}, "pitchHand": {"code": "R"}}
    assert _person_handedness(person) == {"bat_side": "L", "throw_hand": "R"}


def test_person_handedness_returns_none_for_missing_person():
    assert _person_handedness(None) == {"bat_side": None, "throw_hand": None}


def test_previous_start_excludes_same_day_and_future_entries():
    log = [_game_log_entry("2026-08-10"), _game_log_entry("2026-08-15"), _game_log_entry("2026-08-20")]
    previous = _previous_start(log, "2026-08-15")
    assert previous["date"] == "2026-08-10"  # 08-15 itself and anything after must never be picked


def test_previous_start_returns_none_when_no_prior_appearance():
    log = [_game_log_entry("2026-08-20")]
    assert _previous_start(log, "2026-08-15") is None


def test_live_statcast_buffer_evicts_rows_older_than_lookback(monkeypatch):
    calls = []

    def fake_fetch(date, force=False):
        calls.append(date)
        return f"game_date,pitcher\n{date},999\n"

    monkeypatch.setattr(live_features, "fetch_cached_statcast_csv_text", fake_fetch)
    buffer = LiveStatcastBuffer(lookback_days=5)
    buffer.advance_to("2026-08-01")
    buffer.advance_to("2026-08-10")  # 9 days later -- should evict 2026-08-01
    dates_remaining = {r["game_date"] for r in buffer.rows()}
    assert "2026-08-01" not in dates_remaining
    assert "2026-08-10" in dates_remaining


def test_build_live_pregame_pitcher_features_never_includes_data_on_or_after_as_of_date(monkeypatch):
    log = [_game_log_entry("2026-08-10"), _game_log_entry("2026-08-15")]  # 08-15 is the target date itself

    monkeypatch.setattr(live_features, "fetch_pitcher_game_log", lambda player_id, season: {"stats": [{"splits": [{"date": e["date"], "stat": e["stat"]} for e in log]}]})
    monkeypatch.setattr(live_features, "fetch_person", lambda player_id: {"batSide": {"code": "R"}, "pitchHand": {"code": "R"}})

    buffer = LiveStatcastBuffer()  # empty -- no advance_to calls, no network

    result = build_live_pregame_pitcher_features(
        player_id="123", team="NYY", opponent="BOS", home_away="home",
        as_of_date="2026-08-15", venue_id=15, statcast_buffer=buffer,
    )

    # Only the 08-10 start should count -- rolling_starts_season must be 1, not 2.
    assert result.features["rolling_starts_season"] == 1
    assert result.features["days_rest"] == 5  # 08-10 -> 08-15


def test_build_live_pregame_pitcher_features_returns_every_feature_column(monkeypatch):
    monkeypatch.setattr(live_features, "fetch_pitcher_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_features, "fetch_person", lambda player_id: None)
    buffer = LiveStatcastBuffer()

    result = build_live_pregame_pitcher_features(
        player_id="999", team="NYY", opponent="BOS", home_away="away",
        as_of_date="2026-08-22", venue_id=15, statcast_buffer=buffer,
    )
    for col in FEATURE_COLUMNS:
        assert col in result.features, f"missing feature column: {col}"


def test_build_live_pregame_pitcher_features_weather_is_always_missing_never_fabricated(monkeypatch):
    monkeypatch.setattr(live_features, "fetch_pitcher_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_features, "fetch_person", lambda player_id: None)
    buffer = LiveStatcastBuffer()

    result = build_live_pregame_pitcher_features(
        player_id="999", team="NYY", opponent="BOS", home_away="home",
        as_of_date="2026-08-22", venue_id=15, statcast_buffer=buffer,
    )
    assert result.features["weather_available"] is False
    for col in ("weather_temperature_f", "weather_wind_speed_mph", "weather_wind_direction_deg", "weather_precipitation", "weather_humidity_pct"):
        assert result.features[col] is None


def test_build_live_pregame_pitcher_features_home_away_selects_correct_roof_team(monkeypatch):
    monkeypatch.setattr(live_features, "fetch_pitcher_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_features, "fetch_person", lambda player_id: None)
    buffer = LiveStatcastBuffer()

    away_result = build_live_pregame_pitcher_features(
        player_id="999", team="NYY", opponent="TB", home_away="away",
        as_of_date="2026-08-22", venue_id=12, statcast_buffer=buffer,
    )
    home_result = build_live_pregame_pitcher_features(
        player_id="999", team="TB", opponent="NYY", home_away="home",
        as_of_date="2026-08-22", venue_id=12, statcast_buffer=buffer,
    )
    # Away pitcher's roof lookup should use the OPPONENT (home) team, not his own team.
    assert away_result.features["venue_roof_type"] == home_result.features["venue_roof_type"]


def test_no_current_slate_imputation_fitting():
    """Train-time imputation statistics come only from the frozen
    artifact's own preprocessor (fit on TRAIN data during M32.2). This
    module never fits/refits any imputer against today's slate -- it
    only ever COMPUTES raw feature values, never touches sklearn."""
    import inspect

    source = inspect.getsource(live_features)
    for forbidden in ("SimpleImputer", "fit(", "fit_transform"):
        assert forbidden not in source, f"live_features.py must never fit an imputer/model against live data: found {forbidden!r}"
