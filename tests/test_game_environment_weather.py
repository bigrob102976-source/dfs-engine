import pytest

from research.game_environment.ballpark import get_ballpark_profile
from research.game_environment.models import WeatherReading, WeatherSnapshot
from research.game_environment.weather import (
    MockWeatherProvider,
    WeatherProvider,
    analyze_weather,
)


def test_base_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        WeatherProvider()


def test_mock_provider_implements_interface():
    assert isinstance(MockWeatherProvider(), WeatherProvider)


def test_mock_provider_is_always_configured():
    assert MockWeatherProvider().is_configured() is True


def test_mock_provider_name_is_clearly_labeled():
    assert MockWeatherProvider().provider_name() == "MOCK WEATHER"


def test_mock_weather_is_deterministic_not_random():
    provider = MockWeatherProvider()
    first = provider.get_weather("g1", "COL", "2026-08-13T23:00:00Z", "open")
    second = provider.get_weather("g1", "COL", "2026-08-13T23:00:00Z", "open")
    assert first.current.temperature_f == second.current.temperature_f
    assert first.current.wind_speed_mph == second.current.wind_speed_mph


def test_mock_weather_differs_by_game_id():
    provider = MockWeatherProvider()
    a = provider.get_weather("g1", "COL", None, "open")
    b = provider.get_weather("g2", "COL", None, "open")
    assert a.current.temperature_f != b.current.temperature_f or a.current.wind_speed_mph != b.current.wind_speed_mph


def test_mock_weather_provides_all_four_display_points():
    provider = MockWeatherProvider()
    snapshot = provider.get_weather("g1", "COL", None, "open")
    assert snapshot.current.temperature_f is not None
    assert snapshot.first_pitch.temperature_f is not None
    assert snapshot.mid_game.temperature_f is not None
    assert snapshot.late_game.temperature_f is not None


def test_dome_roof_produces_stable_indoor_conditions():
    provider = MockWeatherProvider()
    snapshot = provider.get_weather("g1", "TEX", None, "dome")
    assert snapshot.roof_status == "dome"
    assert snapshot.current.wind_speed_mph == 0.0
    assert snapshot.current.rain_percent == 0.0
    assert snapshot.delay_risk_percent == 0.0
    assert snapshot.postponement_risk_percent == 0.0


def test_open_roof_produces_variable_conditions():
    provider = MockWeatherProvider()
    snapshot = provider.get_weather("g1", "COL", None, "open")
    assert snapshot.roof_status == "open"


def test_provenance_fields_present():
    provider = MockWeatherProvider()
    snapshot = provider.get_weather("g1", "COL", None, "open")
    assert snapshot.provider_name == "MOCK WEATHER"
    assert snapshot.is_mock is True
    assert snapshot.retrieved_at


# ----------------------------------------------------------------------------
# analyze_weather
# ----------------------------------------------------------------------------


def _snapshot(**overrides) -> WeatherSnapshot:
    base = dict(
        game_id="g1", provider_name="MOCK WEATHER", is_mock=True, retrieved_at="2026-08-13T18:00:00Z",
        roof_status="open", delay_risk_percent=5.0, postponement_risk_percent=2.0,
        current=WeatherReading(temperature_f=70.0, humidity_percent=50.0, wind_speed_mph=5.0, wind_direction_degrees=0.0, feels_like_f=70.0, rain_percent=5.0),
    )
    base.update(overrides)
    return WeatherSnapshot(**base)


def test_indoor_game_produces_a_single_neutral_conclusion():
    snapshot = _snapshot(roof_status="dome")
    analysis = analyze_weather(snapshot, None)
    assert len(analysis.conclusions) == 1
    assert analysis.conclusions[0].code == "indoor_game"
    assert analysis.conclusions[0].favors == "neutral"


