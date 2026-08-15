from projection_engine.signals import (
    bullpen_signal,
    external_gap_signal,
    matchup_signal,
    ownership_signal,
    park_signal,
    recent_form_signal,
    vegas_signal,
    weather_signal,
)

# ----------------------------------------------------------------------------
# weather_signal
# ----------------------------------------------------------------------------


def test_wind_out_favors_hitter_positive_and_cites_mph():
    analysis = {"conclusions": [{"code": "wind_strong_out", "text": "Strong wind blowing out.", "favors": "hitter"}]}
    weather = {"current": {"wind_speed_mph": 14.0}}
    signal = weather_signal("hitter", weather, analysis)
    assert signal.raw_delta > 0
    assert "Wind Out 14 MPH" in signal.reason


def test_wind_out_favors_hitter_is_negative_for_pitcher():
    analysis = {"conclusions": [{"code": "wind_strong_out", "text": "Strong wind blowing out.", "favors": "hitter"}]}
    weather = {"current": {"wind_speed_mph": 14.0}}
    signal = weather_signal("pitcher", weather, analysis)
    assert signal.raw_delta < 0


def test_wind_in_favors_pitcher():
    analysis = {"conclusions": [{"code": "wind_notable_in", "text": "Notable wind blowing in.", "favors": "pitcher"}]}
    weather = {"current": {"wind_speed_mph": 9.0}}
    signal = weather_signal("pitcher", weather, analysis)
    assert signal.raw_delta > 0
    assert "Wind In 9 MPH" in signal.reason


def test_risk_only_conclusions_produce_no_projection_signal():
    analysis = {"conclusions": [{"code": "rain_delay_risk", "text": "High rain delay risk.", "favors": "risk"}]}
    assert weather_signal("hitter", {}, analysis) is None


def test_no_conclusions_returns_none():
    assert weather_signal("hitter", {}, {"conclusions": []}) is None
    assert weather_signal("hitter", {}, None) is None


# ----------------------------------------------------------------------------
# vegas_signal
# ----------------------------------------------------------------------------


def test_high_total_game_favors_hitter():
    vegas = {"current_home": {"total": 11.0}, "home_implied_runs": 6.0, "away_implied_runs": 5.0, "total_movement": None}
    signal = vegas_signal("hitter", True, vegas)
    assert signal.raw_delta > 0
    assert "6.0 runs" in signal.reason


def test_high_total_game_disfavors_pitcher():
    vegas = {"current_home": {"total": 11.0}, "home_implied_runs": 6.0, "away_implied_runs": 5.0, "total_movement": None}
    signal = vegas_signal("pitcher", True, vegas)
    assert signal.raw_delta < 0


def test_low_total_game_favors_pitcher():
    vegas = {"current_home": {"total": 6.5}, "home_implied_runs": 3.0, "away_implied_runs": 3.5, "total_movement": None}
    signal = vegas_signal("pitcher", False, vegas)
    assert signal.raw_delta > 0


def test_positive_movement_favors_hitter():
    vegas = {"current_home": {"total": 8.5}, "home_implied_runs": 4.2, "away_implied_runs": 4.3, "total_movement": 1.2}
    signal = vegas_signal("hitter", True, vegas)
    assert signal.raw_delta > 0
    assert "moved up 1.2 runs" in signal.reason


def test_movement_is_capped():
    from config.projection_engine_config import VEGAS_MOVEMENT_MAX_POINTS

    vegas = {"current_home": {"total": 8.5}, "home_implied_runs": 4.2, "away_implied_runs": 4.3, "total_movement": 50.0}
    signal = vegas_signal("hitter", True, vegas)
    assert signal.raw_delta <= VEGAS_MOVEMENT_MAX_POINTS + 0.001


def test_missing_vegas_returns_none():
    assert vegas_signal("hitter", True, None) is None


# ----------------------------------------------------------------------------
# bullpen_signal
# ----------------------------------------------------------------------------


def test_pitcher_elite_rested_own_bullpen_is_negative():
    home = {"strength_score": 80.0, "estimated_fatigue": "low"}
    signal = bullpen_signal("pitcher", True, home, None)
    assert signal.raw_delta < 0
    assert "hook risk" in signal.reason


def test_pitcher_weak_own_bullpen_is_positive():
    home = {"strength_score": 20.0, "estimated_fatigue": "low"}
    signal = bullpen_signal("pitcher", True, home, None)
    assert signal.raw_delta > 0


def test_hitter_weak_opposing_bullpen_is_positive():
    away = {"strength_score": 20.0, "estimated_fatigue": "high"}
    signal = bullpen_signal("hitter", True, None, away)
    assert signal.raw_delta > 0
    assert "fatigued" in signal.reason


