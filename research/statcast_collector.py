"""Collection stage for advanced (Statcast) pitching metrics.

This is a dedicated collector -- separate from research/collector.py --
because it talks to a different host (Baseball Savant, not MLB Stats
API) for a conceptually different tier of data. Per the same rule as
research/collector.py: this is the ONLY module that reaches out to
Baseball Savant. Normalization/parsing of what it returns lives in
research/statcast_enrichment.py, which never touches the network.

Every fetch here uses Baseball Savant's own CSV-exportable leaderboard
and search endpoints (no HTML scraping): season-level data comes from
four small leaderboard endpoints that each return ALL pitchers in a
single request, so a 30-pitcher slate costs 4 requests for season data
-- not 120. The "recent form" window uses the pitch-level search export,
scoped per pitcher to their exact last-3-start dates (from
research.enrichment.RecentStatLine.start_dates) so it never has to guess
a date range or pull more than ~3 games' worth of pitches.
"""

import csv
import io
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from research import cache

BASE_URL = "https://baseballsavant.mlb.com"
REQUEST_TIMEOUT_SECONDS = 20
# Savant returns 403s to requests with no User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (mlb-dfs-engine research bot)"}

_FETCH_ERRORS = (urllib.error.URLError, TimeoutError, ValueError, csv.Error)


@dataclass
class RawStatcastData:
    date: str
    season: str
    # Season-level leaderboards, each covering every pitcher in one payload.
    expected_statistics: List[dict] = field(default_factory=list)   # xba, xwoba, xera
    custom_leaderboard: List[dict] = field(default_factory=list)    # swing/whiff/hard-hit/barrel/exit-velo/GB%
    pitch_arsenals: List[dict] = field(default_factory=list)        # season fastball velocity
    pitch_arsenal_stats: List[dict] = field(default_factory=list)   # season pitch usage / mix
    # Recent (last-3-starts) pitch-level rows, per player.
    recent_pitch_level: Dict[str, List[dict]] = field(default_factory=dict)
    sources_used: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _fetch_csv_rows(url: str) -> List[dict]:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        raw = resp.read()
    text = raw.decode("utf-8-sig")  # Savant CSVs are UTF-8 with a leading BOM
    return list(csv.DictReader(io.StringIO(text)))


def fetch_expected_statistics(season: str) -> List[dict]:
    """League-wide xBA/xwOBA/xERA leaderboard for every pitcher with any
    recorded plate appearances against them this season."""
    url = f"{BASE_URL}/leaderboard/expected_statistics?type=pitcher&year={season}&min=1&csv=true"
    return _fetch_csv_rows(url)


def fetch_custom_leaderboard(season: str) -> List[dict]:
    """League-wide swing%/whiff%/hard-hit%/barrel%/exit-velo/GB% leaderboard.

    `whiff_percent` here is Savant's own definition (misses per SWING, not
    per pitch) -- research.statcast_enrichment derives true swinging-strike%
    (per pitch) as swing_percent * whiff_percent / 100.
    """
    selections = "pa,swing_percent,whiff_percent,groundballs_percent,hard_hit_percent,barrel_batted_rate,exit_velocity_avg"
    url = (
        f"{BASE_URL}/leaderboard/custom?year={season}&type=pitcher&min=1&selections={selections}"
        f"&chart=false&x=pa&y=pa&r=no&chartType=beeswarm&csv=true"
    )
    return _fetch_csv_rows(url)


def fetch_pitch_arsenals(season: str) -> List[dict]:
    """League-wide average velocity per pitch type (e.g. ff_avg_speed,
    si_avg_speed) -- source for season fastball velocity.

    Without `min=1` this leaderboard silently defaults to a much higher
    (roughly "qualified starter") innings threshold and quietly omits
    part-time/rookie/reliever-turned-starter pitchers -- confirmed by
    comparing payload sizes (22.8KB vs 47.8KB for the 2026 season). Same
    `min=1` used on the other three season leaderboards below.
    """
    url = f"{BASE_URL}/leaderboard/pitch-arsenals?year={season}&min=1&csv=true"
    return _fetch_csv_rows(url)


def fetch_pitch_arsenal_stats(season: str) -> List[dict]:
    """One row per pitcher per pitch type thrown, including pitch_usage
    (%) -- source for season pitch mix."""
    url = f"{BASE_URL}/leaderboard/pitch-arsenal-stats?type=pitcher&pitchType=&year={season}&csv=true"
    return _fetch_csv_rows(url)