def test_strong_wind_blowing_out_favors_hitter():
    park = get_ballpark_profile("CLE")  # orientation_degrees = 0
    snapshot = _snapshot(current=WeatherReading(temperature_f=70.0, wind_speed_mph=15.0, wind_direction_degrees=0.0))
    analysis = analyze_weather(snapshot, park)
    codes = [c.code for c in analysis.conclusions]
    assert "wind_strong_out" in codes
    conclusion = next(c for c in analysis.conclusions if c.code == "wind_strong_out")
    assert conclusion.favors == "hitter"
    assert "blowing out" in conclusion.text.lower()


def test_strong_wind_blowing_in_favors_pitcher():
    park = get_ballpark_profile("CLE")  # orientation_degrees = 0
    snapshot = _snapshot(current=WeatherReading(temperature_f=70.0, wind_speed_mph=15.0, wind_direction_degrees=180.0))
    analysis = analyze_weather(snapshot, park)
    conclusion = next(c for c in analysis.conclusions if c.code == "wind_strong_in")
    assert conclusion.favors == "pitcher"
    assert "blowing in" in conclusion.text.lower()


def test_strong_crosswind_is_neutral():
    park = get_ballpark_profile("CLE")  # orientation_degrees = 0
    snapshot = _snapshot(current=WeatherReading(temperature_f=70.0, wind_speed_mph=15.0, wind_direction_degrees=90.0))
    analysis = analyze_weather(snapshot, park)
    conclusion = next(c for c in analysis.conclusions if c.code == "wind_strong_cross")
    assert conclusion.favors == "neutral"


def test_mild_wind_below_notable_threshold_produces_no_wind_conclusion():
    park = get_ballpark_profile("CLE")
    snapshot = _snapshot(current=WeatherReading(temperature_f=70.0, wind_speed_mph=2.0, wind_direction_degrees=0.0))
    analysis = analyze_weather(snapshot, park)
    assert all("wind" not in c.code for c in analysis.conclusions)


def test_hot_weather_favors_offense():
    snapshot = _snapshot(current=WeatherReading(temperature_f=90.0, wind_speed_mph=0.0))
    analysis = analyze_weather(snapshot, None)
    conclusion = next(c for c in analysis.conclusions if c.code == "hot_weather")
    assert conclusion.favors == "hitter"
    assert conclusion.text == "Hot weather favors offense."


def test_cold_weather_suppresses_offense():
    snapshot = _snapshot(current=WeatherReading(temperature_f=40.0, wind_speed_mph=0.0))
    analysis = analyze_weather(snapshot, None)
    conclusion = next(c for c in analysis.conclusions if c.code == "cold_weather")
    assert conclusion.favors == "pitcher"
    assert conclusion.text == "Cold weather suppresses offense."


def test_high_rain_delay_risk_flagged():
    snapshot = _snapshot(delay_risk_percent=60.0)
    analysis = analyze_weather(snapshot, None)
    conclusion = next(c for c in analysis.conclusions if c.code == "rain_delay_risk")
    assert conclusion.favors == "risk"


def test_high_postponement_risk_flagged():
    snapshot = _snapshot(postponement_risk_percent=30.0)
    analysis = analyze_weather(snapshot, None)
    conclusion = next(c for c in analysis.conclusions if c.code == "postponement_risk")
    assert conclusion.favors == "risk"


def test_missing_wind_direction_never_crashes_and_produces_no_wind_conclusion():
    snapshot = _snapshot(current=WeatherReading(temperature_f=70.0, wind_speed_mph=15.0, wind_direction_degrees=None))
    analysis = analyze_weather(snapshot, get_ballpark_profile("CLE"))
    assert all("wind" not in c.code for c in analysis.conclusions)


def test_missing_ballpark_never_crashes_and_produces_no_wind_conclusion():
    snapshot = _snapshot(current=WeatherReading(temperature_f=70.0, wind_speed_mph=15.0, wind_direction_degrees=0.0))
    analysis = analyze_weather(snapshot, None)
    assert all("wind" not in c.code for c in analysis.conclusions)
