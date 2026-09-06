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
import sys
import time
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


def _fetch_bulk_hydrated_people(player_ids: List[str], hydrate_expr: str, chunk_size: int = 50) -> Dict[str, dict]:
    """MLB BATTER AGENT PERFORMANCE FIX: the real, measured root cause of
    the batter agent's dominant cost -- collect_batter_stats made 4
    SEQUENTIAL HTTP calls per hitter (season/gameLog/platoon x2), each
    ~1.7s, for up to 270+ real starting-lineup hitters, totaling 461.89s
    on a real production run (see this milestone's own profiling). MLB
    Stats API's own `/people?personIds=id1,id2,...&hydrate=stats(...)`
    endpoint (empirically verified live -- NOT assumed from
    documentation -- to return each person's own `stats` array identical
    in shape/count/values to what the single-player
    `/people/{id}/stats?...` endpoint returns for the exact same
    stats/group/season/sitCodes) lets ONE request cover many players at
    once. Chunked (default 50 IDs/request) to keep each request's
    URL/response size reasonable and to isolate one bad chunk from
    poisoning the whole batch -- a failed chunk simply contributes no
    data for its players (same never-raises philosophy as every other
    collector function; the caller reports a normal per-player "no
    stats available" warning for anyone missing from the result, exactly
    as a failed single-player fetch already did before this change).
    Returns {player_id: {"stats": [...]}} -- the SAME shape
    fetch_batter_season_stats/fetch_pitcher_season_stats/etc. already
    returned per player, so every downstream enrichment function
    (research/batter_enrichment.py, research/enrichment.py) needs zero
    changes."""
    results: Dict[str, dict] = {}
    for i in range(0, len(player_ids), chunk_size):
        chunk = player_ids[i : i + chunk_size]
        url = f"{MLB_STATS_BASE}/people?personIds={','.join(chunk)}&hydrate=stats({hydrate_expr})"
        try:
            data = _get_json(url)
        except _FETCH_ERRORS:
            continue
        for person in data.get("people", []):
            pid = str(person.get("id"))
            stats = person.get("stats")
            if stats:
                results[pid] = {"stats": stats}
    return results


def _fetch_bulk_people(player_ids: List[str], chunk_size: int = 50) -> Dict[str, dict]:
    """Bulk bio lookup (no `hydrate=stats`) -- the same
    `/people?personIds=...` endpoint _fetch_bulk_hydrated_people uses,
    just without the stats hydrate expression. Empirically verified live
    to return the exact same fields per person as the single-player
    `/people/{id}` endpoint. Returns {player_id: raw_person_dict}."""
    results: Dict[str, dict] = {}
    for i in range(0, len(player_ids), chunk_size):
        chunk = player_ids[i : i + chunk_size]
        url = f"{MLB_STATS_BASE}/people?personIds={','.join(chunk)}"
        try:
            data = _get_json(url)
        except _FETCH_ERRORS:
            continue
        for person in data.get("people", []):
            pid = str(person.get("id"))
            results[pid] = person
    return results


