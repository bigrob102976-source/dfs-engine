import json
import urllib.error

import pytest

from draftkings_unofficial import client as dk_client
from draftkings_unofficial.client import (
    DraftKingsUnofficialAccessRestrictedError,
    DraftKingsUnofficialNotFoundError,
    DraftKingsUnofficialRateLimitedError,
    DraftKingsUnofficialUnavailableError,
    get_contests,
    get_contest_details,
    get_draftables,
    get_game_type_rules,
    get_sports,
)


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


def _ok(payload, monkeypatch):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(json.dumps(payload).encode("utf-8"))
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)


# ----------------------------------------------------------------------------
# Endpoint URL shape -- no auth needed (no API key at all)
# ----------------------------------------------------------------------------


def test_get_sports_hits_documented_url(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(json.dumps({"sports": []}).encode("utf-8"))

    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    get_sports()
    assert captured["url"] == "https://api.draftkings.com/sites/US-DK/sports/v1/sports?format=json"


def test_get_contests_hits_documented_url_with_sport(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(json.dumps({"Contests": []}).encode("utf-8"))

    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    get_contests("MLB")
    assert captured["url"] == "https://www.draftkings.com/lobby/getcontests?sport=MLB"


def test_get_draftables_hits_documented_url_with_draft_group_id(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(json.dumps({"draftables": []}).encode("utf-8"))

    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    get_draftables(152389)
    assert captured["url"] == "https://api.draftkings.com/draftgroups/v1/draftgroups/152389/draftables"


def test_get_game_type_rules_hits_documented_url(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(json.dumps({"gameTypeId": 2}).encode("utf-8"))

    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    get_game_type_rules(2)
    assert captured["url"] == "https://api.draftkings.com/lineups/v1/gametypes/2/rules"


def test_get_contest_details_hits_documented_url(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse(json.dumps({"contestDetail": {}}).encode("utf-8"))

    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    get_contest_details(190035665)
    assert captured["url"] == "https://api.draftkings.com/contests/v1/contests/190035665?format=json"


def test_uses_a_user_agent_header(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = dict(request.headers)
        return FakeResponse(json.dumps({"sports": []}).encode("utf-8"))

    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    get_sports()
    assert "User-agent" in captured["headers"]


# ----------------------------------------------------------------------------
# Error handling: 400/401/403/404/429/5xx/timeout/DNS/invalid JSON/empty/HTML
# ----------------------------------------------------------------------------


def test_404_raises_not_found(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialNotFoundError):
        get_draftables(1)


def test_401_raises_access_restricted(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialAccessRestrictedError):
        get_sports()


def test_403_raises_access_restricted(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialAccessRestrictedError):
        get_sports()


def test_429_raises_rate_limited(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialRateLimitedError):
        get_sports()


def test_400_raises_unavailable(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 400, "Bad Request", {}, None)
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialUnavailableError):
        get_sports()


def test_500_raises_unavailable(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 500, "Server Error", {}, None)
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialUnavailableError):
        get_sports()


def test_503_raises_unavailable(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None)
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialUnavailableError):
        get_sports()


def test_timeout_raises_unavailable(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise TimeoutError("timed out")
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialUnavailableError):
        get_sports()


def test_dns_error_raises_unavailable(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("Name or service not known")
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialUnavailableError):
        get_sports()


def test_invalid_json_raises_unavailable(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(b"not json{{{")
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialUnavailableError):
        get_sports()


def test_empty_response_raises_unavailable(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(b"")
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialUnavailableError):
        get_sports()


def test_html_response_raises_access_restricted(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(b"<!DOCTYPE html><html><body>Please log in</body></html>")
    monkeypatch.setattr(dk_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(DraftKingsUnofficialAccessRestrictedError):
        get_sports()


def test_get_contest_details_returns_parsed_payload(monkeypatch):
    _ok({"contestDetail": {"contestSummary": "hi"}}, monkeypatch)
    result = get_contest_details(1)
    assert result == {"contestDetail": {"contestSummary": "hi"}}
