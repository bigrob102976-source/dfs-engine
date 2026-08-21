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
import urllib.request
from typing import List, Optional

STATCAST_SEARCH_URL = "https://baseballsavant.mlb.com/statcast_search/csv"

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
    """One live network call. Returns the raw CSV text (UTF-8, may carry
    a BOM). Never raises for an HTTP-level failure without context --
    lets urllib's own HTTPError/URLError propagate with the real cause,
    since (unlike the DK unofficial provider) this is research-only
    code with no production caller expecting a specific exception type."""
    end_date = end_date or start_date
    req = urllib.request.Request(_build_url(start_date, end_date), headers={"User-Agent": "BigMoneyDFS-Research/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8-sig", errors="replace")


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
