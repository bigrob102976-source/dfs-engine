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


def test_build_live_pregame_hitter_features_weather_is_missing_when_no_snapshot_supplied(monkeypatch):
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


# ---------------------------------------------------------------------------
# M32.7A -- real weather mapping (_map_weather_features), see
# big_money_ml/live_hitter_features.py's module docstring for the exact
# field-by-field rationale.
# ---------------------------------------------------------------------------

def _reading(**overrides):
    base = {
        "temperature_f": 78.5, "humidity_percent": 62.0, "wind_speed_mph": 9.3,
        "wind_direction_degrees": 210.0, "feels_like_f": 80.1, "rain_percent": 10.0,
        "air_density": 1.18, "precipitation_probability_percent": 15.0,
        "precipitation_amount_mm": 0.4, "weather_code": 2, "wind_gusts_mph": 14.0,
    }
    base.update(overrides)
    return base


def _weather_snapshot(is_mock=False, roof_status="open", first_pitch=None):
    reading = first_pitch if first_pitch is not None else _reading()
    return {
        "game_id": "g1", "provider_name": "Open-Meteo", "is_mock": is_mock, "retrieved_at": "2026-08-23T18:00:00Z",
        "roof_status": roof_status, "delay_risk_percent": 0.0, "postponement_risk_percent": None,
        "current": _reading(), "first_pitch": reading, "mid_game": _reading(), "late_game": _reading(),
        "weather_risk_percent": 5.0, "weather_status": "Low disruption risk.",
    }


def test_map_weather_features_real_snapshot_marks_available_true():
    result = live_hitter_features._map_weather_features(_weather_snapshot())
    assert result["weather_available"] is True


def test_map_weather_features_maps_temperature_from_first_pitch_reading():
    result = live_hitter_features._map_weather_features(_weather_snapshot(first_pitch=_reading(temperature_f=91.2)))
    assert result["weather_temperature_f"] == 91.2


def test_map_weather_features_maps_wind_speed_from_first_pitch_reading():
    result = live_hitter_features._map_weather_features(_weather_snapshot(first_pitch=_reading(wind_speed_mph=17.6)))
    assert result["weather_wind_speed_mph"] == 17.6


def test_map_weather_features_maps_wind_direction_from_first_pitch_reading():
    result = live_hitter_features._map_weather_features(_weather_snapshot(first_pitch=_reading(wind_direction_degrees=305.0)))
    assert result["weather_wind_direction_deg"] == 305.0


def test_map_weather_features_maps_precipitation_amount_not_probability():
    """weather_precipitation must map to precipitation_amount_mm (the
    forecast AMOUNT, matching Open-Meteo's raw "precipitation" hourly
    field the model was trained on) -- NEVER
    precipitation_probability_percent, a different signal entirely."""
    result = live_hitter_features._map_weather_features(
        _weather_snapshot(first_pitch=_reading(precipitation_amount_mm=2.3, precipitation_probability_percent=90.0))
    )
    assert result["weather_precipitation"] == 2.3


def test_map_weather_features_maps_humidity_from_first_pitch_reading():
    result = live_hitter_features._map_weather_features(_weather_snapshot(first_pitch=_reading(humidity_percent=71.5)))
    assert result["weather_humidity_pct"] == 71.5


def test_map_weather_features_never_uses_current_reading_only_first_pitch():
    snapshot = _weather_snapshot()
    snapshot["current"] = _reading(temperature_f=999.0)  # decoy -- must never be read
    snapshot["first_pitch"] = _reading(temperature_f=75.0)
    result = live_hitter_features._map_weather_features(snapshot)
    assert result["weather_temperature_f"] == 75.0


def test_map_weather_features_none_snapshot_stays_honestly_missing():
    result = live_hitter_features._map_weather_features(None)
    assert result["weather_available"] is False
    for col in ("weather_temperature_f", "weather_wind_speed_mph", "weather_wind_direction_deg", "weather_precipitation", "weather_humidity_pct"):
        assert result[col] is None


def test_map_weather_features_mock_provider_snapshot_treated_as_unavailable():
    """A mock GameEnvironmentReport (GAME_ENVIRONMENT_PROVIDER=mock) must
    never be treated as real weather -- weather_available stays False
    even though a snapshot object technically exists."""
    result = live_hitter_features._map_weather_features(_weather_snapshot(is_mock=True))
    assert result["weather_available"] is False
    for col in ("weather_temperature_f", "weather_wind_speed_mph", "weather_wind_direction_deg", "weather_precipitation", "weather_humidity_pct"):
        assert result[col] is None


def test_map_weather_features_never_fabricates_a_default_when_a_reading_field_is_null():
    """A real (is_mock=False) snapshot whose first_pitch reading is
    missing some individual field (e.g. a partial provider response)
    must preserve that field as None -- never substitute 0/70/50%."""
    result = live_hitter_features._map_weather_features(
        _weather_snapshot(first_pitch=_reading(temperature_f=None, wind_speed_mph=None, precipitation_amount_mm=None))
    )
    assert result["weather_available"] is True  # the snapshot itself is real
    assert result["weather_temperature_f"] is None
    assert result["weather_wind_speed_mph"] is None
    assert result["weather_precipitation"] is None


