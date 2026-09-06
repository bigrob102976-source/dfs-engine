"""Simple on-disk JSON cache for external API responses (MLB Stats API,
Baseball Savant/Statcast).

Stat enrichment (season pitching lines, game logs, team hitting lines,
Statcast leaderboards) can mean a hundred-plus HTTP calls for one slate.
This cache keeps a run from re-fetching the exact same payload twice --
within one run, and across reruns for the same slate date.

Deliberately no TTL/eviction/LRU logic: cache entries are namespaced by
slate date, so a new day naturally gets a new cache subfolder and can
never read yesterday's stale numbers. That's the entire staleness story.

Two independent roots are provided (MLB Stats vs. Statcast) so a source
outage or format change on one side can never be masked by, or corrupt,
the other's cache -- callers should always pass the root matching the
API they're calling, never share one across sources.
"""

import json
from pathlib import Path
from typing import Callable, Optional

DEFAULT_CACHE_ROOT = Path(__file__).resolve().parent.parent / "data" / "cache" / "mlb_stats"
DEFAULT_STATCAST_CACHE_ROOT = Path(__file__).resolve().parent.parent / "data" / "cache" / "statcast"
# Postgame box scores for a Final game never change -- safe to cache
# indefinitely, same mechanism as the two pregame roots above.
DEFAULT_RESULTS_CACHE_ROOT = Path(__file__).resolve().parent.parent / "data" / "cache" / "results"


def _path_for(cache_root: Path, date: str, cache_key: str) -> Path:
    return Path(cache_root) / date / f"{cache_key}.json"


def read(cache_root: Path, date: str, cache_key: str) -> Optional[object]:
    """Read-only cache lookup for (date, cache_key) -- None if not
    cached yet. Used by callers that want to check which of several
    keys are already cached BEFORE deciding what (if anything) to fetch
    -- e.g. a bulk/batched fetch that only needs to request whichever
    player IDs aren't already on disk (see research/collector.py's
    batched batter/pitcher stats collection)."""
    path = _path_for(cache_root, date, cache_key)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write(cache_root: Path, date: str, cache_key: str, data: object) -> None:
    """Write-only cache store for (date, cache_key). A None `data` is
    never written (mirrors get_or_fetch's own "never cache a failure"
    rule) so a transient miss doesn't get "stuck" for the rest of the
    day."""
    if data is None:
        return
    path = _path_for(cache_root, date, cache_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f)


def get_or_fetch(
    cache_root: Path,
    date: str,
    cache_key: str,
    fetch_fn: Callable[[], Optional[object]],
) -> Optional[object]:
    """Return cached JSON for (date, cache_key) if present; otherwise call
    fetch_fn(), cache a successful (non-None) result, and return it.

    A None result (fetch failed or had nothing to return) is never
    cached, so a transient failure doesn't get "stuck" for the rest of
    the day -- the next call simply tries again.
    """
    cached = read(cache_root, date, cache_key)
    if cached is not None:
        return cached

    data = fetch_fn()
    write(cache_root, date, cache_key, data)
    return data