def fetch_recent_pitch_level(player_id: str, date_gt: str, date_lt: str) -> List[dict]:
    """Every pitch a player threw in (date_gt, date_lt) -- used to compute
    recent CSW%/SwStr%/velocity/hard-hit%/barrel%/GB%/pitch mix from
    Savant's own per-pitch classifications (description, launch_speed,
    launch_speed_angle, bb_type, pitch_type)."""
    url = (
        f"{BASE_URL}/statcast_search/csv?all=true&hfGT=R%7C&hfSea={season_tag(date_lt)}%7C"
        f"&player_type=pitcher&game_date_gt={date_gt}&game_date_lt={date_lt}"
        f"&group_by=name&sort_col=pitches&player_event_sort=api_p_release_speed&sort_order=desc"
        f"&min_pitches=0&min_results=0&type=details&pitchers_lookup%5B%5D={player_id}"
    )
    return _fetch_csv_rows(url)


def season_tag(date_str: str) -> str:
    """Savant's search endpoint wants the season year, not the date, in hfSea."""
    return date_str.split("-")[0]


def _start_date_window(start_dates: List[str]) -> Optional[tuple]:
    """Turn a list of start dates (oldest first) into an inclusive
    (date_gt, date_lt) window one day padded on each side, so boundary
    semantics on Savant's end can't accidentally exclude the games we
    actually want."""
    if not start_dates:
        return None
    oldest = datetime.strptime(start_dates[0], "%Y-%m-%d")
    newest = datetime.strptime(start_dates[-1], "%Y-%m-%d")
    date_gt = (oldest - timedelta(days=1)).strftime("%Y-%m-%d")
    date_lt = (newest + timedelta(days=1)).strftime("%Y-%m-%d")
    return date_gt, date_lt


def collect_statcast_data(
    pitcher_ids: List[str],
    season: str,
    date: str,
    start_dates_by_player: Dict[str, List[str]],
    cache_root: Path = cache.DEFAULT_STATCAST_CACHE_ROOT,
) -> RawStatcastData:
    """Collect season-level (4 requests total, covering every pitcher) and
    per-pitcher recent-window Statcast data. Never raises: a missing
    payload becomes a warning, not a fatal error, so the rest of the
    slate can still be enriched."""
    warnings: List[str] = []
    errors: List[str] = []
    sources: List[str] = []

    season_fetchers = {
        "expected_statistics": fetch_expected_statistics,
        "custom_leaderboard": fetch_custom_leaderboard,
        "pitch_arsenals": fetch_pitch_arsenals,
        "pitch_arsenal_stats": fetch_pitch_arsenal_stats,
    }
    season_results: Dict[str, List[dict]] = {}
    for name, fetch_fn in season_fetchers.items():
        try:
            rows = cache.get_or_fetch(cache_root, date, f"season_{name}_{season}", lambda fn=fetch_fn: fn(season))
        except _FETCH_ERRORS as exc:
            rows = None
            errors.append(f"[statcast_collector] failed to fetch {name} for season {season}: {exc}")
        if rows:
            season_results[name] = rows
            sources.append(f"baseball_savant:{name}")
        else:
            season_results[name] = []
            warnings.append(f"[statcast_collector] no data returned for leaderboard '{name}' (season {season})")

    recent_pitch_level: Dict[str, List[dict]] = {}
    for pid in pitcher_ids:
        window = _start_date_window(start_dates_by_player.get(pid, []))
        if window is None:
            warnings.append(f"[statcast_collector] no known recent start dates for player {pid}; skipping recent Statcast pull")
            continue
        date_gt, date_lt = window
        try:
            rows = cache.get_or_fetch(
                cache_root, date, f"recent_pitch_level_{pid}_{date_gt}_{date_lt}",
                lambda pid=pid, dg=date_gt, dl=date_lt: fetch_recent_pitch_level(pid, dg, dl),
            )
        except _FETCH_ERRORS as exc:
            rows = None
            errors.append(f"[statcast_collector] failed to fetch recent pitch-level data for player {pid}: {exc}")
        if rows:
            recent_pitch_level[pid] = rows
        else:
            warnings.append(f"[statcast_collector] no recent pitch-level data available for player {pid}")

    if pitcher_ids:
        sources.append("baseball_savant:recent_pitch_level")

    return RawStatcastData(
        date=date,
        season=season,
        expected_statistics=season_results.get("expected_statistics", []),
        custom_leaderboard=season_results.get("custom_leaderboard", []),
        pitch_arsenals=season_results.get("pitch_arsenals", []),
        pitch_arsenal_stats=season_results.get("pitch_arsenal_stats", []),
        recent_pitch_level=recent_pitch_level,
        sources_used=sources,
        warnings=warnings,
        errors=errors,
    )
