import json

import pytest

from fantasydata_audit import client as fd_client
from fantasydata_audit.client import (
    FantasyDataAuthenticationError,
    FantasyDataNotConfiguredError,
    FantasyDataRateLimitedError,
    FantasyDataUnavailableError,
    get_dfs_slates_by_date,
    get_fantasy_game_stats_by_date,
    get_player_game_projection_stats_by_date,
    is_configured,
)

SAMPLE_LIST_RESPONSE = [{"PlayerID": 1, "GameID": 100, "FantasyPointsDraftKings": 12.5}]


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
    # config/env_loader.py auto-loads FANTASYDATA_API_KEY from
    # dashboard/.env.local at import time in a real dev environment --
    # tests must not depend on that ambient state.
    monkeypatch.delenv("FANTASYDATA_API_KEY", raising=False)


# ----------------------------------------------------------------------------
# Configuration / missing key
# ----------------------------------------------------------------------------


def test_is_configured_false_without_key():
    assert is_configured() is False


def test_is_configured_true_with_key(monkeypatch):
    monkeypatch.setenv("FANTASYDATA_API_KEY", "test-key")
    assert is_configured() is True


def test_get_player_game_projection_stats_raises_not_configured_without_key():
    with pytest.raises(FantasyDataNotConfiguredError):
        get_player_game_projection_stats_by_date("2025-JUN-15")


def test_get_fantasy_game_stats_raises_not_configured_without_key():
    with pytest.raises(FantasyDataNotConfiguredError):
        get_fantasy_game_stats_by_date("2025-JUN-15")


def test_get_dfs_slates_raises_not_configured_without_key():
    with pytest.raises(FantasyDataNotConfiguredError):
        get_dfs_slates_by_date("2025-JUN-15")


# ----------------------------------------------------------------------------
# Request shape: Ocp-Apim-Subscription-Key header, never a query param,
# key never in the URL
# ----------------------------------------------------------------------------


def test_uses_subscription_key_header_never_query_string(monkeypatch):
    monkeypatch.setenv("FANTASYDATA_API_KEY", "super-secret-fd-key")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        return FakeResponse(json.dumps(SAMPLE_LIST_RESPONSE).encode("utf-8"))

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)

    get_player_game_projection_stats_by_date("2025-JUN-15")

    assert "super-secret-fd-key" not in captured["url"]
    assert "subscription" not in captured["url"].lower()
    assert captured["headers"].get("Ocp-apim-subscription-key") == "super-secret-fd-key"


def test_fetches_documented_projection_endpoint_path(monkeypatch):
    monkeypatch.setenv("FANTASYDATA_API_KEY", "k")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(json.dumps(SAMPLE_LIST_RESPONSE).encode("utf-8"))

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    get_player_game_projection_stats_by_date("2025-JUN-15")
    assert captured["url"] == "https://api.sportsdata.io/v3/mlb/projections/json/PlayerGameProjectionStatsByDate/2025-JUN-15"


def test_fetches_documented_actual_results_endpoint_path(monkeypatch):
    monkeypatch.setenv("FANTASYDATA_API_KEY", "k")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(json.dumps(SAMPLE_LIST_RESPONSE).encode("utf-8"))

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    get_fantasy_game_stats_by_date("2025-JUN-15")
    assert captured["url"] == "https://api.sportsdata.io/v3/mlb/stats/json/FantasyGameStatsByDate/2025-JUN-15"


def test_fetches_documented_dfs_slates_endpoint_path(monkeypatch):
    monkeypatch.setenv("FANTASYDATA_API_KEY", "k")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(json.dumps(SAMPLE_LIST_RESPONSE).encode("utf-8"))

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    get_dfs_slates_by_date("2025-JUN-15")
    assert captured["url"] == "https://api.sportsdata.io/v3/mlb/projections/json/DfsSlatesByDate/2025-JUN-15"


# ----------------------------------------------------------------------------
# Response parsing
# ----------------------------------------------------------------------------


def test_returns_status_and_parsed_data(monkeypatch):
    monkeypatch.setenv("FANTASYDATA_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        return FakeResponse(json.dumps(SAMPLE_LIST_RESPONSE).encode("utf-8"), status=200)

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    result = get_player_game_projection_stats_by_date("2025-JUN-15")
    assert result["status"] == 200
    assert result["data"] == SAMPLE_LIST_RESPONSE


def test_empty_body_returns_none_data(monkeypatch):
    monkeypatch.setenv("FANTASYDATA_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        return FakeResponse(b"", status=204)

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    result = get_dfs_slates_by_date("2025-JUN-15")
    assert result["status"] == 204
    assert result["data"] is None


# ----------------------------------------------------------------------------
# Error handling
# ----------------------------------------------------------------------------


def test_401_raises_authentication_error(monkeypatch):
    import urllib.error

    monkeypatch.setenv("FANTASYDATA_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyDataAuthenticationError):
        get_player_game_projection_stats_by_date("2025-JUN-15")


def test_403_raises_authentication_error(monkeypatch):
    import urllib.error

    monkeypatch.setenv("FANTASYDATA_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyDataAuthenticationError):
        get_player_game_projection_stats_by_date("2025-JUN-15")


def test_429_raises_rate_limited_error(monkeypatch):
    import urllib.error

    monkeypatch.setenv("FANTASYDATA_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyDataRateLimitedError):
        get_player_game_projection_stats_by_date("2025-JUN-15")


def test_500_raises_unavailable_error(monkeypatch):
    import urllib.error

    monkeypatch.setenv("FANTASYDATA_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 500, "Server Error", {}, None)

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyDataUnavailableError):
        get_player_game_projection_stats_by_date("2025-JUN-15")


def test_url_error_raises_unavailable_error(monkeypatch):
    import urllib.error

    monkeypatch.setenv("FANTASYDATA_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyDataUnavailableError):
        get_player_game_projection_stats_by_date("2025-JUN-15")


def test_malformed_json_raises_unavailable_error(monkeypatch):
    monkeypatch.setenv("FANTASYDATA_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        return FakeResponse(b"not json{{{")

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyDataUnavailableError):
        get_player_game_projection_stats_by_date("2025-JUN-15")


# ----------------------------------------------------------------------------
# Key never leaks into an error message
# ----------------------------------------------------------------------------


def test_api_key_never_appears_in_error_messages(monkeypatch):
    import urllib.error

    monkeypatch.setenv("FANTASYDATA_API_KEY", "super-secret-fd-key-xyz")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(fd_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(FantasyDataAuthenticationError) as excinfo:
        get_player_game_projection_stats_by_date("2025-JUN-15")
    assert "super-secret-fd-key-xyz" not in str(excinfo.value)
