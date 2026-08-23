import json
from datetime import datetime, timezone
from io import BytesIO

import pytest

from research.game_environment.providers import open_meteo


def _hourly_response(start="2026-08-23T20:00", hours=8):
    times = []
    base = datetime.fromisoformat(start)
    for i in range(hours):
        times.append((base.replace(hour=(base.hour + i) % 24)).isoformat())
    n = len(times)
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [70.0 + i for i in range(n)],
            "relative_humidity_2m": [50.0] * n,
            "precipitation_probability": [10 * i for i in range(n)],
            "precipitation": [0.1 * i for i in range(n)],
            "weather_code": [0] * n,
            "wind_speed_10m": [8.0] * n,
            "wind_direction_10m": [180.0] * n,
            "wind_gusts_10m": [12.0] * n,
        }
    }


# ---------------------------------------------------------------------------
# Pure helpers -- no network.
# ---------------------------------------------------------------------------


def test_nearest_hour_index_picks_the_closest_hour():
    times = ["2026-08-23T20:00", "2026-08-23T21:00", "2026-08-23T22:00"]
    target = datetime(2026, 8, 23, 20, 50, tzinfo=timezone.utc)
    assert open_meteo.nearest_hour_index(times, target) == 1


def test_nearest_hour_index_returns_none_outside_the_forecast_window():
    times = ["2026-08-23T20:00", "2026-08-23T21:00"]
    target = datetime(2026, 8, 25, 20, 0, tzinfo=timezone.utc)
    assert open_meteo.nearest_hour_index(times, target) is None


def test_nearest_hour_index_empty_times_returns_none():
    assert open_meteo.nearest_hour_index([], datetime.now(timezone.utc)) is None


def test_reading_at_extracts_every_field_by_index():
    hourly = _hourly_response(hours=3)["hourly"]
    reading = open_meteo.reading_at(hourly, 1)
    assert reading["temperature_f"] == 71.0
    assert reading["precipitation_probability"] == 10
    assert reading["weather_code"] == 0
    assert reading["wind_gusts_mph"] == 12.0


def test_reading_at_out_of_range_index_returns_none_fields():
    hourly = _hourly_response(hours=2)["hourly"]
    reading = open_meteo.reading_at(hourly, 99)
    assert reading["temperature_f"] is None


def test_game_window_indices_covers_first_pitch_through_plus_four_hours():
    times = [f"h{i}" for i in range(10)]
    assert open_meteo.game_window_indices(times, first_pitch_index=2, hours_after=4) == [2, 3, 4, 5, 6]


def test_game_window_indices_clamps_to_the_end_of_the_forecast():
    times = [f"h{i}" for i in range(5)]
    assert open_meteo.game_window_indices(times, first_pitch_index=3, hours_after=4) == [3, 4]


# ---------------------------------------------------------------------------
# fetch_forecast -- network mocked, never live.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetch_forecast_builds_the_documented_request_and_caches(tmp_path, monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return _FakeResponse(json.dumps(_hourly_response()).encode("utf-8"))

    monkeypatch.setattr(open_meteo.urllib.request, "urlopen", fake_urlopen)

    doc = open_meteo.fetch_forecast("PHI", "2026-08-23", 39.9061, -75.1665, cache_root=tmp_path)
    assert "hourly" in doc
    assert len(calls) == 1
    url = calls[0]
    assert url.startswith(open_meteo.API_BASE_URL)
    assert "latitude=39.9061" in url
    assert "longitude=-75.1665" in url
    assert "temperature_unit=fahrenheit" in url
    assert "wind_speed_unit=mph" in url
    assert "precipitation_probability" in url
    assert "wind_gusts_10m" in url

    # Second call for the same (team, date) must be served from cache --
    # no second network call.
    open_meteo.fetch_forecast("PHI", "2026-08-23", 39.9061, -75.1665, cache_root=tmp_path)
    assert len(calls) == 1


def test_fetch_forecast_raises_on_malformed_response(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        return _FakeResponse(b"not json")

    monkeypatch.setattr(open_meteo.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(open_meteo.OpenMeteoUnavailableError):
        open_meteo.fetch_forecast("PHI", "2026-08-23", 39.9, -75.1, cache_root=tmp_path)


def test_fetch_forecast_raises_when_hourly_block_is_missing(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        return _FakeResponse(json.dumps({"no_hourly_here": True}).encode("utf-8"))

    monkeypatch.setattr(open_meteo.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(open_meteo.OpenMeteoUnavailableError):
        open_meteo.fetch_forecast("PHI", "2026-08-23", 39.9, -75.1, cache_root=tmp_path)
