"""Collection stage: the only module in the Research Engine that talks to
the network.

Uses the free, public MLB Stats API (no API key required). Normalization,
validation, and scoring never call the network directly — they only ever
see the raw JSON this module hands them, or the typed models the
normalizer builds from it.

Network failures here are recorded as warnings/errors on `RawSlateData`
rather than raised, so one flaky call (e.g. enriching a single pitcher's
throwing hand) doesn't take down the whole pipeline. A failure to fetch
the schedule itself — the one piece everything else depends on — is
recorded as an error and the pipeline continues with an empty schedule
rather than crashing silently or fabricating games.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from research import cache

MLB_STATS_BASE = "https://statsapi.mlb.com/api/v1"
REQUEST_TIMEOUT_SECONDS = 10

# Exceptions a single flaky network/parsing call can raise; caught at
# every call site here so one bad response never takes down the pipeline.
_FETCH_ERRORS = (urllib.error.URLError, TimeoutError, ValueError)


@dataclass
class RawSlateData:
    date: str
    schedule: dict
    people: Dict[str, dict]
    sources_used: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class RawPitcherStats:
    """Raw (un-normalized) statistics payloads for one slate's probable
    pitchers and their opponents. Everything here is exactly what MLB
    Stats API returned -- research.enrichment is what turns it into
    typed, provenance-tagged numbers."""

    date: str
    season: str
    season_pitching: Dict[str, dict] = field(default_factory=dict)   # player_id -> raw payload
    game_log_pitching: Dict[str, dict] = field(default_factory=dict)  # player_id -> raw payload
    team_hitting: Dict[str, dict] = field(default_factory=dict)       # team_id -> raw payload
    sources_used: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_schedule(date: str) -> dict:
    """Fetch one day's MLB schedule, hydrated with team/venue/probable
    pitcher/lineup info in a single call."""
    url = (
        f"{MLB_STATS_BASE}/schedule"
        f"?sportId=1&date={date}&hydrate=team,probablePitcher,venue,lineups"
    )
    return _get_json(url)


def fetch_person(player_id: str) -> Optional[dict]:
    """Fetch bio info (throws/bats/etc.) for a single player. Returns None
    on any failure rather than raising — this is enrichment, not critical
    path."""
    url = f"{MLB_STATS_BASE}/people/{player_id}"
    try:
        data = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    people = data.get("people") or []
    return people[0] if people else None


def fetch_team_roster(team_id: str, roster_type: str = "active") -> Optional[dict]:
    """Fetch one team's roster (default: the 25/26-man active roster).
    Live-verified real response shape: {"roster": [{"person": {"id",
    "fullName"}, "position": {"abbreviation"}, "status": {"code"}, ...}]}.
    Used by player_identity/ to build MLB player identity independent of
    today's starting-lineup confirmation (see that package's module
    docstring). Returns None on any failure rather than raising -- a
    single team's roster fetch failing must never take down a refresh
    that covers many teams."""
    url = f"{MLB_STATS_BASE}/teams/{team_id}/roster?rosterType={roster_type}"
    try:
        return _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def _extract_probable_pitcher_ids(schedule: dict) -> List[str]:
    ids = []
    for date_block in schedule.get("dates", []):
        for game in date_block.get("games", []):
            teams = game.get("teams", {})
            for side in ("home", "away"):
                pitcher = teams.get(side, {}).get("probablePitcher")
                if pitcher and pitcher.get("id"):
                    ids.append(str(pitcher["id"]))
    # de-duplicate while preserving order
    seen = set()
    unique_ids = []
    for pid in ids:
        if pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)
    return unique_ids


def collect(date: str) -> RawSlateData:
    """Collect stage: gather raw data for one slate date. Never raises —
    problems are recorded on the returned object so the pipeline can
    still produce a (possibly partial) research package and report them
    loudly rather than dying silently."""
    warnings: List[str] = []
    errors: List[str] = []
    sources: List[str] = []

    schedule: dict = {}
    try:
        schedule = fetch_schedule(date)
        sources.append("mlb_stats_api:schedule")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        errors.append(f"[collector] failed to fetch schedule for {date}: {exc}")

    people: Dict[str, dict] = {}
    pitcher_ids = _extract_probable_pitcher_ids(schedule)
    for pid in pitcher_ids:
        person = fetch_person(pid)
        if person:
            people[pid] = person
        else:
            warnings.append(f"[collector] could not fetch bio info for player {pid}")
    if pitcher_ids:
        sources.append("mlb_stats_api:people")

    return RawSlateData(
        date=date,
        schedule=schedule,
        people=people,
        sources_used=sources,
        warnings=warnings,
        errors=errors,
    )


def fetch_pitcher_season_stats(player_id: str, season: str) -> Optional[dict]:
    """Season-to-date pitching totals for one player (battersFaced,
    strikeOuts, baseOnBalls, earnedRuns, hits, homeRuns, outs, era, ...).
    Returns None on any failure -- callers treat that exactly like "no
    stats available yet" rather than crashing the pipeline."""
    url = f"{MLB_STATS_BASE}/people/{player_id}/stats?stats=season&group=pitching&season={season}"
    try:
        return _get_json(url)
    except _FETCH_ERRORS:
        return None


