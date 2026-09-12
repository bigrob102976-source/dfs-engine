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

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

from dfs.providers.source_provenance import DRAFTKINGS_UNOFFICIAL_LIVE
from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from nfl.models import NflPlayer, NflPoolBuildResult, NflPoolValidationFinding, NflPoolValidationResult
from nfl.persistence import DEFAULT_NFL_DFS_INPUT_ROOT, list_nfl_player_pools, load_latest_nfl_player_pool

# Mirrors dashboard/lib/optimizerWorkspace/poolCache.ts's
# PROVIDER_SLATE_FRESHNESS_MS exactly -- the same 15-minute reuse
# window MLB's production dashboard already relies on.
POOL_CACHE_FRESHNESS_SECONDS = 15 * 60

# 2026-09-11 incident fix -- mirrors dashboard/lib/optimizerWorkspace/
# poolCache.ts's PROVIDER_SLATE_STALE_MAX_MS exactly (same 2-hour
# ceiling, same reasoning, same platform): a real, correctly-
# provenanced pool older than FRESHNESS is still reused (marked
# "stale") rather than triggering a live DraftKings call that is
# PERMANENTLY blocked from Railway's egress IP -- confirmed live: a
# request for a pool whose cache had gone ~2 hours stale (the external
# worker was behind) fell through to a live call and returned a 502
# with DraftKings' own "ACCESS_RESTRICTED (HTTP 403)". Past this
# ceiling the pool is genuinely too old to trust (salaries/injury
# status/lineup news could have materially changed since) -- refuse it
# with a clear error rather than serving it OR attempting the doomed
# live call. No NFL-specific reason to pick a different bound than
# MLB's already-proven one on the same DK platform.
POOL_CACHE_STALE_MAX_SECONDS = 2 * 60 * 60

DEFAULT_NFL_UNIVERSE_ROOT = Path(__file__).resolve().parent.parent / "dfs_input" / "nfl" / "_universe"

# Matches both the new <timestamp>_<draft_group_id>.json filenames
# (nfl/persistence.py's 2026-09-11 incident fix) and old, suffix-less
# ones already in production.
_POOL_TIMESTAMP_RE = re.compile(r"nfl_player_pool_(\d{8}T\d{6})(?:_\d+)?\.json$")
_UNIVERSE_TIMESTAMP_RE = re.compile(r"nfl_universe_(\d{8}T\d{6})\.json$")

PoolFreshness = Literal["fresh", "stale", "expired"]


def is_railway_production_environment() -> bool:
    """True only inside an actual Railway-hosted container (any
    environment, not just one named "production" -- the underlying
    constraint is Railway's own datacenter egress IP being blocked by
    DraftKings, not the environment's name). RAILWAY_ENVIRONMENT is set
    automatically by the platform on every deployed service and is
    never present on a local dev machine, so this needs no separate
    config flag. Callers use this to refuse a live DraftKings call
    instead of attempting one that is guaranteed to fail -- see
    POOL_CACHE_STALE_MAX_SECONDS's own docstring for the incident this
    fixes."""
    return bool(os.environ.get("RAILWAY_ENVIRONMENT"))


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


def _classify_freshness(
    timestamp: Optional[datetime], fresh_max_seconds: int, stale_max_seconds: int, now_utc: Optional[datetime] = None,
) -> Optional[PoolFreshness]:
    """Mirrors poolCache.ts's providerSlateFreshness exactly: None when
    there's no parseable timestamp at all (treated as not reusable,
    same as this module's pre-existing behavior), else "fresh" / "stale"
    / "expired" against the two ceilings above."""
    if timestamp is None:
        return None
    now_utc = now_utc or datetime.now(timezone.utc)
    age_seconds = (now_utc - timestamp).total_seconds()
    if age_seconds <= fresh_max_seconds:
        return "fresh"
    if age_seconds <= stale_max_seconds:
        return "stale"
    return "expired"


def _pool_result_from_dict(doc: dict, data_status: PoolFreshness, pool_generated_at_utc: Optional[str]) -> NflPoolBuildResult:
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
        data_status=data_status, pool_generated_at_utc=pool_generated_at_utc,
    )


