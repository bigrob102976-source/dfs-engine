"""NFL M15 -- production DraftKings-access resilience.

Railway's own egress IP is blocked from reaching DraftKings directly --
the SAME real, already-documented block MLB's production dashboard hit
(see scripts/fetch_all_dfs_slates.py's docstring) and already solved
via an external-fetch + object-storage-cache-reuse architecture (see
dashboard/lib/optimizerWorkspace/poolCache.ts's PROVIDER_SLATE_
FRESHNESS_MS / provenance-check convention, mirrored here for NFL).

This module does NOT fetch DraftKings itself. It only reads back
artifacts a REAL live fetch already wrote -- either from a normal local
dev run, or from scripts/fetch_nfl_slates.py, an external script run on
a machine with real DraftKings network access (e.g. Windows Task
Scheduler + `railway run` to inject storage credentials, mirroring
MLB's own external-fetch pattern) that keeps a fresh snapshot available
for a Railway-hosted dashboard that cannot reach DraftKings itself.

No CSV/mock/synthetic fallback: every value read back here is real
DraftKings data from a real prior fetch, gated on real
DRAFTKINGS_UNOFFICIAL_LIVE provenance, never invented. A cache miss is
not handled here -- callers fall back to their own existing live fetch,
which still fails loudly (no silent substitute) if that also can't
reach DraftKings.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dfs.providers.source_provenance import DRAFTKINGS_UNOFFICIAL_LIVE
from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from nfl.models import NflPlayer, NflPoolBuildResult, NflPoolValidationFinding, NflPoolValidationResult
from nfl.persistence import DEFAULT_NFL_DFS_INPUT_ROOT, list_nfl_player_pools, load_latest_nfl_player_pool

# Mirrors dashboard/lib/optimizerWorkspace/poolCache.ts's
# PROVIDER_SLATE_FRESHNESS_MS exactly -- the same 15-minute reuse
# window MLB's production dashboard already relies on.
POOL_CACHE_FRESHNESS_SECONDS = 15 * 60

DEFAULT_NFL_UNIVERSE_ROOT = Path(__file__).resolve().parent.parent / "dfs_input" / "nfl" / "_universe"

_POOL_TIMESTAMP_RE = re.compile(r"nfl_player_pool_(\d{8}T\d{6})\.json$")
_UNIVERSE_TIMESTAMP_RE = re.compile(r"nfl_universe_(\d{8}T\d{6})\.json$")


def _parse_timestamp(name: str, pattern: "re.Pattern") -> Optional[datetime]:
    match = pattern.search(name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _fresh_enough(timestamp: Optional[datetime], max_age_seconds: int, now_utc: Optional[datetime] = None) -> bool:
    if timestamp is None:
        return False
    now_utc = now_utc or datetime.now(timezone.utc)
    return (now_utc - timestamp).total_seconds() <= max_age_seconds


def _pool_result_from_dict(doc: dict) -> NflPoolBuildResult:
    players = [NflPlayer(**p) for p in doc["players"]]
    v = doc["validation"]
    validation = NflPoolValidationResult(
        passed=v["passed"],
        findings=[NflPoolValidationFinding(f["level"], f["message"]) for f in v["findings"]],
        total_players=v["total_players"], position_counts=v["position_counts"],
        team_count=v["team_count"], game_count=v["game_count"],
        salary_min=v["salary_min"], salary_max=v["salary_max"],
    )
    return NflPoolBuildResult(
        draft_group_id=doc["draft_group_id"], slate_date=doc["slate_date"], slate_name=doc["slate_name"],
        players=players, validation=validation, source_provenance=doc["source_provenance"],
    )


def load_fresh_cached_pool(
    slate_date: str, draft_group_id: int,
    max_age_seconds: int = POOL_CACHE_FRESHNESS_SECONDS,
    output_root: Path = DEFAULT_NFL_DFS_INPUT_ROOT,
    now_utc: Optional[datetime] = None,
) -> Optional[NflPoolBuildResult]:
    """A recently-persisted (<= max_age_seconds old) real pool snapshot
    for this EXACT DraftGroup, or None if no snapshot exists, it's for a
    different DraftGroup, it isn't real DraftKings-live provenance, or
    it's stale. Never fabricates a DraftGroup match or a timestamp."""
    pools = list_nfl_player_pools(slate_date, output_root)
    if not pools:
        return None
    latest_path = pools[-1]
    timestamp = _parse_timestamp(latest_path.name, _POOL_TIMESTAMP_RE)
    if not _fresh_enough(timestamp, max_age_seconds, now_utc):
        return None

    doc = load_latest_nfl_player_pool(slate_date, output_root)
    if doc is None or doc.get("draft_group_id") != draft_group_id:
        return None
    if doc.get("source_provenance") != DRAFTKINGS_UNOFFICIAL_LIVE:
        return None
    return _pool_result_from_dict(doc)


