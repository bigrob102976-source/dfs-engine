"""Milestone 32.1 -- historical_mlb/cache.py. No network calls."""

import json

from historical_mlb.cache import RawCache, atomic_write_text


def test_atomic_write_text_creates_file(tmp_path):
    path = tmp_path / "sub" / "file.json"
    atomic_write_text(path, '{"a": 1}')
    assert path.exists()
    assert json.loads(path.read_text()) == {"a": 1}
    assert not path.with_suffix(path.suffix + ".tmp").exists()  # tmp file cleaned up (renamed away)


def test_raw_cache_has_false_when_nothing_cached(tmp_path):
    cache = RawCache(tmp_path)
    assert cache.has("key1", "json") is False


def test_raw_cache_write_and_read_roundtrip(tmp_path):
    cache = RawCache(tmp_path)
    cache.write_text("key1", "json", '{"x": 1}', {"source": "test", "record_count": 1})
    assert cache.has("key1", "json") is True
    assert cache.read_text("key1", "json") == '{"x": 1}'
    meta = cache.read_meta("key1")
    assert meta["source"] == "test"
    assert meta["record_count"] == 1


def test_raw_cache_get_or_fetch_text_uses_cache_on_second_call(tmp_path):
    cache = RawCache(tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return "fetched-data"

    first = cache.get_or_fetch_text("k", "csv", fetch_fn=fetch, build_meta_fn=lambda t: {"len": len(t)})
    second = cache.get_or_fetch_text("k", "csv", fetch_fn=fetch, build_meta_fn=lambda t: {"len": len(t)})
    assert first == second == "fetched-data"
    assert len(calls) == 1  # NOT re-fetched on the second call


def test_raw_cache_get_or_fetch_text_force_redownloads(tmp_path):
    cache = RawCache(tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return f"fetch-{len(calls)}"

    cache.get_or_fetch_text("k", "csv", fetch_fn=fetch, build_meta_fn=lambda t: {})
    result = cache.get_or_fetch_text("k", "csv", fetch_fn=fetch, build_meta_fn=lambda t: {}, force=True)
    assert len(calls) == 2
    assert result == "fetch-2"


def test_raw_cache_payload_without_meta_is_not_considered_cached(tmp_path):
    cache = RawCache(tmp_path)
    # Simulates a killed process that wrote the payload but never reached the metadata write.
    (tmp_path / "k.json").write_text("partial")
    assert cache.has("k", "json") is False


def test_get_or_fetch_json_uses_cache_on_second_call(tmp_path):
    cache = RawCache(tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return {"x": 1}

    first = cache.get_or_fetch_json("k", fetch_fn=fetch, meta={"source": "test"})
    second = cache.get_or_fetch_json("k", fetch_fn=fetch, meta={"source": "test"})
    assert first == second == {"x": 1}
    assert len(calls) == 1


def test_get_or_fetch_json_self_heals_a_corrupted_cache_entry(tmp_path):
    """Regression guard for a real defect caught live during Milestone
    32.1's full warehouse build: a cached weather payload file existed
    (both has() checks passed) but its content was corrupted/blank
    (not valid JSON) -- almost certainly left by an abrupt process kill
    during an earlier interrupted run. A JSONDecodeError on read must
    be treated as a cache miss (silent re-fetch + repair), never an
    unhandled crash that aborts the whole date's collection."""
    cache = RawCache(tmp_path)
    # Simulate exactly the corrupted state found live: both files exist
    # (has() is True) but the payload is not valid JSON.
    (tmp_path / "k.json").write_text("                    ")
    (tmp_path / "k.meta.json").write_text('{"source": "test"}')
    assert cache.has("k", "json") is True  # both files present -- looks cached

    calls = []

    def fetch():
        calls.append(1)
        return {"repaired": True}

    result = cache.get_or_fetch_json("k", fetch_fn=fetch, meta={"source": "test"})
    assert result == {"repaired": True}
    assert len(calls) == 1  # refetched despite has() being True, because the content was corrupt
    # The corrupted entry is now actually repaired on disk for next time.
    assert json.loads((tmp_path / "k.json").read_text()) == {"repaired": True}


def test_get_or_fetch_json_force_redownloads(tmp_path):
    cache = RawCache(tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return {"n": len(calls)}

    cache.get_or_fetch_json("k", fetch_fn=fetch, meta={})
    result = cache.get_or_fetch_json("k", fetch_fn=fetch, meta={}, force=True)
    assert len(calls) == 2
    assert result == {"n": 2}


def test_get_or_fetch_json_caches_none_result(tmp_path):
    """A genuine 'no data' result (e.g. an unknown team, or a provider
    with nothing for this date) must be cached too -- json.dumps(None)
    is valid JSON ("null"), so a second call should NOT re-fetch."""
    cache = RawCache(tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return None

    first = cache.get_or_fetch_json("k", fetch_fn=fetch, meta={})
    second = cache.get_or_fetch_json("k", fetch_fn=fetch, meta={})
    assert first is None
    assert second is None
    assert len(calls) == 1
