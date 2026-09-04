"""Break-glass admin DraftKings CSV import -- canonical normalization.

Mirrors canonical_ingestion/normalize.py::build_canonical_artifact for the
ONE way it must genuinely differ: that function derives slateDate from
real per-game start instants (canonical/slate_date.py), because the live
DraftKings Unofficial provider always supplies them. A DraftKings CSV
export's "Game Info" column ("NYY@BOS 09/04/2026 07:05PM ET") is real DK
data but not a reliably machine-parseable timezone-aware instant --
dfs/draftkings_parser.py deliberately never attempts to parse one, and
dfs/providers/draftkings_csv_provider.py always sets ProviderPlayer.start_time
to None as a result. Guessing one here to satisfy compute_slate_date_from_game_starts
would violate this project's anti-fabrication rule.

Instead: an admin CSV import always carries an EXPLICIT, admin-supplied
`slate_date` (the same date field the existing upload form already
collects) -- a real, human-confirmed fact about which real calendar day's
slate this is, never derived/guessed. `first_game_start_utc` (a REQUIRED
field on CanonicalSlate, documented elsewhere as "the real instant
slateDate was derived from") is honestly NOT that for this source --
it's set to the import's own real processing timestamp instead, and this
is called out explicitly wherever it's read (see this module's own
`ADMIN_CSV_FIRST_GAME_START_NOTE`) so nothing downstream can mistake it
for a genuine first-pitch time.

Reuses every other real canonical building block unchanged: identity
resolution (canonical_ingestion/identity_bridge.py), the CanonicalSlate/
CanonicalSlatePlayer/CanonicalSlateArtifact models, and normalizedHash
hashing -- this is not a parallel/second canonical format, only a
different slateDate/firstGameStartUtc INPUT for the one genuinely
CSV-specific gap.
"""

from __future__ import annotations

import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from canonical.hashing import compute_normalized_hash
from canonical.models import (
    IDENTITY_STATUS_RESOLVED,
    IDENTITY_STATUS_REVIEW_REQUIRED,
    IDENTITY_STATUS_UNRESOLVED,
    CanonicalSlate,
    CanonicalSlateArtifact,
    CanonicalSlatePlayer,
    VALIDATION_STATE_REJECTED,
    VALIDATION_STATE_VALID,
    slate_player_from_provider_player,
)
from canonical.schema_version import CURRENT_SLATE_SCHEMA_VERSION
from canonical_ingestion.identity_bridge import NameTeamIndex, load_name_team_index, resolve_dk_player
from canonical_ingestion.normalized_storage import write_normalized_artifact
from canonical_ingestion.pipeline import ShadowIngestionResult
from canonical_ingestion.raw_capture import RawCaptureRecorder, write_raw_capture
from dfs.providers.source_provenance import TRUSTED_FOR_PRODUCTION
from research.artifact_storage import ARTIFACT_ROOT, resolve_artifact_storage

# Recorded verbatim into validation_findings on every admin-CSV artifact
# (never silently -- see build_canonical_artifact_from_admin_csv below),
# so this honest caveat travels with the data all the way to canonical
# Postgres's own validation_findings_json column, not just this module's
# docstring.
ADMIN_CSV_FIRST_GAME_START_NOTE = (
    "firstGameStartUtc is NOT a real first-pitch time for this slate -- DraftKings CSV exports do not "
    "reliably expose one in machine-parseable form. It is the timestamp this admin CSV import was processed. "
    "slateDate itself is real: the calendar date the uploading admin explicitly specified."
)


class AdminCsvNormalizationError(ValueError):
    """Raised when an admin CSV import cannot be honestly normalized --
    never falls back to a fabricated value."""