def save_nfl_universe_snapshot(slates: List[dict], timestamp: str, output_root: Path = DEFAULT_NFL_UNIVERSE_ROOT) -> Path:
    """Persists the real Classic-slate discovery list (the same shape
    scripts/nfl_dashboard_slates.py already returns) so a caller without
    live DraftKings access can still resolve draft_group_id ->
    slate_date and populate the slate picker. Immutable, like every
    other artifact this project persists (see nfl/persistence.py's own
    discipline)."""
    path = Path(output_root) / f"nfl_universe_{timestamp}.json"
    raise_if_exists(path)
    doc = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "source_provenance": DRAFTKINGS_UNOFFICIAL_LIVE, "slates": slates}
    save_json(path, doc)
    return path


class NflSlateDiscoveryError(Exception):
    """Raised when a live DraftKings universe discovery call fails and
    no fresh cached universe snapshot covers the requested DraftGroup
    either -- callers format this exactly as they already formatted a
    live collect_sport_universe() failure before this wrapper existed."""


def resolve_nfl_slate_date(
    draft_group_id: int, max_age_seconds: int = POOL_CACHE_FRESHNESS_SECONDS,
    output_root: Path = DEFAULT_NFL_UNIVERSE_ROOT, now_utc: Optional[datetime] = None,
) -> Optional[str]:
    """Resolves draft_group_id -> slate_date, preferring a recent cached
    universe snapshot (see save_nfl_universe_snapshot(), written by the
    external scripts/fetch_nfl_slates.py) over a live DraftKings call.
    Returns None if the DraftGroup isn't found in whichever source was
    used. Raises NflSlateDiscoveryError only when BOTH the cache misses
    (or is stale) AND the live fallback call itself fails -- local dev,
    where DraftKings access always works, reaches the exact same live
    call and the exact same failure branch it always did."""
    cached = load_fresh_cached_universe(max_age_seconds, output_root, now_utc=now_utc)
    if cached is not None:
        match = next((s for s in cached if s.get("draft_group_id") == draft_group_id), None)
        if match is not None:
            return match.get("slate_date")

    from draftkings_unofficial import collector

    universe = collector.collect_sport_universe("NFL")
    if universe.status != collector.STATUS_OK:
        raise NflSlateDiscoveryError(f"{universe.status} ({universe.error})")
    slate = next((s for s in universe.slates if s.draft_group_id == draft_group_id), None)
    if slate is None:
        return None
    return collector.slate_local_date(slate)


def load_fresh_cached_universe(
    max_age_seconds: int = POOL_CACHE_FRESHNESS_SECONDS,
    output_root: Path = DEFAULT_NFL_UNIVERSE_ROOT,
    now_utc: Optional[datetime] = None,
) -> Optional[List[dict]]:
    """The real Classic-slate list from a recent (<= max_age_seconds)
    external fetch, or None on any miss/staleness/bad provenance."""
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    keys = storage.list_files(to_artifact_key(Path(output_root)), prefix="nfl_universe_", ext=".json")
    if not keys:
        return None
    latest_key = keys[-1]
    timestamp = _parse_timestamp(Path(latest_key).name, _UNIVERSE_TIMESTAMP_RE)
    if not _fresh_enough(timestamp, max_age_seconds, now_utc):
        return None
    doc = storage.read_json(latest_key)
    if doc is None or doc.get("source_provenance") != DRAFTKINGS_UNOFFICIAL_LIVE:
        return None
    return doc.get("slates")
