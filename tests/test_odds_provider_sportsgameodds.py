import json
import urllib.error

import pytest

from research.game_environment.providers import sportsgameodds as sgo_module
from research.game_environment.providers.base import (
    OddsProviderAuthenticationError,
    OddsProviderNotConfiguredError,
    OddsProviderRateLimitedError,
    OddsProviderUnavailableError,
)
from research.game_environment.providers.sportsgameodds import SportsGameOddsProvider

SAMPLE_EVENT = {
    "eventID": "evt_1",
    "leagueID": "MLB",
    "teams": {
        "home": {"teamID": "LAD", "names": {"short": "LAD"}},
        "away": {"teamID": "SD", "names": {"short": "SD"}},
    },
    "status": {"startsAt": "2026-08-17T23:10:00Z"},
    "odds": {
        "points-home-game-ml-home": {"sideID": "home", "byBookmaker": {"draftkings": {"odds": "-165"}}},
        "points-away-game-ml-away": {"sideID": "away", "byBookmaker": {"draftkings": {"odds": "140"}}},
    },
}


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


def make_provider(tmp_path, api_key="test-key-123"):
    return SportsGameOddsProvider(api_key=api_key, cache_root=tmp_path)


@pytest.fixture(autouse=True)
def _no_ambient_api_key(monkeypatch):
    # Milestone 24's config/env_loader.py auto-loads SPORTSGAMEODDS_API_KEY
    # from dashboard/.env.local at import time in a real dev environment,
    # so "without key" tests must not rely on the ambient environment
    # actually being unconfigured -- explicitly clear it here instead.
    monkeypatch.delenv("SPORTSGAMEODDS_API_KEY", raising=False)


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------


def test_is_configured_true_with_key(tmp_path):
    assert make_provider(tmp_path).is_configured() is True


def test_is_configured_false_without_key(tmp_path):
    assert SportsGameOddsProvider(api_key=None, cache_root=tmp_path).is_configured() is False


def test_get_odds_raises_not_configured_without_key(tmp_path):
    provider = SportsGameOddsProvider(api_key=None, cache_root=tmp_path)
    with pytest.raises(OddsProviderNotConfiguredError):
        provider.get_odds("MLB", "2026-08-17")


def test_provider_name_and_is_mock(tmp_path):
    provider = make_provider(tmp_path)
    assert provider.provider_name() == "SportsGameOdds"
    assert provider.is_mock is False


# ----------------------------------------------------------------------------
# Request shape: header auth, no key in URL, documented endpoint/filters
# ----------------------------------------------------------------------------


def test_uses_x_api_key_header_not_query_string(tmp_path, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        return FakeResponse(json.dumps({"data": []}).encode("utf-8"))

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)

    provider = make_provider(tmp_path, api_key="super-secret-key")
    provider.get_odds("MLB", "2026-08-17")

    assert "apiKey=" not in captured["url"]
    assert "super-secret-key" not in captured["url"]
    assert captured["headers"].get("X-api-key") == "super-secret-key"


def test_fetches_documented_endpoint_and_filters(tmp_path, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(json.dumps({"data": []}).encode("utf-8"))

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)

    provider = make_provider(tmp_path)
    provider.get_odds("MLB", "2026-08-17")

    assert captured["url"].startswith("https://api.sportsgameodds.com/v2/events")
    assert "leagueID=MLB" in captured["url"]
    assert "oddsAvailable=true" in captured["url"]


# ----------------------------------------------------------------------------
# Successful parsing
# ----------------------------------------------------------------------------


def test_get_odds_returns_normalized_events(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(json.dumps({"data": [SAMPLE_EVENT]}).encode("utf-8"))

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)

    provider = make_provider(tmp_path)
    results = provider.get_odds("MLB", "2026-08-17")

    assert len(results) == 1
    assert results[0].event_id == "evt_1"
    assert results[0].home_team == "LAD"


# ----------------------------------------------------------------------------
# Pagination
# ----------------------------------------------------------------------------


def test_follows_pagination_cursor_until_exhausted(tmp_path, monkeypatch):
    call_count = {"n": 0}

    def fake_urlopen(request, timeout=None):
        call_count["n"] += 1
        if "cursor=" not in request.full_url:
            return FakeResponse(json.dumps({"data": [SAMPLE_EVENT], "nextCursor": "page2"}).encode("utf-8"))
        return FakeResponse(json.dumps({"data": [{**SAMPLE_EVENT, "eventID": "evt_2"}]}).encode("utf-8"))

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)

    provider = make_provider(tmp_path)
    results = provider.get_odds("MLB", "2026-08-17")

    assert call_count["n"] == 2
    assert {r.event_id for r in results} == {"evt_1", "evt_2"}


def test_pagination_stops_at_max_pages_ceiling(tmp_path, monkeypatch):
    call_count = {"n": 0}

    def fake_urlopen(request, timeout=None):
        call_count["n"] += 1
        return FakeResponse(json.dumps({"data": [], "nextCursor": "always-more"}).encode("utf-8"))

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)

    provider = make_provider(tmp_path)
    provider.get_odds("MLB", "2026-08-17")

    assert call_count["n"] == sgo_module.MAX_PAGES


# ----------------------------------------------------------------------------
# Failure handling
# ----------------------------------------------------------------------------


def test_401_raises_authentication_error(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OddsProviderAuthenticationError):
        make_provider(tmp_path).get_odds("MLB", "2026-08-17")


def test_403_raises_authentication_error(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OddsProviderAuthenticationError):
        make_provider(tmp_path).get_odds("MLB", "2026-08-17")


def test_429_raises_rate_limited_error(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OddsProviderRateLimitedError):
        make_provider(tmp_path).get_odds("MLB", "2026-08-17")


def test_500_raises_unavailable_error(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", {}, None)

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OddsProviderUnavailableError):
        make_provider(tmp_path).get_odds("MLB", "2026-08-17")


def test_timeout_raises_unavailable_error(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OddsProviderUnavailableError):
        make_provider(tmp_path).get_odds("MLB", "2026-08-17")


def test_connection_error_raises_unavailable_error(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OddsProviderUnavailableError):
        make_provider(tmp_path).get_odds("MLB", "2026-08-17")


def test_malformed_json_raises_unavailable_error(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(b"not json{{{")

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OddsProviderUnavailableError):
        make_provider(tmp_path).get_odds("MLB", "2026-08-17")


def test_unsupported_league_raises_unavailable_error(tmp_path):
    provider = make_provider(tmp_path)
    with pytest.raises(OddsProviderUnavailableError):
        provider.get_odds("NFL", "2026-08-17")


def test_no_mlb_games_returns_empty_list_not_an_error(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(json.dumps({"data": []}).encode("utf-8"))

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)
    results = make_provider(tmp_path).get_odds("MLB", "2026-08-17")
    assert results == []


# ----------------------------------------------------------------------------
# Caching
# ----------------------------------------------------------------------------


def test_second_call_within_same_process_uses_cache_not_a_second_network_call(tmp_path, monkeypatch):
    call_count = {"n": 0}

    def fake_urlopen(request, timeout=None):
        call_count["n"] += 1
        return FakeResponse(json.dumps({"data": [SAMPLE_EVENT]}).encode("utf-8"))

    monkeypatch.setattr(sgo_module.urllib.request, "urlopen", fake_urlopen)

    provider = make_provider(tmp_path)
    provider.get_odds("MLB", "2026-08-17")
    provider.get_odds("MLB", "2026-08-17")

    assert call_count["n"] == 1


def test_usage_status_returns_none_without_a_documented_endpoint(tmp_path):
    assert make_provider(tmp_path).usage_status() is None
