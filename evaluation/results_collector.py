"""Collection stage for ACTUAL (postgame) pitcher results.

This is the only module in evaluation/ that talks to the network, mirroring
research/collector.py's role for the pregame side. It is a SEPARATE module
in a SEPARATE package on purpose: the pregame Pitcher Agent pipeline
(agents/, research/, scripts/run_real_pitcher_agent.py) must never import
anything from evaluation/, and physically isolating "talks to postgame
data" here makes that boundary easy to see and easy to test (see
tests/test_architecture_separation.py).

Uses the same free, public MLB Stats API as research/collector.py --
just different endpoints (schedule status + boxscore) queried after the
fact. Reuses research.collector.fetch_schedule directly rather than
duplicating that request (evaluation depending on research is the
allowed direction; the reverse is not).
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from research import cache
from research.collector import MLB_STATS_BASE, fetch_schedule

REQUEST_TIMEOUT_SECONDS = 15
_FETCH_ERRORS = (urllib.error.URLError, TimeoutError, ValueError)


@dataclass
class RawResultsData:
    date: str
    schedule: dict = field(default_factory=dict)
    boxscores: Dict[str, dict] = field(default_factory=dict)  # game_id -> raw boxscore payload
    sources_used: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_boxscore(game_id: str):
    """Full postgame boxscore for one game -- per-team pitching lines
    (innings, outs, K, BB, H, ER, HR, HBP, pitch count, decision),
    keyed by MLB player ID. Returns None on any failure."""
    url = f"{MLB_STATS_BASE}/game/{game_id}/boxscore"
    try:
        return _get_json(url)
    except _FETCH_ERRORS:
        return None


def collect_actual_results(
    date: str,
    game_ids: List[str],
    cache_root: Path = cache.DEFAULT_RESULTS_CACHE_ROOT,
) -> RawResultsData:
    """Collect the day's schedule (for game status: Final/Postponed/etc.)
    plus one boxscore per unique game_id referenced by a prediction
    snapshot. Never raises -- a missing payload becomes a warning, and
    evaluation.results_enrichment turns that into an explicit status
    (e.g. "missing_result") rather than a crash."""
    warnings: List[str] = []
    errors: List[str] = []
    sources: List[str] = []

    schedule: dict = {}
    try:
        schedule = fetch_schedule(date)
        sources.append("mlb_stats_api:schedule")
    except _FETCH_ERRORS as exc:
        errors.append(f"[results_collector] failed to fetch schedule for {date}: {exc}")

    boxscores: Dict[str, dict] = {}
    for game_id in sorted(set(game_ids)):
        if not game_id:
            continue
        data = cache.get_or_fetch(
            cache_root, date, f"boxscore_{game_id}",
            lambda gid=game_id: fetch_boxscore(gid),
        )
        if data:
            boxscores[game_id] = data
        else:
            warnings.append(f"[results_collector] no boxscore available for game {game_id}")

    if game_ids:
        sources.append("mlb_stats_api:boxscore")

    return RawResultsData(
        date=date,
        schedule=schedule,
        boxscores=boxscores,
        sources_used=sources,
        warnings=warnings,
        errors=errors,
    )
