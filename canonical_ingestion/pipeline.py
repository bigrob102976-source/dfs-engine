"""M2/M3 -- top-level shadow-ingestion orchestration.

Real DK fetch (with byte-exact raw capture) -> RAW R2 -> canonical
normalize -> NORMALIZED R2. This is the Python half of the shadow path
only -- see canonical_ingestion/__init__.py for why the Postgres
shadow-CURRENT write is a separate, Node-owned step
(dashboard/scripts/promote-canonical-slate.ts) that reads the
NORMALIZED artifact this module writes.

M3 REDESIGN NOTE (2026-09-01 worker reliability finding): M2's original
ingest_slate_shadow() always ran its OWN independent real DK fetch, on
the theory that "both paths may receive the same real fetch." In
practice, scripts/fetch_dfs_slate.py (the legacy path) ALREADY performs
one real fetch per slate -- calling ingest_slate_shadow() afterward as
a separate subprocess meant every real slate was fetched from DK TWICE
per worker cycle. With multiple real Classic slates live at once, this
measurably doubled per-cycle wall-clock time and produced repeated
worker cycles that never completed within Task Scheduler's execution
window (confirmed live: two consecutive scheduled runs after the
fetch_dfs_slate.py -> subprocess(ingest_canonical_slate.py) design was
deployed never logged a completion at all).

FIX: build_normalized_from_fetch() below is the shared core (RAW
capture -- from an ALREADY-POPULATED RawCaptureRecorder -- through
NORMALIZED write) with no fetching of its own. scripts/fetch_dfs_slate.py
now passes `capture=` into the ONE real fetch it already makes and
calls this function in-process (no subprocess, no second fetch).
ingest_slate_shadow() (the original, fetch-owning entry point) is kept
for standalone/manual use (scripts/ingest_canonical_slate.py, M2K-style
manual backfill/proof) -- it now just does its own fetch and delegates
to the same shared core, so there is exactly ONE normalization
implementation either way.

M2I / M3C FAILURE ISOLATION: neither entry point below ever raises.
Every failure mode -- network, validation, storage -- is caught and
reported in the returned ShadowIngestionResult's error/error_type
fields. This is the contract that lets a caller run this AFTER its own
legacy artifact write has already succeeded, without any risk of a
canonical-path failure turning into a customer-facing outage. Errors
are never silently swallowed either -- callers are expected to print/
log a non-ok result clearly.
"""

from __future__ import annotations

import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from canonical.models import IDENTITY_STATUS_RESOLVED, IDENTITY_STATUS_REVIEW_REQUIRED, IDENTITY_STATUS_UNRESOLVED
from canonical_ingestion.identity_bridge import load_name_team_index
from canonical_ingestion.normalize import build_canonical_artifact
from canonical_ingestion.normalized_storage import write_normalized_artifact
from canonical_ingestion.raw_capture import RawCaptureRecorder, write_raw_capture
from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider
from draftkings_unofficial.cache import DkUnofficialCache
from research.artifact_storage import ARTIFACT_ROOT, resolve_artifact_storage