def load_fresh_cached_pool(
    slate_date: str, draft_group_id: int,
    max_age_seconds: int = POOL_CACHE_FRESHNESS_SECONDS,
    stale_max_age_seconds: int = POOL_CACHE_STALE_MAX_SECONDS,
    output_root: Path = DEFAULT_NFL_DFS_INPUT_ROOT,
    now_utc: Optional[datetime] = None,
) -> Optional[NflPoolBuildResult]:
    """A real, correctly-provenanced pool snapshot for this EXACT
    DraftGroup, or None if no snapshot exists, it's for a different
    DraftGroup, it isn't real DraftKings-live provenance, or it's past
    stale_max_age_seconds ("expired" -- see that constant's own
    docstring for why this refuses rather than serving it or attempting
    a live call). Within max_age_seconds the returned result's
    data_status is "fresh"; between max_age_seconds and
    stale_max_age_seconds it is "stale" -- reused deliberately rather
    than triggering a doomed live DraftKings call from production (see
    is_railway_production_environment/POOL_CACHE_STALE_MAX_SECONDS).
    Callers that show this to a user MUST surface data_status honestly,
    never presenting a stale pool as current. Never fabricates a
    DraftGroup match or a timestamp.

    2026-09-11 incident fix: list_nfl_player_pools is now called WITH
    draft_group_id, so a date with several concurrently-live DraftGroups
    (confirmed live: 2026-09-13 has five) each get their own file
    listing -- previously this took the single latest file across EVERY
    DraftGroup sharing the date, so whichever DraftGroup happened to be
    fetched most recently silently answered lookups for every other one
    too (or, combined with the filename-collision bug this same incident
    also fixed in nfl/persistence.py, usually just found nothing at all
    for every DraftGroup but the one lucky enough to win the collision)."""
    pools = list_nfl_player_pools(slate_date, draft_group_id, output_root)
    if not pools:
        return None
    latest_path = pools[-1]
    timestamp = _parse_timestamp(latest_path.name, _POOL_TIMESTAMP_RE)
    freshness = _classify_freshness(timestamp, max_age_seconds, stale_max_age_seconds, now_utc)
    if freshness is None or freshness == "expired":
        return None

    doc = load_latest_nfl_player_pool(slate_date, draft_group_id, output_root)
    if doc is None or doc.get("draft_group_id") != draft_group_id:
        return None
    if doc.get("source_provenance") != DRAFTKINGS_UNOFFICIAL_LIVE:
        return None
    return _pool_result_from_dict(doc, freshness, timestamp.isoformat() if timestamp else None)


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
    stale_max_age_seconds: int = POOL_CACHE_STALE_MAX_SECONDS,
    output_root: Path = DEFAULT_NFL_UNIVERSE_ROOT, now_utc: Optional[datetime] = None,
) -> Optional[str]:
    """Resolves draft_group_id -> slate_date, preferring a cached
    universe snapshot (fresh OR stale -- see load_fresh_cached_universe;
    written by the external scripts/fetch_nfl_slates.py) over a live
    DraftKings call. Returns None if the DraftGroup isn't found in
    whichever source was used.

    2026-09-11 incident fix: the live fallback is never attempted inside
    a Railway-hosted container (is_railway_production_environment()) --
    that call is PERMANENTLY blocked by DraftKings' own IP-level
    restriction on Railway's egress, so attempting it is guaranteed to
    fail and previously surfaced as a bare 502 with no useful message
    (confirmed live: ACCESS_RESTRICTED HTTP 403). In that environment,
    a cache miss/expiry raises NflSlateDiscoveryError immediately with a
    message that says so, instead of a doomed network round trip. Local
    dev (where DraftKings access always works) is unaffected -- it
    reaches the exact same live call and the exact same failure branch
    it always did."""
    cached = load_fresh_cached_universe(max_age_seconds, stale_max_age_seconds, output_root, now_utc=now_utc)
    if cached is not None:
        match = next((s for s in cached if s.get("draft_group_id") == draft_group_id), None)
        if match is not None:
            return match.get("slate_date")

    if is_railway_production_environment():
        raise NflSlateDiscoveryError(
            "no fresh-or-stale cached universe snapshot covers this DraftGroup, and a live DraftKings call is "
            "never attempted from production (Railway's egress IP is permanently blocked) -- the external fetch "
            "worker needs to catch up."
        )

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
    stale_max_age_seconds: int = POOL_CACHE_STALE_MAX_SECONDS,
    output_root: Path = DEFAULT_NFL_UNIVERSE_ROOT,
    now_utc: Optional[datetime] = None,
) -> Optional[List[dict]]:
    """The real Classic-slate list from the latest external fetch, fresh
    OR stale (see POOL_CACHE_STALE_MAX_SECONDS), or None on any miss/
    expiry/bad provenance. The universe is just a draft_group_id ->
    slate_date lookup (not player-facing salary/status data), so unlike
    the pool this has no data_status to surface -- reusing it stale is
    safe as long as it's within the same ceiling."""
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    keys = storage.list_files(to_artifact_key(Path(output_root)), prefix="nfl_universe_", ext=".json")
    if not keys:
        return None
    latest_key = keys[-1]
    timestamp = _parse_timestamp(Path(latest_key).name, _UNIVERSE_TIMESTAMP_RE)
    freshness = _classify_freshness(timestamp, max_age_seconds, stale_max_age_seconds, now_utc)
    if freshness is None or freshness == "expired":
        return None
    doc = storage.read_json(latest_key)
    if doc is None or doc.get("source_provenance") != DRAFTKINGS_UNOFFICIAL_LIVE:
        return None
    return doc.get("slates")


DEFAULT_SNAPSHOT_RETENTION_COUNT = 12


def list_nfl_universe_snapshots(output_root: Path = DEFAULT_NFL_UNIVERSE_ROOT) -> List[str]:
    """Every saved universe snapshot key, oldest first (mirrors
    nfl/persistence.py::list_nfl_player_pools's ordering)."""
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    return storage.list_files(to_artifact_key(Path(output_root)), prefix="nfl_universe_", ext=".json")


def prune_old_snapshots(paths_or_keys: List, keep_last: int = DEFAULT_SNAPSHOT_RETENTION_COUNT) -> List:
    """Deletes all but the most recent `keep_last` entries from an
    oldest-first snapshot listing (nfl/persistence.py::
    list_nfl_player_pools() or list_nfl_universe_snapshots() above).

    Bounds the otherwise-unbounded growth a recurring external fetch
    (scripts/fetch_nfl_slates.py, run every few minutes) would cause.
    These are a rolling operational CACHE for production DK-access
    resilience, not the permanent evaluation-integrity prediction
    history CLAUDE.md protects (predictions/, ownership_predictions/,
    etc. are untouched here -- a stale DK pool re-fetch has no
    evaluation value once a fresher one exists). Returns the entries
    actually deleted."""
    if len(paths_or_keys) <= keep_last:
        return []
    to_delete = paths_or_keys[:-keep_last]
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    for entry in to_delete:
        key = entry if isinstance(entry, str) else to_artifact_key(Path(entry))
        storage.delete(key)
    return to_delete