def fetch_pitcher_game_log(player_id: str, season: str) -> Optional[dict]:
    """Game-by-game pitching log for one player, chronological (oldest
    first) -- the last entries are the player's most recent starts."""
    url = f"{MLB_STATS_BASE}/people/{player_id}/stats?stats=gameLog&group=pitching&season={season}"
    try:
        return _get_json(url)
    except _FETCH_ERRORS:
        return None


def fetch_team_hitting_stats(team_id: str, season: str) -> Optional[dict]:
    """Season-to-date team hitting totals, used for the team's overall
    (not handedness-specific) strikeout rate."""
    url = f"{MLB_STATS_BASE}/teams/{team_id}/stats?stats=season&group=hitting&season={season}"
    try:
        return _get_json(url)
    except _FETCH_ERRORS:
        return None


def collect_pitcher_stats(
    pitcher_ids: List[str],
    opponent_team_ids: List[str],
    season: str,
    date: str,
    cache_root: Path = cache.DEFAULT_CACHE_ROOT,
) -> RawPitcherStats:
    """Collect raw season/recent pitching stats for each pitcher and raw
    season hitting stats for each opponent team, going through the
    on-disk cache so the same player/team/season is never fetched twice
    in one run (or across reruns for the same slate date).

    Never raises: a missing payload for one player/team becomes a
    warning, not a fatal error, since the rest of the slate can still be
    scored (with lower confidence for that pitcher)."""
    warnings: List[str] = []
    errors: List[str] = []
    sources: List[str] = []

    season_pitching: Dict[str, dict] = {}
    game_log_pitching: Dict[str, dict] = {}
    for pid in pitcher_ids:
        data = cache.get_or_fetch(
            cache_root, date, f"season_pitching_{pid}_{season}",
            lambda pid=pid: fetch_pitcher_season_stats(pid, season),
        )
        if data:
            season_pitching[pid] = data
        else:
            warnings.append(f"[collector] no season pitching stats available for player {pid}")

        data = cache.get_or_fetch(
            cache_root, date, f"gamelog_pitching_{pid}_{season}",
            lambda pid=pid: fetch_pitcher_game_log(pid, season),
        )
        if data:
            game_log_pitching[pid] = data
        else:
            warnings.append(f"[collector] no game log available for player {pid}")

    if pitcher_ids:
        sources.append("mlb_stats_api:pitching_season_stats")
        sources.append("mlb_stats_api:pitching_game_log")

    team_hitting: Dict[str, dict] = {}
    for tid in sorted(set(opponent_team_ids)):
        data = cache.get_or_fetch(
            cache_root, date, f"team_hitting_{tid}_{season}",
            lambda tid=tid: fetch_team_hitting_stats(tid, season),
        )
        if data:
            team_hitting[tid] = data
        else:
            warnings.append(f"[collector] no team hitting stats available for team {tid}")

    if opponent_team_ids:
        sources.append("mlb_stats_api:team_hitting_stats")

    return RawPitcherStats(
        date=date,
        season=season,
        season_pitching=season_pitching,
        game_log_pitching=game_log_pitching,
        team_hitting=team_hitting,
        sources_used=sources,
        warnings=warnings,
        errors=errors,
    )


