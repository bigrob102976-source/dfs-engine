import json
import urllib.error

import pytest

from fantasypros import client as fp_client
from fantasypros.client import (
    FantasyProsAuthenticationError,
    FantasyProsNotConfiguredError,
    FantasyProsRateLimitedError,
    FantasyProsUnavailableError,
    get_daily_projections,
    is_configured,
)

SAMPLE_HITTER_RESPONSE = {
    "season": 2026, "date": "2026-08-19", "type": "daily", "position": "H", "count": 388,
    "player": [
        {"fpid": 3365, "player_id": 3365, "yahooid": 8658, "team_id": "LAD", "name": "Freddie Freeman",
         "pa": 4.26, "hits": 1.54, "1b": 1.06, "2b": 0.39, "3b": 0, "runs": 0.61, "hrs": 0.09, "rbi": 0.45,
         "bb": 0.28, "ibb": 0, "hbp": 0.05, "sb": 0.04},
    ],
    "limit": 10, "public_api_limited": True, "tier": "free",
}

SAMPLE_PITCHER_RESPONSE = {
    "season": 2026, "date": "2026-08-19", "type": "daily", "position": "P", "count": 264,
    "player": [
        {"fpid": 3068, "player_id": 3068, "yahooid": 8616, "team_id": "BOS", "name": "Aroldis Chapman",
         "ip": 0.39, "k": 0.49, "er": 0.14, "bbi": 0.18, "h": 0.29, "hp": 0.01, "w": 0.03, "cg": 0, "sho": 0},
    ],
    "limit": 10, "public_api_limited": True, "tier": "free",
}


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


@pytest.fixture(autouse=True)
def _no_ambient_api_key(monkeypatch):
    # config/env_loader.py auto-loads FANTASYPROS_API_KEY from
    # dashboard/.env.local at import time in a real dev environment --
    # tests must not depend on that ambient state.
    monkeypatch.delenv("FANTASYPROS_API_KEY", raising=False)


# ----------------------------------------------------------------------------
# Configuration / missing key
# ----------------------------------------------------------------------------


def test_is_configured_false_without_key():
    assert is_configured() is False


def test_is_configured_true_with_key(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "test-key")
    assert is_configured() is True


def test_get_daily_projections_raises_not_configured_without_key():
    with pytest.raises(FantasyProsNotConfiguredError):
        get_daily_projections("2026-08-19", "H")


# ----------------------------------------------------------------------------
# Request shape: x-api-key header, never a query param, key never in the URL
# ----------------------------------------------------------------------------


def test_uses_x_api_key_header_never_query_string(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "super-secret-fp-key")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        return FakeResponse(json.dumps(SAMPLE_HITTER_RESPONSE).encode("utf-8"))

    monkeypatch.setattr(fp_client.urllib.request, "urlopen", fake_urlopen)

    get_daily_projections("2026-08-19", "H")

    assert "super-secret-fp-key" not in captured["url"]
    assert "apikey" not in captured["url"].lower()
    assert captured["headers"].get("X-api-key") == "super-secret-fp-key"


def test_fetches_documented_endpoint_with_type_date_position(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(json.dumps(SAMPLE_HITTER_RESPONSE).encode("utf-8"))

    monkeypatch.setattr(fp_client.urllib.request, "urlopen", fake_urlopen)
    get_daily_projections("2026-08-19", "H")

    assert "/mlb/2026/projections" in captured["url"]
    assert "type=daily" in captured["url"]
    assert "date=2026-08-19" in captured["url"]
    assert "position=H" in captured["url"]


def test_invalid_position_raises_value_error(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")
    with pytest.raises(ValueError):
        get_daily_projections("2026-08-19", "X")


# ----------------------------------------------------------------------------
# Parsing hitter/pitcher projections + public-api-limited metadata
# ----------------------------------------------------------------------------


def test_parses_hitter_projections(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")
    monkeypatch.setattr(fp_client.urllib.request, "urlopen",
                         lambda request, timeout=None: FakeResponse(json.dumps(SAMPLE_HITTER_RESPONSE).encode("utf-8")))

    result = get_daily_projections("2026-08-19", "H")

    assert len(result.players) == 1
    p = result.players[0]
    assert p.fpid == "3365"
    assert p.name == "Freddie Freeman"
    assert p.team_id == "LAD"
    assert p.player_type == "hitter"
    assert p.yahoo_id == "8658"
    assert p.stats["hrs"] == 0.09
    assert p.stats["1b"] == 1.06
    assert result.count == 388
    assert result.public_api_limited is True
    assert result.tier == "free"


def test_parses_pitcher_projections(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")
    monkeypatch.setattr(fp_client.urllib.request, "urlopen",
                         lambda request, timeout=None: FakeResponse(json.dumps(SAMPLE_PITCHER_RESPONSE).encode("utf-8")))

    result = get_daily_projections("2026-08-19", "P")

    assert len(result.players) == 1
    p = result.players[0]
    assert p.name == "Aroldis Chapman"
    assert p.player_type == "pitcher"
    assert p.stats["ip"] == 0.39
    assert p.stats["bbi"] == 0.18


def test_empty_player_list_returns_empty_result(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")
    empty = {**SAMPLE_HITTER_RESPONSE, "player": [], "count": 0}
    monkeypatch.setattr(fp_client.urllib.request, "urlopen",
                         lambda request, timeout=None: FakeResponse(json.dumps(empty).encode("utf-8")))
    result = get_daily_projections("2026-08-19", "H")
    assert result.players == []
    assert result.count == 0


# ----------------------------------------------------------------------------
# Failure modes: auth, rate limit, unavailable, malformed body
# ----------------------------------------------------------------------------


def test_401_raises_authentication_error(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", None, None)

    monkeypatch.setattr(fp_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyProsAuthenticationError):
        get_daily_projections("2026-08-19", "H")


def test_403_raises_authentication_error(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", None, None)

    monkeypatch.setattr(fp_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyProsAuthenticationError):
        get_daily_projections("2026-08-19", "H")


def test_429_raises_rate_limited_error(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", None, None)

    monkeypatch.setattr(fp_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyProsRateLimitedError):
        get_daily_projections("2026-08-19", "H")


def test_500_raises_unavailable_error(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "Internal Server Error", None, None)

    monkeypatch.setattr(fp_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyProsUnavailableError):
        get_daily_projections("2026-08-19", "H")


def test_malformed_json_raises_unavailable_error(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")
    monkeypatch.setattr(fp_client.urllib.request, "urlopen",
                         lambda request, timeout=None: FakeResponse(b"not json"))
    with pytest.raises(FantasyProsUnavailableError):
        get_daily_projections("2026-08-19", "H")


def test_url_error_raises_unavailable_error(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(fp_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyProsUnavailableError):
        get_daily_projections("2026-08-19", "H")


# ----------------------------------------------------------------------------
# Security: the key never appears in any exception message
# ----------------------------------------------------------------------------


def test_api_key_never_appears_in_error_messages(monkeypatch):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "super-secret-fp-key-xyz")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", None, None)

    monkeypatch.setattr(fp_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyProsAuthenticationError) as exc_info:
        get_daily_projections("2026-08-19", "H")
    assert "super-secret-fp-key-xyz" not in str(exc_info.value)
