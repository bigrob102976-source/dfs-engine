from datetime import datetime, timezone

import pytest

from research.game_environment.weather import OpenMeteoWeatherProvider, WeatherProviderUnavailableError


def _hourly(start_hour_utc: datetime, hours: int, **overrides):
    times = []
    for i in range(hours):
        t = start_hour_utc.replace(tzinfo=None)
        t = t.replace(hour=(t.hour + i) % 24)
        times.append(t.isoformat())
    n = len(times)
    base = {
        "time": times,
        "temperature_2m": [75.0] * n,
        "relative_humidity_2m": [50.0] * n,
        "precipitation_probability": [0] * n,
        "precipitation": [0.0] * n,
        "weather_code": [0] * n,
        "wind_speed_10m": [8.0] * n,
        "wind_direction_10m": [180.0] * n,
        "wind_gusts_10m": [10.0] * n,
    }
    base.update(overrides)
    return {"hourly": base}


@pytest.fixture
def stub_fetch(monkeypatch):
    """Stubs research.game_environment.weather's imported `fetch_forecast`
    reference directly -- never touches urllib, so this is guaranteed
    network-free regardless of caching behavior."""
    calls = []

    def _install(doc):
        def fake_fetch(home_team_abbr, forecast_date, lat, lon, cache_root=None):
            calls.append((home_team_abbr, forecast_date, lat, lon))
            return doc
        monkeypatch.setattr("research.game_environment.weather.fetch_forecast", fake_fetch)
        return calls

    return _install


def test_is_configured_always_true_keyless():
    assert OpenMeteoWeatherProvider().is_configured() is True


def test_provider_name_is_open_meteo():
    assert OpenMeteoWeatherProvider().provider_name() == "Open-Meteo"


def test_never_labeled_mock():
    provider = OpenMeteoWeatherProvider()
    assert provider.is_mock is False


def test_confirmed_closed_dome_never_fetches_and_reports_zero_risk(stub_fetch):
    calls = stub_fetch({"hourly": {}})
    provider = OpenMeteoWeatherProvider()
    snapshot = provider.get_weather("g1", "TEX", "2026-08-23T23:00:00Z", "dome")

    assert calls == []  # no network call for a confirmed closed dome
    assert snapshot.is_mock is False
    assert snapshot.weather_risk_percent == 0.0
    assert snapshot.delay_risk_percent == 0.0
    assert snapshot.current.wind_speed_mph == 0.0


def test_retractable_roof_still_fetches_real_forecast_never_guesses_closed(stub_fetch):
    start = datetime(2026, 8, 23, 22, 0, tzinfo=timezone.utc)
    doc = _hourly(start, 8)
    calls = stub_fetch(doc)
    provider = OpenMeteoWeatherProvider()
    provider.get_weather("g1", "TOR", "2026-08-23T22:00:00Z", "retractable")

    assert len(calls) == 1  # a real fetch happened -- "retractable" was never treated as closed


def test_open_air_game_selects_the_first_pitch_hour(stub_fetch):
    start = datetime(2026, 8, 23, 20, 0, tzinfo=timezone.utc)
    doc = _hourly(start, 8, temperature_2m=[60.0 + i for i in range(8)])
    stub_fetch(doc)
    provider = OpenMeteoWeatherProvider()
    snapshot = provider.get_weather("g1", "PHI", "2026-08-23T23:00:00Z", "open")

    assert snapshot.first_pitch.temperature_f == 63.0  # hour index 3 (20:00 + 3h = 23:00)
    assert snapshot.mid_game.temperature_f == 65.0  # +2h from first pitch
    assert snapshot.late_game.temperature_f == 67.0  # +4h from first pitch


def test_raises_a_clear_error_when_forecast_window_doesnt_cover_the_start_time(stub_fetch):
    start = datetime(2026, 8, 23, 20, 0, tzinfo=timezone.utc)
    doc = _hourly(start, 3)  # only 3 hours -- doesn't reach a start time 10 hours later
    stub_fetch(doc)
    provider = OpenMeteoWeatherProvider()
    with pytest.raises(WeatherProviderUnavailableError):
        provider.get_weather("g1", "PHI", "2026-08-24T06:00:00Z", "open")


def test_raises_a_clear_error_for_an_unknown_team():
    provider = OpenMeteoWeatherProvider()
    with pytest.raises(WeatherProviderUnavailableError):
        provider.get_weather("g1", "ZZZ", "2026-08-23T23:00:00Z", "open")


def test_raises_a_clear_error_when_no_scheduled_start_time(stub_fetch):
    stub_fetch(_hourly(datetime(2026, 8, 23, 20, 0, tzinfo=timezone.utc), 8))
    provider = OpenMeteoWeatherProvider()
    with pytest.raises(WeatherProviderUnavailableError):
        provider.get_weather("g1", "PHI", None, "open")


def test_snapshot_carries_the_new_forecast_fields(stub_fetch):
    start = datetime(2026, 8, 23, 23, 0, tzinfo=timezone.utc)
    doc = _hourly(
        start, 8,
        precipitation_probability=[40, 40, 40, 40, 40, 40, 40, 40],
        precipitation=[0.5] * 8,
        weather_code=[61] * 8,
        wind_gusts_10m=[18.0] * 8,
    )
    stub_fetch(doc)
    provider = OpenMeteoWeatherProvider()
    snapshot = provider.get_weather("g1", "PHI", "2026-08-23T23:00:00Z", "open")

    assert snapshot.first_pitch.precipitation_probability_percent == 40
    assert snapshot.first_pitch.precipitation_amount_mm == 0.5
    assert snapshot.first_pitch.weather_code == 61
    assert snapshot.first_pitch.wind_gusts_mph == 18.0
    assert snapshot.weather_risk_percent is not None
    assert snapshot.weather_status is not None
    assert snapshot.postponement_risk_percent is None  # no fabricated independent signal
    assert snapshot.delay_risk_percent == snapshot.weather_risk_percent


def test_provider_is_registered_as_the_automatic_default(monkeypatch):
    from research.game_environment import collector
    monkeypatch.delenv("GAME_ENVIRONMENT_PROVIDER", raising=False)
    provider, source = collector.get_configured_weather_provider()
    assert isinstance(provider, OpenMeteoWeatherProvider)
    assert source == "automatic_default"