@dataclass
class ShadowIngestionResult:
    ok: bool
    provider_slate_id: Optional[str] = None
    internal_slate_id_proposed: Optional[str] = None
    raw_manifest_key: Optional[str] = None
    raw_hash: Optional[str] = None
    raw_is_duplicate_of_latest: Optional[bool] = None
    normalized_key: Optional[str] = None
    normalized_hash: Optional[str] = None
    is_semantic_duplicate: Optional[bool] = None
    player_count: Optional[int] = None
    resolved_count: Optional[int] = None
    unresolved_count: Optional[int] = None
    review_required_count: Optional[int] = None
    error: Optional[str] = None
    error_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def build_normalized_from_fetch(
    *, sport: str, site: str, provider_name: str, slate_info, provider_players: List, recorder: RawCaptureRecorder,
    date: str, fetched_at: Optional[str] = None,
) -> ShadowIngestionResult:
    """The shared core: RAW capture (from an ALREADY-POPULATED
    `recorder` -- no fetching happens here) through NORMALIZED R2
    write. Used both by ingest_slate_shadow() (which populates
    `recorder` via its own fetch) and directly by
    scripts/fetch_dfs_slate.py (which populates `recorder` from the ONE
    real fetch it already performs for the legacy path -- see this
    module's own M3 REDESIGN docstring for why avoiding a second fetch
    here matters). Never raises."""
    try:
        storage = resolve_artifact_storage(ARTIFACT_ROOT)
        provider_slate_id = slate_info.slate_id
        fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()

        raw_result = write_raw_capture(
            storage, sport=sport, slate_date=date, provider=provider_name, provider_slate_id=provider_slate_id,
            recorder=recorder, fetched_at=fetched_at,
        )

        internal_slate_id_proposed = str(uuid.uuid4())
        name_team_index = load_name_team_index()
        artifact = build_canonical_artifact(
            sport=sport, site=site, provider=provider_name, slate_info=slate_info, provider_players=provider_players,
            internal_slate_id=internal_slate_id_proposed, raw_hash=raw_result.raw_hash, name_team_index=name_team_index,
            fetched_at=fetched_at,
        )

        write_result = write_normalized_artifact(storage, artifact)

        statuses = [p.identity_status for p in artifact.players]
        return ShadowIngestionResult(
            ok=True,
            provider_slate_id=provider_slate_id,
            internal_slate_id_proposed=internal_slate_id_proposed,
            raw_manifest_key=raw_result.manifest_key,
            raw_hash=raw_result.raw_hash,
            raw_is_duplicate_of_latest=raw_result.is_duplicate_of_latest,
            normalized_key=write_result["key"],
            normalized_hash=artifact.normalized_hash,
            is_semantic_duplicate=write_result["isSemanticDuplicate"],
            player_count=len(artifact.players),
            resolved_count=statuses.count(IDENTITY_STATUS_RESOLVED),
            unresolved_count=statuses.count(IDENTITY_STATUS_UNRESOLVED),
            review_required_count=statuses.count(IDENTITY_STATUS_REVIEW_REQUIRED),
        )
    except Exception as exc:  # noqa: BLE001 -- M2I/M3C: report, never let a shadow-path failure propagate
        return ShadowIngestionResult(
            ok=False, provider_slate_id=getattr(slate_info, "slate_id", None),
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}", error_type=type(exc).__name__,
        )


def ingest_slate_shadow(*, date: str, provider_slate_id: str, sport: str = "MLB", site: str = "draftkings") -> ShadowIngestionResult:
    """Standalone/manual entry point (scripts/ingest_canonical_slate.py,
    M2K-style manual backfill/proof): runs ONE independent, real DK
    fetch for `provider_slate_id`, with its own fresh, unshared cache so
    `capture` always fires against a real network call rather than a
    shared-cache hit, then delegates to build_normalized_from_fetch()
    (the same core the automatic in-process path uses -- never a second,
    divergent implementation). Never raises."""
    try:
        recorder = RawCaptureRecorder()
        fresh_cache = DkUnofficialCache()
        provider = DraftKingsUnofficialProvider()

        fetch_result = provider.get_slate(date, sport=sport, site=site, research_games=[], capture=recorder.record, cache=fresh_cache)

        slate_info = next((s for s in fetch_result.slates if s.slate_id == provider_slate_id), None)
        if slate_info is None:
            return ShadowIngestionResult(
                ok=False, provider_slate_id=provider_slate_id,
                error=f"providerSlateId {provider_slate_id!r} was not among the slates this independent fetch discovered: "
                      f"{[s.slate_id for s in fetch_result.slates]}",
                error_type="slate_not_found",
            )
        provider_players = fetch_result.players_by_slate.get(slate_info.slate_id, [])
        return build_normalized_from_fetch(
            sport=sport, site=site, provider_name=provider.name, slate_info=slate_info, provider_players=provider_players,
            recorder=recorder, date=date,
        )
    except Exception as exc:  # noqa: BLE001 -- M2I/M3C: report, never let a shadow-path failure propagate
        return ShadowIngestionResult(
            ok=False, provider_slate_id=provider_slate_id,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}", error_type=type(exc).__name__,
        )