# ----------------------------------------------------------------------------
# Batter stats (Milestone 7) -- same host, same _get_json helper, same
# never-raises philosophy as the pitcher functions above.
# ----------------------------------------------------------------------------


@dataclass
class RawBatterStats:
    """Raw (un-normalized) hitting payloads for one slate's starting
    lineup hitters. research.batter_enrichment turns this into typed,
    provenance-tagged numbers."""

    date: str
    season: str
    season_hitting: Dict[str, dict] = field(default_factory=dict)          # player_id -> raw payload
    game_log_hitting: Dict[str, dict] = field(default_factory=dict)        # player_id -> raw payload
    platoon_vs_rhp: Dict[str, dict] = field(default_factory=dict)          # player_id -> raw payload
    platoon_vs_lhp: Dict[str, dict] = field(default_factory=dict)          # player_id -> raw payload
    sources_used: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def fetch_batter_season_stats(player_id: str, season: str) -> Optional[dict]:
    """Season-to-date hitting totals for one player (plateAppearances,
    hits, doubles, triples, homeRuns, baseOnBalls, strikeOuts, avg, obp,
    slg, ops, stolenBases, ...)."""
    url = f"{MLB_STATS_BASE}/people/{player_id}/stats?stats=season&group=hitting&season={season}"
    try:
        return _get_json(url)
    except _FETCH_ERRORS:
        return None


def fetch_batter_game_log(player_id: str, season: str) -> Optional[dict]:
    """Game-by-game hitting log, chronological (oldest first) -- used to
    build the last-14-days recent-form window."""
    url = f"{MLB_STATS_BASE}/people/{player_id}/stats?stats=gameLog&group=hitting&season={season}"
    try:
        return _get_json(url)
    except _FETCH_ERRORS:
        return None


def fetch_batter_platoon_split(player_id: str, season: str, sit_code: str) -> Optional[dict]:
    """True handedness split: sit_code 'vr' = vs RHP, 'vl' = vs LHP."""
    url = f"{MLB_STATS_BASE}/people/{player_id}/stats?stats=statSplits&group=hitting&season={season}&sitCodes={sit_code}"
    try:
        return _get_json(url)
    except _FETCH_ERRORS:
        return None