def test_hitter_elite_opposing_bullpen_is_negative():
    away = {"strength_score": 85.0, "estimated_fatigue": "low"}
    signal = bullpen_signal("hitter", True, None, away)
    assert signal.raw_delta < 0


def test_missing_strength_score_returns_none():
    assert bullpen_signal("pitcher", True, {"strength_score": None}, None) is None
    assert bullpen_signal("pitcher", True, None, None) is None


# ----------------------------------------------------------------------------
# park_signal
# ----------------------------------------------------------------------------


def test_hitter_friendly_park_is_positive_for_hitter():
    ballpark = {"hr_factor": 120, "venue_name": "Yankee Stadium"}
    signal = park_signal("hitter", ballpark)
    assert signal.raw_delta > 0
    assert "Yankee Stadium" in signal.reason


def test_hitter_friendly_park_is_negative_for_pitcher():
    ballpark = {"hr_factor": 120, "venue_name": "Yankee Stadium"}
    signal = park_signal("pitcher", ballpark)
    assert signal.raw_delta < 0


def test_neutral_park_returns_none():
    ballpark = {"hr_factor": 100, "venue_name": "Neutral Park"}
    assert park_signal("hitter", ballpark) is None


def test_missing_ballpark_returns_none():
    assert park_signal("hitter", None) is None


# ----------------------------------------------------------------------------
# ownership_signal
# ----------------------------------------------------------------------------


def test_high_ownership_fires_chalk_fade():
    signal = ownership_signal({"projected_ownership": 45.0, "leverage_score": 0.0})
    assert signal.raw_delta < 0
    assert "popular" in signal.reason


def test_high_leverage_fires_bonus():
    signal = ownership_signal({"projected_ownership": 5.0, "leverage_score": 30.0})
    assert signal.raw_delta > 0
    assert "leverage" in signal.reason


def test_both_fire_together():
    signal = ownership_signal({"projected_ownership": 45.0, "leverage_score": 30.0})
    assert "popular" in signal.reason and "leverage" in signal.reason


def test_neutral_ownership_returns_none():
    assert ownership_signal({"projected_ownership": 10.0, "leverage_score": 0.0}) is None


def test_missing_ownership_row_returns_none():
    assert ownership_signal(None) is None


# ----------------------------------------------------------------------------
# matchup_signal
# ----------------------------------------------------------------------------


def test_favorable_matchup_is_positive():
    signal = matchup_signal({"matchup_score": 80.0})
    assert signal.raw_delta > 0


def test_difficult_matchup_is_negative():
    signal = matchup_signal({"matchup_score": 20.0})
    assert signal.raw_delta < 0


def test_neutral_matchup_returns_none():
    assert matchup_signal({"matchup_score": 50.0}) is None


def test_missing_matchup_score_returns_none():
    assert matchup_signal({}) is None


# ----------------------------------------------------------------------------
# recent_form_signal
# ----------------------------------------------------------------------------


def test_hitter_improving_trend_positive():
    signal = recent_form_signal("hitter", {"recent_trend_score": 75.0})
    assert signal.raw_delta > 0


def test_hitter_declining_trend_negative():
    signal = recent_form_signal("hitter", {"recent_trend_score": 25.0})
    assert signal.raw_delta < 0


def test_pitcher_positive_trend_tag():
    signal = recent_form_signal("pitcher", {"tags": ["positive_trend"]})
    assert signal.raw_delta > 0


def test_pitcher_negative_trend_tag():
    signal = recent_form_signal("pitcher", {"tags": ["negative_trend"]})
    assert signal.raw_delta < 0


def test_pitcher_no_trend_tag_returns_none():
    assert recent_form_signal("pitcher", {"tags": ["elite_csw"]}) is None


def test_hitter_missing_trend_score_returns_none():
    assert recent_form_signal("hitter", {}) is None


# ----------------------------------------------------------------------------
# external_gap_signal
# ----------------------------------------------------------------------------


def test_external_above_independent_is_positive():
    signal = external_gap_signal(10.0, 12.0)
    assert signal.raw_delta == 2.0
    assert "above" in signal.reason


def test_external_below_independent_is_negative():
    signal = external_gap_signal(10.0, 8.0)
    assert signal.raw_delta == -2.0
    assert "below" in signal.reason


def test_missing_either_value_returns_none():
    assert external_gap_signal(None, 10.0) is None
    assert external_gap_signal(10.0, None) is None


def test_zero_gap_returns_none():
    assert external_gap_signal(10.0, 10.0) is None