def test_map_weather_features_dome_game_uses_the_existing_real_indoor_reading_honestly():
    """Indoor/dome behavior: research/game_environment/weather.py's real
    OpenMeteoWeatherProvider already substitutes a documented, constant
    indoor-climate reading for roof_status in ("dome", "closed") and
    still marks is_mock=False (see that module) -- this is the existing,
    correct representation this milestone is told to preserve, not
    invent a second one here."""
    indoor_reading = _reading(
        temperature_f=72.0, humidity_percent=45.0, wind_speed_mph=0.0, wind_direction_degrees=0.0,
        precipitation_amount_mm=0.0,
    )
    result = live_hitter_features._map_weather_features(_weather_snapshot(roof_status="dome", first_pitch=indoor_reading))
    assert result["weather_available"] is True
    assert result["weather_temperature_f"] == 72.0
    assert result["weather_wind_speed_mph"] == 0.0
    assert result["weather_precipitation"] == 0.0


def test_build_live_pregame_hitter_features_maps_real_weather_when_snapshot_supplied(monkeypatch):
    """End-to-end plumbing proof: passing a real weather_snapshot through
    build_live_pregame_hitter_features actually reaches the returned
    feature row, restoring AFTER_LINEUP hitter inference's weather
    features."""
    monkeypatch.setattr(live_hitter_features, "fetch_batter_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_hitter_features, "fetch_person", _no_person_lookup)
    monkeypatch.setattr(live_hitter_features, "fetch_pitcher_game_log", lambda player_id, season: None)
    buffer = LiveStatcastBuffer()

    result = build_live_pregame_hitter_features(
        player_id="999", team="NYY", opponent="BOS", home_away="home",
        as_of_date="2026-08-22", venue_id=15, statcast_buffer=buffer,
        opposing_starter_id="111", batting_order_actual=2,
        weather_snapshot=_weather_snapshot(first_pitch=_reading(temperature_f=84.0, wind_speed_mph=6.0)),
    )
    assert result.features["weather_available"] is True
    assert result.features["weather_temperature_f"] == 84.0
    assert result.features["weather_wind_speed_mph"] == 6.0


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


def test_opposing_pitcher_cache_avoids_refetching_for_a_shared_opposing_starter(monkeypatch):
    """Milestone 32.4 performance optimization: two hitters facing the
    SAME opposing starter within one shared cache dict must trigger only
    ONE fetch_person/fetch_pitcher_game_log call for that starter, not two."""
    monkeypatch.setattr(live_hitter_features, "fetch_batter_game_log", lambda player_id, season: None)

    call_counts = {"person": 0, "game_log": 0}

    def counting_person(player_id):
        if player_id == "111":
            call_counts["person"] += 1
        return {"batSide": {"code": "R"}, "pitchHand": {"code": "L"}}

    def counting_game_log(player_id, season):
        if player_id == "111":
            call_counts["game_log"] += 1
        return None

    monkeypatch.setattr(live_hitter_features, "fetch_person", counting_person)
    monkeypatch.setattr(live_hitter_features, "fetch_pitcher_game_log", counting_game_log)

    buffer = LiveStatcastBuffer()
    shared_cache: dict = {}

    for player_id in ("100", "200"):
        build_live_pregame_hitter_features(
            player_id=player_id, team="NYY", opponent="BOS", home_away="home",
            as_of_date="2026-08-22", venue_id=15, statcast_buffer=buffer,
            opposing_starter_id="111", batting_order_actual=2,
            opposing_pitcher_cache=shared_cache,
        )

    assert call_counts["person"] == 1
    assert call_counts["game_log"] == 1


def test_opposing_pitcher_cache_still_produces_correct_values_for_every_hitter(monkeypatch):
    """The cache must never change the RESULT -- both hitters facing the
    same opposing starter must see identical opposing_* feature values."""
    monkeypatch.setattr(live_hitter_features, "fetch_batter_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_hitter_features, "fetch_person", lambda player_id: {"batSide": {"code": "R"}, "pitchHand": {"code": "L"}})
    monkeypatch.setattr(live_hitter_features, "fetch_pitcher_game_log", lambda player_id, season: None)

    buffer = LiveStatcastBuffer()
    shared_cache: dict = {}
    results = [
        build_live_pregame_hitter_features(
            player_id=player_id, team="NYY", opponent="BOS", home_away="home",
            as_of_date="2026-08-22", venue_id=15, statcast_buffer=buffer,
            opposing_starter_id="111", batting_order_actual=2,
            opposing_pitcher_cache=shared_cache,
        )
        for player_id in ("100", "200")
    ]
    assert results[0].features["opposing_starting_pitcher_hand"] == results[1].features["opposing_starting_pitcher_hand"] == "L"


def test_no_current_slate_imputation_fitting():
    """Train-time imputation statistics come only from the frozen
    artifact's own preprocessor. This module only ever COMPUTES raw
    feature values, never touches sklearn."""
    import inspect

    source = inspect.getsource(live_hitter_features)
    for forbidden in ("SimpleImputer", "fit(", "fit_transform"):
        assert forbidden not in source, f"live_hitter_features.py must never fit an imputer/model against live data: found {forbidden!r}"
