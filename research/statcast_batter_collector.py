"""Collection stage for advanced (Statcast) hitting metrics.

A dedicated, separate collector -- mirrors research/statcast_collector.py
(the pitcher version) exactly, including its own small `_fetch_csv_rows`
helper rather than importing the pitcher module's private one, on
purpose: the two stay fully decoupled so nothing done for batters can
ever affect pitcher behavior.

Season-level data (expected stats + custom leaderboard) covers every
hitter in the league in 2 requests total. The "recent form" window uses
the same per-pitch search export as the pitcher collector, scoped to the
hitter's last 14 days, and also doubles as the source for the (optional,
minimal) pitch-type-performance signal.
"""

import csv
import io
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from research import cache

BASE_URL = "https://baseballsavant.mlb.com"
REQUEST_TIMEOUT_SECONDS = 20
_HEADERS = {"User-Agent": "Mozilla/5.0 (mlb-dfs-engine research bot)"}
_FETCH_ERRORS = (urllib.error.URLError, TimeoutError, ValueError, csv.Error)


@dataclass
class RawBatterStatcastData:
    date: str
    season: str
    expected_statistics: List[dict] = field(default_factory=list)  # xba, xslg, xwoba, woba
    custom_leaderboard: List[dict] = field(default_factory=list)   # k%/bb%/hard-hit/barrel/exit-velo/launch-angle/sweet-spot/bat-speed
    recent_pitch_level: Dict[str, List[dict]] = field(default_factory=dict)  # player_id -> pitch rows, last 14 days
    sources_used: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _fetch_csv_rows(url: str) -> List[dict]:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        raw = resp.read()
    text = raw.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(round(pct * (len(sorted_values) - 1))))
    return sorted_values[idx]


def _report_per_player_timings(label: str, elapsed_seconds: List[float]) -> None:
    """MLB BATTER AGENT PERFORMANCE FIX Phase 2: permanent, cheap
    per-player timing -- a local copy (not a cross-import from
    research/collector.py) on purpose, matching this file's own existing
    "stays fully decoupled" design note above for _fetch_csv_rows."""
    if not elapsed_seconds:
        return
    s = sorted(elapsed_seconds)
    print(
        f"[statcast_batter_collector] {label} n={len(s)} total={sum(s):.2f}s "
        f"p50={_percentile(s, 0.50):.3f}s p90={_percentile(s, 0.90):.3f}s "
        f"p99={_percentile(s, 0.99):.3f}s max={s[-1]:.3f}s",
        file=sys.stderr, flush=True,
    )


def fetch_expected_statistics(season: str) -> List[dict]:
    """League-wide xBA/xSLG/xwOBA/wOBA leaderboard for every hitter with
    any recorded plate appearances this season."""
    url = f"{BASE_URL}/leaderboard/expected_statistics?type=batter&year={season}&min=1&csv=true"
    return _fetch_csv_rows(url)


def fetch_custom_leaderboard(season: str) -> List[dict]:
    """League-wide K%/BB%/hard-hit%/barrel%/exit-velo/launch-angle/
    sweet-spot%/GB%/bat-speed leaderboard. `avg_swing_speed` is Savant's
    bat-speed metric; `squared_up_percent`/`max_hit_speed` were tested
    and are NOT reliably exposed by this endpoint for batters, so they
    are not requested here and stay None downstream."""
    selections = (
        "pa,k_percent,bb_percent,hard_hit_percent,barrel_batted_rate,exit_velocity_avg,"
        "launch_angle_avg,sweet_spot_percent,groundballs_percent,avg_swing_speed"
    )
    url = (
        f"{BASE_URL}/leaderboard/custom?year={season}&type=batter&min=1&selections={selections}"
        f"&chart=false&x=pa&y=pa&r=no&chartType=beeswarm&csv=true"
    )
    return _fetch_csv_rows(url)


def fetch_recent_pitch_level(player_id: str, date_gt: str, date_lt: str) -> List[dict]:
    """Every pitch a hitter saw in (date_gt, date_lt) -- used for recent
    exit velocity/hard-hit%/barrel%/xwOBA/pitch-type performance, from
    Savant's own per-pitch classifications."""
    season_tag = date_lt.split("-")[0]
    url = (
        f"{BASE_URL}/statcast_search/csv?all=true&hfGT=R%7C&hfSea={season_tag}%7C"
        f"&player_type=batter&game_date_gt={date_gt}&game_date_lt={date_lt}"
        f"&group_by=name&sort_col=pitches&player_event_sort=api_p_release_speed&sort_order=desc"
        f"&min_pitches=0&min_results=0&type=details&batters_lookup%5B%5D={player_id}"
    )
    return _fetch_csv_rows(url)


def collect_batter_statcast_data(
    batter_ids: List[str],
    season: str,
    date: str,
    reference_date: str,
    window_days: int = 14,
    cache_root: Path = cache.DEFAULT_STATCAST_CACHE_ROOT,
) -> RawBatterStatcastData:
    """Collect season-level (2 requests total, covering every hitter) and
    per-hitter recent-window (last `window_days` days) Statcast data.
    Never raises."""
    warnings: List[str] = []
    errors: List[str] = []
    sources: List[str] = []

    season_fetchers = {
        "expected_statistics": fetch_expected_statistics,
        "custom_leaderboard": fetch_custom_leaderboard,
    }
    season_results: Dict[str, List[dict]] = {}
    for name, fetch_fn in season_fetchers.items():
        try:
            rows = cache.get_or_fetch(cache_root, date, f"batter_season_{name}_{season}", lambda fn=fetch_fn: fn(season))
        except _FETCH_ERRORS as exc:
            rows = None
            errors.append(f"[statcast_batter_collector] failed to fetch {name} for season {season}: {exc}")
        if rows:
            season_results[name] = rows
            sources.append(f"baseball_savant:{name}")
        else:
            season_results[name] = []
            warnings.append(f"[statcast_batter_collector] no data returned for leaderboard '{name}' (season {season})")

    ref = datetime.strptime(reference_date, "%Y-%m-%d")
    date_gt = (ref - timedelta(days=window_days + 1)).strftime("%Y-%m-%d")
    date_lt = ref.strftime("%Y-%m-%d")

    recent_pitch_level: Dict[str, List[dict]] = {}
    per_player_elapsed: List[float] = []
    for pid in batter_ids:
        player_started = time.monotonic()
        try:
            rows = cache.get_or_fetch(
                cache_root, date, f"batter_recent_pitch_level_{pid}_{date_gt}_{date_lt}",
                lambda pid=pid: fetch_recent_pitch_level(pid, date_gt, date_lt),
            )
        except _FETCH_ERRORS as exc:
            rows = None
            errors.append(f"[statcast_batter_collector] failed to fetch recent pitch-level data for player {pid}: {exc}")
        if rows:
            recent_pitch_level[pid] = rows
        else:
            warnings.append(f"[statcast_batter_collector] no recent pitch-level data available for player {pid}")
        per_player_elapsed.append(time.monotonic() - player_started)

    _report_per_player_timings("recent_pitch_level (per-hitter Savant CSV search)", per_player_elapsed)

    if batter_ids:
        sources.append("baseball_savant:recent_pitch_level")

    return RawBatterStatcastData(
        date=date,
        season=season,
        expected_statistics=season_results.get("expected_statistics", []),
        custom_leaderboard=season_results.get("custom_leaderboard", []),
        recent_pitch_level=recent_pitch_level,
        sources_used=sources,
        warnings=warnings,
        errors=errors,
    )