def build_canonical_artifact_from_admin_csv(
    *, sport: str, site: str, provider: str, slate_info, provider_players: List, internal_slate_id: str,
    slate_date: str, raw_hash: Optional[str], name_team_index: NameTeamIndex, fetched_at: Optional[str] = None,
) -> CanonicalSlateArtifact:
    """`slate_info`/`provider_players` are dfs/providers/models.py's
    ProviderSlateInfo/ProviderPlayer, exactly as DraftKingsCsvProvider.get_slate()
    already returns them (real DK CSV data, already structurally
    validated by dfs/draftkings_parser.py and content-realism-checked by
    dfs/providers/source_realism.py). `slate_date` is the admin's own
    explicit YYYY-MM-DD input -- the caller (scripts/import_dk_csv_to_canonical.py)
    is responsible for having validated its shape; this function does not
    re-validate it, only refuses an empty value."""
    if not slate_date:
        raise AdminCsvNormalizationError("slate_date is required for an admin CSV import -- refusing to fabricate one.")
    if not provider_players:
        raise AdminCsvNormalizationError(
            f"No players available for {provider}:{slate_info.slate_id} -- refusing to promote an empty slate."
        )

    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()

    validation_state = VALIDATION_STATE_VALID if slate_info.source_provenance in TRUSTED_FOR_PRODUCTION else VALIDATION_STATE_REJECTED
    validation_findings = [ADMIN_CSV_FIRST_GAME_START_NOTE, *slate_info.realism_findings]

    canonical_slate = CanonicalSlate(
        internal_slate_id=internal_slate_id, sport=sport, site=site, provider=provider,
        provider_slate_id=slate_info.slate_id, slate_name=slate_info.slate_name, slate_date=slate_date,
        first_game_start_utc=fetched_at, game_count=slate_info.game_count,
        game_ids=list(slate_info.game_ids), source_provenance=slate_info.source_provenance,
        validation_state=validation_state, validation_findings=validation_findings, fetched_at=fetched_at,
    )

    slate_players: List[CanonicalSlatePlayer] = []
    identity_matches: Dict[str, Dict[str, Any]] = {}
    for provider_player in provider_players:
        match = resolve_dk_player(provider_player, name_team_index)
        slate_player = slate_player_from_provider_player(provider_player, internal_slate_id=internal_slate_id)
        slate_player.identity_status = match.identity_status
        slate_players.append(slate_player)
        identity_matches[provider_player.external_player_id] = match.to_dict()

    artifact = CanonicalSlateArtifact(
        slate=canonical_slate, players=slate_players, raw_hash=raw_hash, schema_version=CURRENT_SLATE_SCHEMA_VERSION,
        identity_matches=identity_matches,
    )
    artifact.normalized_hash = compute_normalized_hash(canonical_slate.to_dict(), [p.to_dict() for p in slate_players])
    return artifact


def build_normalized_from_admin_csv(
    *, sport: str, site: str, provider: str, slate_info, provider_players: List, slate_date: str,
    original_filename: str, csv_text: str, fetched_at: Optional[str] = None,
) -> ShadowIngestionResult:
    """Admin-CSV equivalent of canonical_ingestion/pipeline.py's
    build_normalized_from_fetch(): real bytes in (the admin's own
    uploaded CSV, byte-exact, via the same RAW-capture machinery real DK
    fetches use -- see raw_capture.py's own honesty note) through a
    written NORMALIZED artifact out. Never raises -- every failure mode
    is reported in the returned ShadowIngestionResult, matching that
    function's own failure-isolation contract, because this always runs
    AFTER dfs.providers.draftkings_csv_storage.save_upload() has already
    durably saved the upload; a normalization failure here must never
    look like the upload itself failed.

    `slate_info`/`provider_players` come from
    dfs.providers.draftkings_csv_provider.DraftKingsCsvProvider.get_slate()
    -- already real, already structurally validated, already
    realism-checked. `csv_text` is the exact text of the uploaded file
    (read back from wherever save_upload() wrote it), captured RAW
    verbatim -- this module never re-serializes a parsed representation
    as if it were the raw upload."""
    try:
        storage = resolve_artifact_storage(ARTIFACT_ROOT)
        fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()

        recorder = RawCaptureRecorder()
        recorder.record(f"admin-csv-upload://{original_filename}", csv_text)

        raw_result = write_raw_capture(
            storage, sport=sport, slate_date=slate_date, provider=provider, provider_slate_id=slate_info.slate_id,
            recorder=recorder, fetched_at=fetched_at,
        )

        internal_slate_id_proposed = str(uuid.uuid4())
        name_team_index = load_name_team_index()
        artifact = build_canonical_artifact_from_admin_csv(
            sport=sport, site=site, provider=provider, slate_info=slate_info, provider_players=provider_players,
            internal_slate_id=internal_slate_id_proposed, slate_date=slate_date, raw_hash=raw_result.raw_hash,
            name_team_index=name_team_index, fetched_at=fetched_at,
        )

        write_result = write_normalized_artifact(storage, artifact)

        statuses = [p.identity_status for p in artifact.players]
        return ShadowIngestionResult(
            ok=True,
            provider_slate_id=slate_info.slate_id,
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
    except Exception as exc:  # noqa: BLE001 -- mirrors build_normalized_from_fetch's own failure-isolation contract
        return ShadowIngestionResult(
            ok=False, provider_slate_id=getattr(slate_info, "slate_id", None),
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}", error_type=type(exc).__name__,
        )
