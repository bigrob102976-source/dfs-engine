import json
import urllib.error

import research.collector as collector


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_fetch_team_roster_returns_real_response_shape(monkeypatch):
    captured_url = {}

    def fake_urlopen(url, timeout=None):
        captured_url["url"] = url
        return _FakeResponse({"roster": [
            {"person": {"id": 645305, "fullName": "Ali Sanchez"}, "position": {"abbreviation": "C"}, "status": {"code": "A"}},
        ]})

    monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)

    result = collector.fetch_team_roster("147")

    assert result == {"roster": [
        {"person": {"id": 645305, "fullName": "Ali Sanchez"}, "position": {"abbreviation": "C"}, "status": {"code": "A"}},
    ]}
    assert "teams/147/roster" in captured_url["url"]
    assert "rosterType=active" in captured_url["url"]


def test_fetch_team_roster_defaults_to_active_roster_type(monkeypatch):
    captured_url = {}

    def fake_urlopen(url, timeout=None):
        captured_url["url"] = url
        return _FakeResponse({"roster": []})

    monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
    collector.fetch_team_roster("147")
    assert "rosterType=active" in captured_url["url"]


def test_fetch_team_roster_honors_explicit_roster_type(monkeypatch):
    captured_url = {}

    def fake_urlopen(url, timeout=None):
        captured_url["url"] = url
        return _FakeResponse({"roster": []})

    monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
    collector.fetch_team_roster("147", roster_type="40Man")
    assert "rosterType=40Man" in captured_url["url"]


def test_fetch_team_roster_returns_none_on_network_failure(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
    assert collector.fetch_team_roster("147") is None


def test_fetch_team_roster_returns_none_on_malformed_json(monkeypatch):
    class _BadResponse(_FakeResponse):
        def read(self):
            return b"not json"

    def fake_urlopen(url, timeout=None):
        return _BadResponse({})

    monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
    assert collector.fetch_team_roster("147") is None
