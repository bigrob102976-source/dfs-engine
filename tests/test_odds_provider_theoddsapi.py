import json

import pytest

from research.game_environment.providers import theoddsapi as odds_module
from research.game_environment.providers.base import (
    OddsProviderAuthenticationError,
    OddsProviderNotConfiguredError,
    OddsProviderRateLimitedError,
    OddsProviderUnavailableError,
)
from research.game_environment.providers.normalizer import normalize_theoddsapi_event
from research.game_environment.providers.theoddsapi import TheOddsAPIProvider

SAMPLE_EVENT = {
    "id": "evt_1",
    "sport_key": "baseball_mlb",
    "commence_time": "2026-08-17T23:10:00Z",
    "home_team": "Colorado Rockies",
    "away_team": "Los Angeles Dodgers",
    "bookmakers": [
        {
            "key": "draftkings",
            "title": "DraftKings",
            "last_update": "2026-08-17T18:00:00Z",
            "markets": [
                {"key": "h2h", "outcomes": [{"name": "Los Angeles Dodgers", "price": -250}, {"name": "Colorado Rockies", "price": 200}]},
                {"key": "spreads", "outcomes": [{"name": "Los Angeles Dodgers", "price": -110, "point": -1.5}, {"name": "Colorado Rockies", "price": -110, "point": 1.5}]},
                {"key": "totals", "outcomes": [{"name": "Over", "price": -110, "point": 12.5}, {"name": "Under", "price": -110, "point": 12.5}]},
            ],
        }
    ],
}


class FakeResponse:
    def __init__(self, body: bytes, headers=None):
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


def make_provider(tmp_path, api_key="test-key-123"):
    return TheOddsAPIProvider(api_key=api_key, cache_root=tmp_path)


@pytest.fixture(autouse=True)
def _no_ambient_api_key(monkeypatch):
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)


def test_is_configured_true_with_key(tmp_path):
    assert make_provider(tmp_path).is_configured() is True


def test_is_configured_false_without_key(tmp_path):
    assert TheOddsAPIProvider(api_key=None, cache_root=tmp_path).is_configured() is False


def test_get_odds_raises_not_configured_without_key(tmp_path):
    provider = TheOddsAPIProvider(api_key=None, cache_root=tmp_path)
    with pytest.raises(OddsProviderNotConfiguredError):
        provider.get_odds("MLB", "2026-08-17")


def test_provider_name(tmp_path):
    assert make_provider(tmp_path).provider_name() == "The Odds API"


def test_fetches_documented_endpoint_with_minimal_markets(tmp_path, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(json.dumps([]).encode("utf-8"))

    monkeypatch.setattr(odds_module.urllib.request, "urlopen", fake_urlopen)
    make_provider(tmp_path).get_odds("MLB", "2026-08-17")

    assert "/sports/baseball_mlb/odds/" in captured["url"]
    assert "markets=h2h,spreads,totals" in captured["url"]
    assert "regions=us" in captured["url"]
    # Never request player props or extra markets/regions -- credit-metered free tier.
    assert "player" not in captured["url"]


def test_get_odds_returns_normalized_events(tmp_path, monkeypatch):
    monkeypatch.setattr(odds_module.urllib.request, "urlopen", lambda request, timeout=None: FakeResponse(json.dumps([SAMPLE_EVENT]).encode("utf-8")))
    events = make_provider(tmp_path).get_odds("MLB", "2026-08-17")
    assert len(events) == 1
    assert events[0].home_team == "COL"
    assert events[0].away_team == "LAD"
    assert events[0].books[0].total == 12.5


def test_401_raises_authentication_error(tmp_path, monkeypatch):
    import urllib.error

    def raise_401(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(odds_module.urllib.request, "urlopen", raise_401)
    with pytest.raises(OddsProviderAuthenticationError):
        make_provider(tmp_path).get_odds("MLB", "2026-08-17")


def test_429_raises_rate_limited_error(tmp_path, monkeypatch):
    import urllib.error

    def raise_429(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(odds_module.urllib.request, "urlopen", raise_429)
    with pytest.raises(OddsProviderRateLimitedError):
        make_provider(tmp_path).get_odds("MLB", "2026-08-17")


def test_500_raises_unavailable_error(tmp_path, monkeypatch):
    import urllib.error

    def raise_500(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", {}, None)

    monkeypatch.setattr(odds_module.urllib.request, "urlopen", raise_500)
    with pytest.raises(OddsProviderUnavailableError):
        make_provider(tmp_path).get_odds("MLB", "2026-08-17")


def test_key_never_appears_in_any_raised_exception_message(tmp_path, monkeypatch):
    import urllib.error

    def raise_500(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", {}, None)

    monkeypatch.setattr(odds_module.urllib.request, "urlopen", raise_500)
    with pytest.raises(OddsProviderUnavailableError) as excinfo:
        make_provider(tmp_path, api_key="super-secret-key").get_odds("MLB", "2026-08-17")
    assert "super-secret-key" not in str(excinfo.value)


def test_usage_status_populated_from_response_headers(tmp_path, monkeypatch):
    monkeypatch.setattr(
        odds_module.urllib.request,
        "urlopen",
        lambda request, timeout=None: FakeResponse(json.dumps([]).encode("utf-8"), headers={"x-requests-used": "5", "x-requests-remaining": "495"}),
    )
    provider = make_provider(tmp_path)
    provider.get_odds("MLB", "2026-08-17")
    usage = provider.usage_status()
    assert usage.requests_used == 5
    assert usage.requests_limit == 500


def test_second_call_within_same_process_uses_cache(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        return FakeResponse(json.dumps([]).encode("utf-8"))

    monkeypatch.setattr(odds_module.urllib.request, "urlopen", fake_urlopen)
    provider = make_provider(tmp_path)
    provider.get_odds("MLB", "2026-08-17")
    provider.get_odds("MLB", "2026-08-17")
    assert calls["n"] == 1


# ----------------------------------------------------------------------------
# Normalizer
# ----------------------------------------------------------------------------


def test_normalize_full_event():
    normalized = normalize_theoddsapi_event(SAMPLE_EVENT, "2026-08-17T18:30:00Z")
    assert normalized.provider == "theoddsapi"
    assert normalized.home_team == "COL"
    assert normalized.away_team == "LAD"
    book = normalized.books[0]
    assert book.home_moneyline == 200
    assert book.away_moneyline == -250
    assert book.total == 12.5
    assert book.home_run_line == 1.5
    assert book.away_run_line == -1.5


def test_normalize_unrecognized_team_name_returns_none():
    bad_event = {**SAMPLE_EVENT, "home_team": "Not A Real Team"}
    assert normalize_theoddsapi_event(bad_event, "2026-08-17T18:30:00Z") is None


def test_normalize_missing_id_returns_none():
    bad_event = {k: v for k, v in SAMPLE_EVENT.items() if k != "id"}
    assert normalize_theoddsapi_event(bad_event, "2026-08-17T18:30:00Z") is None


def test_normalize_never_sets_event_status():
    normalized = normalize_theoddsapi_event(SAMPLE_EVENT, "2026-08-17T18:30:00Z")
    assert normalized.event_status is None
