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
    path = Path(cache_root) / date / f"{cache_key}.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    data = fetch_fn()
    if data is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f)
    return data
