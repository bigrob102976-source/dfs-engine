"""Baseball Savant / Statcast adapter.

Milestone 32.0 audit finding: Baseball Savant's pitch-level Statcast
search exposes a public, unauthenticated CSV export endpoint
(baseballsavant.mlb.com/statcast_search/csv). Live-tested for
2025-06-15: 4,294 pitch-level rows, 119 columns, ~2.96MB, ~1-2s response
time, no API key required. Confirmed fields include batter/pitcher
MLBAM IDs, stand/p_throws (handedness), launch_speed, launch_angle,
estimated_woba_using_speedangle (Statcast's pitch-level xwOBA
contribution), woba_value, and full pitch-type/velocity/spin detail.

`pybaseball.statcast()` was also live-tested and returns byte-identical
row/column counts for the same date range -- it is confirmed to be a
thin pandas convenience wrapper around this SAME public CSV endpoint
(see M32.0's final report Part C). This module calls the endpoint
directly rather than depending on pybaseball, so historical_mlb has no
new hard dependency pending a decision on whether to add pybaseball to
requirements.txt in a future milestone.

Statcast is pitch-level, not game-level -- xwOBA/barrel%/hard-hit% etc.
per player per game must be AGGREGATED from these rows (one row per
pitch). This module fetches; historical_mlb/rolling.py aggregates.
"""

import csv
import io
import urllib.parse
from typing import List, Optional

from historical_mlb.cache import RawCache
from historical_mlb.http import fetch_url
from historical_mlb.paths import RAW_STATCAST_DIR

STATCAST_SEARCH_URL = "https://baseballsavant.mlb.com/statcast_search/csv"

_cache = RawCache(RAW_STATCAST_DIR)

# Fixed search parameters that make the query "all regular-season pitches
# for the given date range, both player types" -- the same defaults
# pybaseball.statcast() itself sends. `player_type` is intentionally
# "batter": Statcast's own search returns full at-bat detail (both the
# batter's AND the pitcher's ids) either way; requesting "batter" avoids
# a documented Savant quirk where "pitcher" mode omits a few batted-ball
# fields for the batter side.
_FIXED_PARAMS = {
    "all": "true", "hfGT": "R|", "player_type": "batter", "hfSA": "",
    "group_by": "name", "sort_col": "pitches", "player_event_sort": "api_p_release_speed",
    "sort_order": "desc", "min_pas": "0", "min_pitches": "0", "min_results": "0", "type": "details",
}


def _build_url(start_date: str, end_date: str) -> str:
    params = dict(_FIXED_PARAMS)
    params["game_date_gt"] = start_date
    params["game_date_lt"] = end_date
    return f"{STATCAST_SEARCH_URL}?{urllib.parse.urlencode(params)}"


def fetch_statcast_csv_text(start_date: str, end_date: Optional[str] = None, timeout: int = 60) -> str:
    """One live network call (via the shared retry/backoff/pacing
    helper -- Part 6). Returns the raw CSV text (UTF-8, may carry a
    BOM)."""
    end_date = end_date or start_date
    raw = fetch_url(_build_url(start_date, end_date), timeout=timeout)
    return raw.decode("utf-8-sig", errors="replace")


def fetch_cached_statcast_csv_text(date: str, force: bool = False) -> str:
    """Milestone 32.1, Part 4: one cached fetch per DATE (Statcast is
    queried single-day at a time for the warehouse build, one row per
    pitch that day across every game) -- never re-downloaded on a
    resumed/rerun build unless --force."""
    key = f"statcast_{date}"
    return _cache.get_or_fetch_text(
        key, "csv", fetch_fn=lambda: fetch_statcast_csv_text(date, date),
        build_meta_fn=lambda text: {"source": "baseball_savant", "date": date, "record_count": max(text.count("\n") - 1, 0)},
        force=force,
    )


def parse_statcast_csv(csv_text: str) -> List[dict]:
    """Pure parsing, no network -- this is what unit tests exercise
    against a small saved fixture. Returns one dict per pitch, keys
    exactly as Baseball Savant names its own columns (never renamed
    here, so a schema audit can diff against Savant's own docs)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    return list(reader)


# Statcast columns this package's rolling-feature aggregation (Part 7)
# actually reads -- documented explicitly so a future Savant column
# rename is caught by a KeyError at aggregation time, not silently
# ignored. Every other one of the 119 columns is preserved verbatim in
# the parsed rows but not specially interpreted here.
RELEVANT_COLUMNS = [
    "game_date", "game_pk", "batter", "pitcher", "player_name", "stand", "p_throws",
    "events", "description", "launch_speed", "launch_angle",
    "estimated_woba_using_speedangle", "woba_value", "woba_denom",
    "pitch_type", "release_speed", "release_spin_rate",
]
