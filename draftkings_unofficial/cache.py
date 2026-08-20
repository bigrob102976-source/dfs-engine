"""Milestone 31.2 -- conservative, in-process, per-category cache for
the unofficial DraftKings provider. Avoids repeat live calls for data
that doesn't change quickly (sports, rules) or that a single
collection run would otherwise re-fetch multiple times (draftables for
a draft group referenced by many contests).

This is a simple in-memory TTL cache, not a distributed one -- this
provider is development-only (see DK_UNOFFICIAL_ENABLED), so a
per-process cache is sufficient; the durable, cross-run cache is
persistence.py's immutable snapshot archive, which this module doesn't
replace.

Each category gets its OWN TTL, since some data is far more volatile
than others (contests/draftables during a live slate vs. rules, which
essentially never change intra-day).
"""

import time
from typing import Any, Callable, Dict, Optional, Tuple

# Named, documented TTLs (seconds) -- not scattered magic numbers.
DEFAULT_TTLS = {
    "sports": 3600,       # sport list changes rarely
    "contests": 60,       # entries/contest lists change quickly while live
    "draftgroups": 60,
    "draftables": 30,     # status/salary can change close to lock
    "rules": 3600,        # roster/salary-cap rules are effectively static intra-day
}


class DkUnofficialCache:
    def __init__(self, ttls: Optional[Dict[str, int]] = None):
        self._ttls = {**DEFAULT_TTLS, **(ttls or {})}
        self._store: Dict[Tuple[str, str], Tuple[float, Any]] = {}

    def get_or_fetch(self, category: str, key: str, fetch: Callable[[], Any]) -> Any:
        cache_key = (category, key)
        ttl = self._ttls.get(category, 60)
        now = time.monotonic()
        cached = self._store.get(cache_key)
        if cached is not None:
            fetched_at, value = cached
            if now - fetched_at < ttl:
                return value
        value = fetch()
        self._store[cache_key] = (now, value)
        return value

    def invalidate(self, category: Optional[str] = None, key: Optional[str] = None) -> None:
        if category is None:
            self._store.clear()
            return
        self._store = {k: v for k, v in self._store.items() if not (k[0] == category and (key is None or k[1] == key))}

    def size(self) -> int:
        return len(self._store)


_default_cache: Optional[DkUnofficialCache] = None


def get_default_cache() -> DkUnofficialCache:
    global _default_cache
    if _default_cache is None:
        _default_cache = DkUnofficialCache()
    return _default_cache


def reset_default_cache() -> None:
    global _default_cache
    _default_cache = None