def collect_batter_stats(
    batter_ids: List[str],
    season: str,
    date: str,
    cache_root: Path = cache.DEFAULT_CACHE_ROOT,
) -> RawBatterStats:
    """Collect raw season/recent/platoon hitting stats for each starting
    lineup hitter, going through the same on-disk cache the pitcher
    collector uses. Never raises -- a missing payload for one player
    becomes a warning, not a fatal error."""
    warnings: List[str] = []
    errors: List[str] = []
    sources: List[str] = []

    season_hitting: Dict[str, dict] = {}
    game_log_hitting: Dict[str, dict] = {}
    platoon_vs_rhp: Dict[str, dict] = {}
    platoon_vs_lhp: Dict[str, dict] = {}

    for pid in batter_ids:
        data = cache.get_or_fetch(
            cache_root, date, f"season_hitting_{pid}_{season}",
            lambda pid=pid: fetch_batter_season_stats(pid, season),
        )
        if data:
            season_hitting[pid] = data
        else:
            warnings.append(f"[collector] no season hitting stats available for player {pid}")

        data = cache.get_or_fetch(
            cache_root, date, f"gamelog_hitting_{pid}_{season}",
            lambda pid=pid: fetch_batter_game_log(pid, season),
        )
        if data:
            game_log_hitting[pid] = data
        else:
            warnings.append(f"[collector] no hitting game log available for player {pid}")

        data = cache.get_or_fetch(
            cache_root, date, f"platoon_vr_{pid}_{season}",
            lambda pid=pid: fetch_batter_platoon_split(pid, season, "vr"),
        )
        if data:
            platoon_vs_rhp[pid] = data
        else:
            warnings.append(f"[collector] no vs-RHP split available for player {pid}")

        data = cache.get_or_fetch(
            cache_root, date, f"platoon_vl_{pid}_{season}",
            lambda pid=pid: fetch_batter_platoon_split(pid, season, "vl"),
        )
        if data:
            platoon_vs_lhp[pid] = data
        else:
            warnings.append(f"[collector] no vs-LHP split available for player {pid}")

    if batter_ids:
        sources.append("mlb_stats_api:hitting_season_stats")
        sources.append("mlb_stats_api:hitting_game_log")
        sources.append("mlb_stats_api:hitting_platoon_splits")

    return RawBatterStats(
        date=date,
        season=season,
        season_hitting=season_hitting,
        game_log_hitting=game_log_hitting,
        platoon_vs_rhp=platoon_vs_rhp,
        platoon_vs_lhp=platoon_vs_lhp,
        sources_used=sources,
        warnings=warnings,
        errors=errors,
    )


def collect_batter_bios(
    batter_ids: List[str],
    date: str,
    cache_root: Path = cache.DEFAULT_CACHE_ROOT,
) -> Dict[str, dict]:
    """Bio info (batSide/etc.) for a list of starting-lineup hitters,
    reusing the same `fetch_person` endpoint already used to resolve
    pitcher throwing hand. batters.json itself never carries `bats` (see
    research/normalizer.py) -- this is what research.batter_enrichment
    uses to fill it in without touching that existing, already-tested
    pipeline."""
    people: Dict[str, dict] = {}
    for pid in batter_ids:
        person = cache.get_or_fetch(cache_root, date, f"person_{pid}", lambda pid=pid: fetch_person(pid))
        if person:
            people[pid] = person
    return people


def fetch_team_recent_schedule(team_id: str, start_date: str, end_date: str) -> Optional[dict]:
    """One team's schedule over a date range (used to find its most
    recently PLAYED games before a slate date, for probable-starter
    inference -- see dfs/probable_starters.py). Returns None on any
    failure rather than raising -- a single team's lookup failing must
    never take down a refresh covering many teams."""
    url = f"{MLB_STATS_BASE}/schedule?sportId=1&teamId={team_id}&startDate={start_date}&endDate={end_date}"
    try:
        return _get_json(url)
    except _FETCH_ERRORS:
        return None


def fetch_boxscore(game_id: str) -> Optional[dict]:
    """Full boxscore for one COMPLETED game -- includes each team's actual
    starting batting order (dfs/probable_starters.py's real-evidence
    source for "who started recently, and in what order"). A Final game's
    boxscore never changes, so callers should cache this indefinitely
    (see research/cache.py's DEFAULT_RESULTS_CACHE_ROOT docstring for the
    same reasoning already established for postgame pitcher results).
    Mirrors evaluation/results_collector.py::fetch_boxscore exactly, but
    lives here so dfs/ and research/ (both PREGAME-path packages, see
    tests/test_architecture_separation.py) never need to import
    evaluation/ (a POSTGAME-only package) just to read a historical,
    already-completed game's real lineup -- that is not a lookahead-bias
    concern, since the game being inspected is always from a date BEFORE
    the slate being built, never today's own games."""
    url = f"{MLB_STATS_BASE}/game/{game_id}/boxscore"
    try:
        return _get_json(url)
    except _FETCH_ERRORS:
        return None
