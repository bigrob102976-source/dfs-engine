"""Orchestrates one FantasyPros projection fetch: hitters + pitchers ->
DK-points conversion (fantasypros/scoring.py) -> MLB identity matching
(fantasypros/matcher.py) -> a single FantasyProsSnapshot, ready to save
(fantasypros/persistence.py).

FantasyPros remains fully OPTIONAL and never raises out of
build_fantasypros_snapshot(): every failure mode (not configured, auth
rejected, rate limited, unavailable, no research package yet) is
returned as a structured {"status": ..., "error": ...} result instead,
so a caller (the admin slate pipeline) can always continue with Big
Money Native/AI regardless of what happened here.
"""

from datetime import datetime, timezone
from typing import Optional

from fantasypros import client
from fantasypros.matcher import match_fantasypros_players
from fantasypros.models import FantasyProsSnapshot
from fantasypros.scoring import calculate_fantasypros_hitter_dk_points, calculate_fantasypros_pitcher_dk_points
from research.adapters import batter_input as batter_adapter
from research.adapters import pitcher_input as pitcher_adapter
from research.adapters.pitcher_input import ResearchPackageNotFoundError

STATUS_NOT_CONFIGURED = "not_configured"
STATUS_READY = "ready"
STATUS_NO_RESEARCH = "no_research"
STATUS_API_ERROR = "api_error"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_research_package(date: str, research_output_root: str) -> Optional[dict]:
    """Read-only load -- deliberately does NOT build a missing research
    package (unlike dfs/pool_builder.py::ensure_research_package). By the
    time FantasyPros fetch runs in the slate pipeline, research/pitchers/
    batters have already run; a missing package here is a genuine
    upstream-ordering problem this function surfaces (STATUS_NO_RESEARCH)
    rather than silently triggering an expensive rebuild as a side effect
    of an OPTIONAL, comparison-only provider."""
    try:
        pitcher_pkg = pitcher_adapter.load_research_package(research_output_root, date)
    except ResearchPackageNotFoundError:
        return None
    batter_pkg = batter_adapter.load_research_package(research_output_root, date)
    return {"games": pitcher_pkg["games"], "teams": pitcher_pkg["teams"], "pitchers": pitcher_pkg["pitchers"], "batters": batter_pkg["batters"]}


def build_fantasypros_snapshot(date: str, research_output_root: str = "research_output") -> dict:
    """Returns {"status": str, "snapshot": FantasyProsSnapshot | None, "error": str | None}."""
    if not client.is_configured():
        return {"status": STATUS_NOT_CONFIGURED, "snapshot": None, "error": None}

    try:
        hitters_result = client.get_daily_projections(date, "H")
        pitchers_result = client.get_daily_projections(date, "P")
    except client.FantasyProsNotConfiguredError:
        return {"status": STATUS_NOT_CONFIGURED, "snapshot": None, "error": None}
    except (client.FantasyProsAuthenticationError, client.FantasyProsRateLimitedError, client.FantasyProsUnavailableError) as exc:
        return {"status": STATUS_API_ERROR, "snapshot": None, "error": str(exc)}

    package = _load_research_package(date, research_output_root)
    if package is None:
        return {"status": STATUS_NO_RESEARCH, "snapshot": None, "error": f"No research package found for {date} under {research_output_root}/."}

    hitter_matches = match_fantasypros_players(hitters_result.players, package)
    pitcher_matches = match_fantasypros_players(pitchers_result.players, package)

    for proj in hitter_matches:
        scored = calculate_fantasypros_hitter_dk_points(proj.raw_stats)
        proj.dk_points = scored["dk_points"]
        proj.dk_points_breakdown = scored["breakdown"]
    for proj in pitcher_matches:
        scored = calculate_fantasypros_pitcher_dk_points(proj.raw_stats)
        proj.dk_points = scored["dk_points"]
        proj.dk_points_breakdown = scored["breakdown"]

    all_players = hitter_matches + pitcher_matches
    snapshot = FantasyProsSnapshot(
        slate_date=date,
        retrieved_at=_now_iso(),
        hitter_count=len(hitter_matches),
        pitcher_count=len(pitcher_matches),
        hitters_matched=sum(1 for p in hitter_matches if p.match_status == "matched"),
        pitchers_matched=sum(1 for p in pitcher_matches if p.match_status == "matched"),
        public_api_limited=bool(hitters_result.public_api_limited or pitchers_result.public_api_limited),
        api_tier=hitters_result.tier or pitchers_result.tier,
        players=all_players,
    )
    return {"status": STATUS_READY, "snapshot": snapshot, "error": None}
