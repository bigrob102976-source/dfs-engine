"""Canonical MLB Player Identity Foundation.

Decouples PLAYER IDENTITY from STARTING-LINEUP CONFIRMATION. Before this
module existed, this project's ONLY player-identity source was
dfs/player_resolver.py's canonical index, built exclusively from
research_output/<date>/pitchers.json (today's probable starters) and
batters.json (today's POSTED starting lineups) -- see that module's own
docstring. A real, active-roster hitter whose team's lineup simply
hadn't posted yet at research time had NO identity record to match
against at all, and came back "unmatched" -- not because who they are
was genuinely unknown, but because of an unrelated, timing-dependent
data-availability gap. Live-confirmed impact (this milestone's own
audit, 2026-08-23's real DK Main slate): 731/746 DK players unmatched,
purely because that day's research ran before lineups posted.

This module fixes the ROOT CAUSE by adding a second, INDEPENDENT
identity source that has nothing to do with lineup confirmation: each
playing team's real MLB active roster (player_identity/roster_source.py
-- MLB Stats API, the same source research/collector.py already uses
for everything else). A team's active roster is known the moment the
day's SCHEDULE is known (research_output/<date>/teams.json and
games.json are both schedule-derived, never lineup-derived -- see
research/normalizer.py::normalize_games), which is why this refresh can
run BEFORE lineup-dependent research, exactly as the milestone's
intended pipeline order describes:

    DraftKings live slate -> teams -> MLB roster identity refresh ->
    canonical DK<->MLB crosswalk -> lineup/probable starter research ->
    eligibility -> projections

IDENTITY vs ELIGIBILITY stay strictly separate, by construction, not by
convention: this module (and player_identity/identity_package.py, which
feeds its output into dfs/player_resolver.py) only ever WIDENS the set
of players a DK row CAN resolve an mlb_player_id against. It is never
consulted by dfs/eligibility.py, which continues to compute
STARTING_PITCHER/STARTING_HITTER/BENCH/RELIEF_PITCHER/LINEUP_UNCONFIRMED
purely from the original, narrow, confirmed-lineup-only
research_pitchers/research_batters lists -- completely unchanged by this
milestone. A player can therefore be identity-RESOLVED (mlb_player_id
known) while remaining optimizer_eligible=False (bench hitter, relief
pitcher, unconfirmed lineup) -- exactly the milestone's explicit
requirement.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from research.prediction_snapshot import timestamp_tag

from player_identity.crosswalk_builder import build_team_identities
from player_identity.historical_backfill import DEFAULT_HISTORICAL_CROSSWALK_PATH, load_historical_handedness
from player_identity.models import CanonicalIdentity
from player_identity.persistence import (
    DEFAULT_CROSSWALK_ROOT,
    DEFAULT_IDENTITY_SNAPSHOT_ROOT,
    load_crosswalk,
    merge_crosswalk,
    save_crosswalk,
    save_identity_refresh_snapshot,
)
from player_identity.roster_source import DEFAULT_ROSTER_CACHE_ROOT, fetch_cached_team_roster, parse_roster_entries


@dataclass
class IdentityRefreshResult:
    slate_date: str
    generated_at: str
    teams_total: int
    teams_fetched: int
    teams_failed: List[str] = field(default_factory=list)
    players_seen_this_refresh: int = 0
    crosswalk_size_after: int = 0
    historical_backfill_available: bool = False
    historical_backfill_applied_count: int = 0
    snapshot_path: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _load_teams(research_output_root: str, slate_date: str) -> List[dict]:
    import json
    path = Path(research_output_root) / slate_date / "teams.json"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def refresh_identity(
    slate_date: str,
    research_output_root: str = "research_output",
    cache_root: Path = DEFAULT_ROSTER_CACHE_ROOT,
    crosswalk_root: Path = DEFAULT_CROSSWALK_ROOT,
    snapshot_root: Path = DEFAULT_IDENTITY_SNAPSHOT_ROOT,
    historical_crosswalk_path: Path = DEFAULT_HISTORICAL_CROSSWALK_PATH,
) -> IdentityRefreshResult:
    """Refreshes canonical MLB identity for every team playing on
    `slate_date`. Fetches each team's active roster AT MOST ONCE (cached
    per date+team_id -- a rerun within the same day reuses the cache
    rather than re-fetching every team). Never raises: a missing
    schedule, a failed roster fetch for one team, or a missing
    historical backfill file all degrade gracefully rather than blocking
    the refresh."""
    generated_at = datetime.now(timezone.utc).isoformat()
    teams = _load_teams(research_output_root, slate_date)

    handedness_by_id = load_historical_handedness(historical_crosswalk_path)
    existing_crosswalk = load_crosswalk(output_root=crosswalk_root)

    new_identities: List[CanonicalIdentity] = []
    teams_fetched = 0
    teams_failed: List[str] = []

    for team in teams:
        team_id = str(team.get("team_id"))
        team_abbr = team.get("abbreviation")
        if not team_id or not team_abbr:
            continue
        raw_roster = fetch_cached_team_roster(team_id, slate_date, cache_root=cache_root)
        entries = parse_roster_entries(raw_roster)
        if not entries:
            teams_failed.append(team_abbr)
            continue
        teams_fetched += 1
        new_identities.extend(build_team_identities(team_abbr, entries, generated_at, handedness_by_id))

    backfill_applied = sum(1 for i in new_identities if i.bat_side or i.throw_hand)

    merged_crosswalk = merge_crosswalk(existing_crosswalk, new_identities)
    save_crosswalk(merged_crosswalk, generated_at, output_root=crosswalk_root)

    result = IdentityRefreshResult(
        slate_date=slate_date,
        generated_at=generated_at,
        teams_total=len(teams),
        teams_fetched=teams_fetched,
        teams_failed=teams_failed,
        players_seen_this_refresh=len(new_identities),
        crosswalk_size_after=len(merged_crosswalk),
        historical_backfill_available=bool(handedness_by_id),
        historical_backfill_applied_count=backfill_applied,
    )

    snapshot_path = save_identity_refresh_snapshot(
        result.to_dict(), slate_date, timestamp_tag(generated_at), output_root=snapshot_root,
    )
    result.snapshot_path = str(snapshot_path)
    return result
