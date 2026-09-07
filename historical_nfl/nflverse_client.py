"""NFL M6A Phase 1/6 -- thin wrapper around nflreadpy, the nflverse
project's current, maintained Python client (nfl_data_py is deprecated
in its favor -- confirmed live during the NFL M6 audit).

Every function here requires an explicit `season: int` -- there is no
code path that can accidentally trigger a full-history download.
nflreadpy's own loaders take `seasons: int | list[int] | bool | None`
(True/None can mean "all available seasons"); this module never passes
that through, by construction.

Confirmed live (M6A Phase 1, small real read against nflreadpy 0.1.5):
schedules/rosters are natively season-grain (one network fetch covers
every week of that season); weekly_player_stats/team_stats/play_by_play
are ALSO fetched from nflverse as one season-level file each -- nflreadpy
exposes no server-side week filter for any of them. "Bounded by week"
in this module therefore means: fetch the season file (nflreadpy caches
that download itself locally), then filter deterministically in-memory
to the requested week before returning -- never a real per-week network
request, because nflverse's own release format doesn't offer one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import polars as pl

import nflreadpy

NFLREADPY_VERSION = getattr(nflreadpy, "__version__", "unknown")


class NflverseUnavailableError(Exception):
    """nflverse/nflreadpy was reachable-or-not, but the requested data
    could not be retrieved (network failure, unexpected empty/malformed
    response). Never raised for "no rows for this filter" -- that is a
    legitimate empty result, not an error."""


def _provenance(fn_name: str, **kwargs) -> str:
    args = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
    return f"nflreadpy=={NFLREADPY_VERSION} {fn_name}({args})"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch(fn_name: str, season: int) -> tuple:
    """Calls nflreadpy.<fn_name>(seasons=season). Returns (dataframe,
    fetched_at, source_provenance). Raises NflverseUnavailableError on
    any failure -- never returns a partial/guessed result."""
    fetched_at = _now_iso()
    try:
        loader = getattr(nflreadpy, fn_name)
        df = loader(seasons=season)
    except Exception as exc:  # noqa: BLE001 -- nflreadpy's own failure modes (network, parsing) are not enumerated publicly
        raise NflverseUnavailableError(f"nflreadpy.{fn_name}(seasons={season}) failed: {exc}") from exc
    if df is None:
        raise NflverseUnavailableError(f"nflreadpy.{fn_name}(seasons={season}) returned no data.")
    return df, fetched_at, _provenance(fn_name, seasons=season)


def fetch_schedules(season: int) -> tuple:
    """Returns (polars.DataFrame, fetched_at, source_provenance) -- every
    game nflverse has for `season` (regular season + postseason, exactly
    as the source labels game_type)."""
    return _fetch("load_schedules", season)


def fetch_rosters(season: int, week: Optional[int] = None) -> tuple:
    """Uses nflreadpy's load_rosters_weekly(), NOT load_rosters() --
    confirmed live during M6A Phase 1 that load_rosters()'s own `week`
    column does not mean "who was on this roster in this week" (its
    gsis_id values had ZERO overlap with the same week's real
    load_player_stats() player_id values); load_rosters_weekly() is the
    dataset that actually reconciles with weekly stats (confirmed: every
    real week-1 2025 weekly-stat player_id was present in that week's
    load_rosters_weekly() gsis_id set). Same season-file-then-filter
    behavior as the other week-grain fetchers."""
    df, fetched_at, provenance = _fetch("load_rosters_weekly", season)
    if week is not None:
        df = df.filter(pl.col("week") == week)
        provenance = f"{provenance} filtered week={week}"
    return df, fetched_at, provenance


def fetch_weekly_player_stats(season: int, week: Optional[int] = None) -> tuple:
    """Fetches the season's weekly player stats, then filters to `week`
    in-memory if given (see module docstring -- no server-side week
    filter exists). `week=None` returns the whole season."""
    df, fetched_at, provenance = _fetch("load_player_stats", season)
    if week is not None:
        df = df.filter(pl.col("week") == week)
        provenance = f"{provenance} filtered week={week}"
    return df, fetched_at, provenance


def fetch_team_stats(season: int, week: Optional[int] = None) -> tuple:
    df, fetched_at, provenance = _fetch("load_team_stats", season)
    if week is not None:
        df = df.filter(pl.col("week") == week)
        provenance = f"{provenance} filtered week={week}"
    return df, fetched_at, provenance


def fetch_play_by_play(season: int, week: Optional[int] = None) -> tuple:
    df, fetched_at, provenance = _fetch("load_pbp", season)
    if week is not None:
        df = df.filter(pl.col("week") == week)
        provenance = f"{provenance} filtered week={week}"
    return df, fetched_at, provenance


def fetch_snap_counts(season: int, week: Optional[int] = None) -> tuple:
    """NFL M6C -- real, PFR-sourced offense/defense/special-teams snap
    counts. No gsis_id column (uses PFR's own pfr_player_id) -- see
    historical_nfl/usage_identity_bridge.py for the real GSIS bridge."""
    df, fetched_at, provenance = _fetch("load_snap_counts", season)
    if week is not None:
        df = df.filter(pl.col("week") == week)
        provenance = f"{provenance} filtered week={week}"
    return df, fetched_at, provenance


def fetch_participation(season: int, week: Optional[int] = None) -> tuple:
    """NFL M6C -- real, play-level participation charting (2016-2025;
    confirmed live -- nflreadpy itself rejects seasons outside that
    range). GSIS-keyed via `offense_players`/`defense_players`
    (semicolon-delimited GSIS ID strings, confirmed live) -- but see
    historical_nfl/usage_normalize.py's module docstring for why this
    module's per-play `route` field does not decompose into a
    trustworthy per-player route-participation count.

    Real Phase-1 finding: load_participation()'s real schema has NO
    `season`/`week` columns at all -- only `nflverse_game_id` (the exact
    same "{season}_{week}_{away}_{home}" format schedules/pbp already
    use, confirmed live). `season`/`week` are derived here by parsing
    that real, structural ID string -- never by re-fetching or guessing
    -- so this fetcher's return shape matches every other week-grain
    fetcher's (a real `week` column to filter and later persist by)."""
    df, fetched_at, provenance = _fetch("load_participation", season)
    df = df.with_columns([
        pl.col("nflverse_game_id").str.split("_").list.get(0).cast(pl.Int64).alias("season"),
        pl.col("nflverse_game_id").str.split("_").list.get(1).cast(pl.Int64).alias("week"),
    ])
    if week is not None:
        df = df.filter(pl.col("week") == week)
        provenance = f"{provenance} filtered week={week}"
    return df, fetched_at, provenance


def fetch_ff_playerids() -> tuple:
    """NFL M6C -- the DynastyProcess-maintained fantasy-ID crosswalk
    (gsis_id/pfr_id/espn_id/... one row per real person). Not
    season-scoped at the source -- nflreadpy's own load_ff_playerids()
    takes no season argument."""
    fetched_at = _now_iso()
    try:
        df = nflreadpy.load_ff_playerids()
    except Exception as exc:  # noqa: BLE001 -- see _fetch's identical comment
        raise NflverseUnavailableError(f"nflreadpy.load_ff_playerids() failed: {exc}") from exc
    if df is None:
        raise NflverseUnavailableError("nflreadpy.load_ff_playerids() returned no data.")
    return df, fetched_at, _provenance("load_ff_playerids")
