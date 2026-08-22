"""Milestone 32.1, Part 6 -- http.py retry/backoff. No real network
calls -- urllib.request.urlopen is monkeypatched to simulate
failures."""

import urllib.error

import pytest

from historical_mlb.http import FetchError, fetch_url


def test_fetch_url_success_first_try(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"ok"

    monkeypatch.setattr("historical_mlb.http.urllib.request.urlopen", lambda req, timeout: FakeResp())
    monkeypatch.setattr("historical_mlb.http.time.sleep", lambda s: None)
    result = fetch_url("http://example.test", max_retries=2)
    assert result == b"ok"


def test_fetch_url_retries_on_500_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(req, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, None)
        return FakeResp()

    monkeypatch.setattr("historical_mlb.http.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("historical_mlb.http.time.sleep", lambda s: None)
    result = fetch_url("http://example.test", max_retries=3, backoff_base=0.01)
    assert result == b"ok"
    assert calls["n"] == 3


def test_fetch_url_non_retryable_400_raises_immediately(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr("historical_mlb.http.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("historical_mlb.http.time.sleep", lambda s: None)
    with pytest.raises(FetchError):
        fetch_url("http://example.test", max_retries=3)
    assert calls["n"] == 1  # no retries for a non-retryable client error


def test_fetch_url_exhausts_retries_and_raises(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 503, "Unavailable", {}, None)

    monkeypatch.setattr("historical_mlb.http.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("historical_mlb.http.time.sleep", lambda s: None)
    with pytest.raises(FetchError):
        fetch_url("http://example.test", max_retries=2, backoff_base=0.01)


def test_fetch_url_respects_retry_after_header(monkeypatch):
    sleeps = []
    calls = {"n": 0}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(req, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {"Retry-After": "7"}, None)
        return FakeResp()

    monkeypatch.setattr("historical_mlb.http.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("historical_mlb.http.time.sleep", lambda s: sleeps.append(s))
    fetch_url("http://example.test", max_retries=2)
    assert 7 in sleeps  # honored the server's explicit Retry-After value