def _collect_hydrated_stat_category(
    player_ids: List[str], season: str, date: str, cache_root: Path, cache_prefix: str, hydrate_expr: str,
) -> Dict[str, dict]:
    """Cache-first bulk collection for ONE stat category (season hitting,
    game log, a platoon split, ...) across many players -- checks the
    on-disk cache per player FIRST (the exact same `{cache_prefix}_
    {pid}_{season}` keys the old per-player get_or_fetch() calls used,
    so this is fully compatible with, and benefits from, whatever's
    already cached from an earlier run or the old code path), then
    bulk-fetches ONLY the players not already cached, in as few
    requests as _fetch_bulk_hydrated_people needs. Each newly-fetched
    player's result is written back under that SAME per-player key, so
    a later single-player cache read still finds it. Never raises."""
    result: Dict[str, dict] = {}
    missing: List[str] = []
    for pid in player_ids:
        cached = cache.read(cache_root, date, f"{cache_prefix}_{pid}_{season}")
        if cached is not None:
            result[pid] = cached
        else:
            missing.append(pid)
    if missing:
        fetched = _fetch_bulk_hydrated_people(missing, hydrate_expr)
        for pid, data in fetched.items():
            result[pid] = data
            cache.write(cache_root, date, f"{cache_prefix}_{pid}_{season}", data)
    return result



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
    scored (with lower confidence for that pitcher).

    MLB BATTER AGENT PERFORMANCE FIX: this function is called TWICE per
    cycle for the same real pitchers -- once by the Pitcher Agent, once
    by the Batter Agent's own opposing-pitcher-context build (see
    scripts/run_real_batter_agent.py::_build_opposing_pitcher_index,
    intentionally reusing pregame pitcher research rather than the
    Pitcher Agent's scores). The on-disk cache already made the SECOND
    call cheap once the first had run; batching (like
    collect_batter_stats above) additionally makes the FIRST call fast,
    and per-pitcher-id caching still means neither call ever re-fetches
    the same player twice in one day even across process boundaries."""
    warnings: List[str] = []
    errors: List[str] = []
    sources: List[str] = []

    t0 = time.monotonic()
    season_pitching = _collect_hydrated_stat_category(
        pitcher_ids, season, date, cache_root, "season_pitching", f"group=[pitching],type=[season],season={season}",
    )
    game_log_pitching = _collect_hydrated_stat_category(
        pitcher_ids, season, date, cache_root, "gamelog_pitching", f"group=[pitching],type=[gameLog],season={season}",
    )
    elapsed = time.monotonic() - t0

    for pid in pitcher_ids:
        if pid not in season_pitching:
            warnings.append(f"[collector] no season pitching stats available for player {pid}")
        if pid not in game_log_pitching:
            warnings.append(f"[collector] no game log available for player {pid}")

    print(
        f"[collector] collect_pitcher_stats (batched: season+gamelog) n={len(pitcher_ids)} elapsed={elapsed:.2f}s",
        file=sys.stderr, flush=True,
    )

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
    becomes a warning, not a fatal error.

    MLB BATTER AGENT PERFORMANCE FIX: previously 4 sequential per-player
    HTTP calls (measured live: 270 real hitters x ~1.7s x 4 calls =
    461.89s, the dominant cost of the whole batter agent run). Now 4
    bulk-hydrated requests (chunked) via _collect_hydrated_stat_category
    -- semantically identical per-player results (empirically verified:
    the bulk endpoint returns the same `stats` shape/values as the old
    single-player endpoint), just fetched in far fewer round trips."""
    warnings: List[str] = []
    errors: List[str] = []
    sources: List[str] = []

    t0 = time.monotonic()
    season_hitting = _collect_hydrated_stat_category(
        batter_ids, season, date, cache_root, "season_hitting", f"group=[hitting],type=[season],season={season}",
    )
    game_log_hitting = _collect_hydrated_stat_category(
        batter_ids, season, date, cache_root, "gamelog_hitting", f"group=[hitting],type=[gameLog],season={season}",
    )
    platoon_vs_rhp = _collect_hydrated_stat_category(
        batter_ids, season, date, cache_root, "platoon_vr", f"group=[hitting],type=[statSplits],season={season},sitCodes=[vr]",
    )
    platoon_vs_lhp = _collect_hydrated_stat_category(
        batter_ids, season, date, cache_root, "platoon_vl", f"group=[hitting],type=[statSplits],season={season},sitCodes=[vl]",
    )
    elapsed = time.monotonic() - t0

    for pid in batter_ids:
        if pid not in season_hitting:
            warnings.append(f"[collector] no season hitting stats available for player {pid}")
        if pid not in game_log_hitting:
            warnings.append(f"[collector] no hitting game log available for player {pid}")
        if pid not in platoon_vs_rhp:
            warnings.append(f"[collector] no vs-RHP split available for player {pid}")
        if pid not in platoon_vs_lhp:
            warnings.append(f"[collector] no vs-LHP split available for player {pid}")

    print(
        f"[collector] collect_batter_stats (batched: season+gamelog+platoon x2) n={len(batter_ids)} elapsed={elapsed:.2f}s",
        file=sys.stderr, flush=True,
    )

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
    pipeline.

    MLB BATTER AGENT PERFORMANCE FIX: batched (cache-first, bulk-fetch
    only what's missing) instead of one HTTP call per hitter -- see
    _fetch_bulk_people."""
    people: Dict[str, dict] = {}
    missing: List[str] = []
    for pid in batter_ids:
        cached = cache.read(cache_root, date, f"person_{pid}")
        if cached is not None:
            people[pid] = cached
        else:
            missing.append(pid)
    t0 = time.monotonic()
    if missing:
        fetched = _fetch_bulk_people(missing)
        for pid, person in fetched.items():
            people[pid] = person
            cache.write(cache_root, date, f"person_{pid}", person)
    print(f"[collector] collect_batter_bios (batched) n={len(batter_ids)} elapsed={time.monotonic() - t0:.2f}s", file=sys.stderr, flush=True)
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
