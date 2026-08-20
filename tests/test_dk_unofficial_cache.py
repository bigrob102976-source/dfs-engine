import time

from draftkings_unofficial.cache import DkUnofficialCache, get_default_cache, reset_default_cache


def test_get_or_fetch_calls_fetch_once_within_ttl():
    calls = []

    def fetch():
        calls.append(1)
        return {"n": len(calls)}

    cache = DkUnofficialCache(ttls={"sports": 100})
    r1 = cache.get_or_fetch("sports", "all", fetch)
    r2 = cache.get_or_fetch("sports", "all", fetch)
    assert r1 == r2
    assert len(calls) == 1


def test_get_or_fetch_refetches_after_ttl_expires():
    calls = []

    def fetch():
        calls.append(1)
        return len(calls)

    cache = DkUnofficialCache(ttls={"sports": 0})
    cache.get_or_fetch("sports", "all", fetch)
    time.sleep(0.01)
    cache.get_or_fetch("sports", "all", fetch)
    assert len(calls) == 2


def test_different_keys_are_cached_independently():
    calls = []

    def fetch():
        calls.append(1)
        return len(calls)

    cache = DkUnofficialCache()
    cache.get_or_fetch("contests", "MLB", fetch)
    cache.get_or_fetch("contests", "NFL", fetch)
    assert len(calls) == 2


def test_different_categories_are_cached_independently():
    calls = []

    def fetch():
        calls.append(1)
        return len(calls)

    cache = DkUnofficialCache()
    cache.get_or_fetch("sports", "x", fetch)
    cache.get_or_fetch("contests", "x", fetch)
    assert len(calls) == 2


def test_invalidate_all():
    calls = []

    def fetch():
        calls.append(1)
        return len(calls)

    cache = DkUnofficialCache()
    cache.get_or_fetch("sports", "all", fetch)
    cache.invalidate()
    cache.get_or_fetch("sports", "all", fetch)
    assert len(calls) == 2


def test_invalidate_one_category_leaves_others_intact():
    cache = DkUnofficialCache()
    cache.get_or_fetch("sports", "all", lambda: 1)
    cache.get_or_fetch("contests", "MLB", lambda: 2)
    cache.invalidate("sports")
    assert cache.size() == 1


def test_default_cache_singleton_and_reset():
    reset_default_cache()
    c1 = get_default_cache()
    c2 = get_default_cache()
    assert c1 is c2
    reset_default_cache()
    c3 = get_default_cache()
    assert c3 is not c1
