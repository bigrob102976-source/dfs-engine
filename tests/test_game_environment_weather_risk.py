from research.game_environment.weather_risk import compute_weather_risk, weather_risk_status


def test_empty_window_returns_none_never_a_fabricated_score():
    assert compute_weather_risk([]) == (None, None)


def test_clear_calm_hour_scores_near_zero():
    risk, status = compute_weather_risk([{"precipitation_probability": 0, "precipitation": 0.0, "weather_code": 0, "wind_gusts_mph": 5.0}])
    assert risk == 0.0
    assert status == "Low disruption risk"


def test_thunderstorm_hour_scores_high():
    risk, status = compute_weather_risk([{"precipitation_probability": 95, "precipitation": 8.0, "weather_code": 95, "wind_gusts_mph": 30.0}])
    assert risk is not None and risk >= 60.0
    assert status == "High delay/postponement risk"


def test_uses_the_worst_hour_in_the_window_not_an_average():
    calm_hour = {"precipitation_probability": 0, "precipitation": 0.0, "weather_code": 0, "wind_gusts_mph": 0.0}
    storm_hour = {"precipitation_probability": 95, "precipitation": 8.0, "weather_code": 96, "wind_gusts_mph": 35.0}
    risk_with_storm, _ = compute_weather_risk([calm_hour, calm_hour, storm_hour, calm_hour])
    risk_all_calm, _ = compute_weather_risk([calm_hour, calm_hour, calm_hour, calm_hour])
    assert risk_with_storm > risk_all_calm
    # A single bad hour is enough to raise the whole window's score close
    # to what that one hour alone would produce -- not diluted 4x by averaging.
    risk_storm_alone, _ = compute_weather_risk([storm_hour])
    assert risk_with_storm == risk_storm_alone


def test_missing_fields_are_excluded_not_treated_as_zero():
    # A single hour with only wind_gusts populated -- risk should reflect
    # ONLY the wind sub-score (renormalized), not be diluted by treating
    # the other three missing signals as zero-risk.
    risk, _ = compute_weather_risk([{"wind_gusts_mph": 45.0}])
    assert risk == 100.0  # at/above the gust ceiling, wind is the only signal, fully weighted


def test_weather_risk_status_bands_match_configured_thresholds():
    assert weather_risk_status(0.0) == "Low disruption risk"
    assert weather_risk_status(29.99) == "Low disruption risk"
    assert weather_risk_status(30.0) == "Rain possible"
    assert weather_risk_status(59.99) == "Rain possible"
    assert weather_risk_status(60.0) == "High delay/postponement risk"
    assert weather_risk_status(100.0) == "High delay/postponement risk"


def test_never_treats_hot_temperature_as_weather_risk():
    """Part 6's explicit rule: temperature is NOT a disruption signal --
    compute_weather_risk doesn't even accept a temperature field, so a
    scorching-hot forecast can never inflate this score."""
    risk, _ = compute_weather_risk([{"precipitation_probability": 0, "precipitation": 0.0, "weather_code": 0, "wind_gusts_mph": 5.0}])
    assert risk == 0.0
