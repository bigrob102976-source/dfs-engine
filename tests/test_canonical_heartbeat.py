"""M3K -- optional success heartbeat hook tests."""

import urllib.request

import pytest

from canonical_ingestion import heartbeat


def test_no_request_when_url_not_configured(monkeypatch):
    monkeypatch.delenv(heartbeat.HEARTBEAT_URL_ENV_VAR, raising=False)
    called = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: called.append(1))
    result = heartbeat.send_success_heartbeat()
    assert result is False
    assert called == []  # absolutely no external request attempted


def test_no_request_when_url_is_blank(monkeypatch):
    monkeypatch.setenv(heartbeat.HEARTBEAT_URL_ENV_VAR, "   ")
    called = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: called.append(1))
    assert heartbeat.send_success_heartbeat() is False
    assert called == []


def test_pings_the_configured_url(monkeypatch):
    monkeypatch.setenv(heartbeat.HEARTBEAT_URL_ENV_VAR, "https://example.com/ping/abc123")
    captured = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = heartbeat.send_success_heartbeat()
    assert result is True
    assert captured["url"] == "https://example.com/ping/abc123"
    assert captured["timeout"] == heartbeat.HEARTBEAT_TIMEOUT_SECONDS


def test_detail_appended_as_query_param(monkeypatch):
    monkeypatch.setenv(heartbeat.HEARTBEAT_URL_ENV_VAR, "https://example.com/ping/abc123")
    captured = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    heartbeat.send_success_heartbeat(detail="146757: 840 players")
    assert "detail=146757%3A%20840%20players" in captured["url"]


def test_network_failure_never_raises(monkeypatch):
    monkeypatch.setenv(heartbeat.HEARTBEAT_URL_ENV_VAR, "https://example.com/ping/abc123")

    def raise_error(request, timeout=None):
        raise OSError("network unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", raise_error)
    result = heartbeat.send_success_heartbeat()
    assert result is True  # a ping WAS attempted -- the failure is swallowed, not hidden as "never attempted"


def test_no_credential_required_no_hardcoded_url():
    # Structural proof: this module never constructs a URL string
    # itself (only reads one from the environment) and defines no
    # credential/API-key/token constant anywhere.
    import inspect

    source = inspect.getsource(heartbeat)
    assert "https://" not in source and "http://" not in source
    assert "api_key" not in source.lower()
    assert "token" not in source.lower()
