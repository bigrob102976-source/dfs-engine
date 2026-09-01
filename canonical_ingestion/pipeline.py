"""M2 -- top-level shadow-ingestion orchestration.

Real DK fetch (with byte-exact raw capture) -> RAW R2 -> canonical
normalize -> NORMALIZED R2. This is the Python half of the shadow path
only -- see canonical_ingestion/__init__.py for why the Postgres
shadow-CURRENT write is a separate, Node-owned step
(dashboard/scripts/promote-canonical-slate.ts) that reads the
NORMALIZED artifact this module writes.

M2I FAILURE ISOLATION: ingest_slate_shadow() NEVER raises. Every
failure mode -- network, validation, storage -- is caught and reported
in the returned ShadowIngestionResult's error/error_type fields. This
is the contract that lets a caller (scripts/fetch_dfs_slate.py) run
this AFTER its own legacy artifact write has already succeeded, without
any risk of a canonical-path failure turning into a customer-facing
outage. Errors are never silently swallowed either -- the caller is
expected to print/log a non-ok result clearly (see this module's own
CLI wrapper, scripts/ingest_canonical_slate.py).
"""

from __future__ import annotations

import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

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


def ingest_slate_shadow(*, date: str, provider_slate_id: str, sport: str = "MLB", site: str = "draftkings") -> ShadowIngestionResult:
    """Runs ONE independent, real DK fetch for `provider_slate_id` (the
    DraftGroup id the legacy path already fetched and validated), with
    its own fresh, unshared cache so `capture` always fires against a
    real network call rather than a shared-cache hit -- "both paths may
    receive the same real fetch" (M2's architecture principle), each
    fetch fully real and independent. Captures RAW bytes, resolves DK
    identity against the existing MLB crosswalk (never fuzzy), and
    writes the NORMALIZED R2 artifact. Never raises -- see this module's
    own docstring."""
    try:
        storage = resolve_artifact_storage(ARTIFACT_ROOT)
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
        fetched_at = datetime.now(timezone.utc).isoformat()

        raw_result = write_raw_capture(
            storage, sport=sport, slate_date=date, provider=provider.name, provider_slate_id=provider_slate_id,
            recorder=recorder, fetched_at=fetched_at,
        )

        internal_slate_id_proposed = str(uuid.uuid4())
        name_team_index = load_name_team_index()
        artifact = build_canonical_artifact(
            sport=sport, site=site, provider=provider.name, slate_info=slate_info, provider_players=provider_players,
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
    except Exception as exc:  # noqa: BLE001 -- M2I: report, never let a shadow-path failure propagate
        return ShadowIngestionResult(
            ok=False, provider_slate_id=provider_slate_id,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}", error_type=type(exc).__name__,
        )
