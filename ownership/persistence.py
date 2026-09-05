"""Immutable, reproducible storage for one ownership projection run.
Mirrors dfs/persistence.py's and optimizer/persistence.py's save
discipline -- a new timestamped file every run, FileExistsError instead
of silent overwrite.

    ownership_predictions/
      YYYY-MM-DD/
        ownership_<timestamp>.json                 (no slate_id -- legacy/single-slate day)
        <slate_id>/
          ownership_<timestamp>.json                (Milestone 26 -- slate-scoped)

Milestone 26: ownership is estimated RELATIVE TO ONE SLATE's player pool
(see ownership/slate_normalization.py) -- when a date has more than one
real DraftKings slate (Main/Turbo/Night/...), each slate's ownership
projection is a DIFFERENT, independently-normalized document and must
never overwrite or be confused with another slate's. Passing `slate_id`
scopes both the save path and the document's own `slate_id` field;
omitting it preserves the exact pre-Milestone-26 date-only behavior, so
old artifacts written before this milestone remain readable by the same
functions (list_ownership_snapshots/load_latest_ownership_snapshot
degrade to "no slate scoping" exactly like they always have).

The document is structured so ACTUAL contest ownership can later be
joined by dk_player_id / mlb_player_id / slate_date (and a contest
identifier, once one exists) without rebuilding this snapshot -- see
the milestone's "Ownership Snapshot Evaluation Foundation" note. No
evaluator is built yet; this only preserves enough provenance for one
to exist later.
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

# Reuses the exact same UTC/local/timezone metadata helper the Pitcher,
# Batter, and lineup-set outputs already use (America/Chicago,
# tzdata-backed) instead of re-deriving the same logic a fourth time.
from research.artifact_storage import ARTIFACT_ROOT, resolve_artifact_storage, to_artifact_key
from research.prediction_snapshot import _timezone_metadata
from research.storage import save_json

from ownership.models import OwnershipProjection, TeamPopularity

DEFAULT_OWNERSHIP_ROOT = Path(__file__).resolve().parent.parent / "ownership_predictions"

# MLB FILE LOCK / DUPLICATE ARTIFACT WRITER RACE: real production
# incident (2026-09-05) -- two duplicate orphaned refresh processes (see
# the separate worker-orphan-hardening fix; that fix is the actual root
# cause remedy, this is defense in depth for the artifact writer itself)
# computed ownership for the SAME slate within the SAME wall-clock
# second, both passing a naive path.exists()-then-write check before
# either had written -- confirmed live: the second writer's
# save_ownership_document() raised FileExistsError, correctly refusing
# to overwrite, but a slightly different timing could equally have let
# it silently clobber the first writer's real data instead (a plain
# "check, then write with overwrite allowed" has no ordering guarantee
# either way). timestamp_tag() is SECOND resolution by design (matches
# every other immutable snapshot in this project) -- not the actual
# defect; the defect is relying on a non-atomic existence check as the
# ONLY thing standing between two writers and the SAME key.
#
# Fix: the persisted filename itself now includes a deterministic
# content hash (never a random/run-ID suffix -- "do not introduce
# random naming if a deterministic content hash is cleaner"). Two
# writers computing the SAME real ownership result (the actual race
# above) now derive the IDENTICAL key -- so even if both pass the
# existence check and both write, they write byte-for-byte identical
# JSON to the identical key, which is a true no-op duplicate, never
# corruption, never data loss. Two writers computing GENUINELY
# DIFFERENT content (a real distinct result) now land at DIFFERENT
# keys by construction -- no collision is even possible, so nothing is
# ever silently overwritten. This is the SAME "does the new artifact
# differ from the last one" question canonical_ingestion's own
# isSemanticDuplicate/normalizedHash mechanism already answers for
# canonical slate artifacts -- reused here as the identical concept for
# a different artifact type, not a new idea.
_VOLATILE_OWNERSHIP_FIELDS = frozenset({"generated_at", "generated_at_utc", "generated_at_local"})


def _content_hash(document: dict) -> str:
    """Deterministic SHA-256 (first 12 hex chars -- short but still
    collision-resistant enough for this project's real slate sizes,
    matching canonical/hashing.py's own precedent of truncating a full
    hex digest for a filename-safe tag) over the document's REAL,
    stable content -- excludes only the per-run generation timestamps,
    never any field that reflects an actual computed result (player
    ownership values, team popularity, model_version, slate identity).
    Two independent computations of the SAME underlying inputs must
    hash identically; two computations of DIFFERENT inputs must not."""
    stable = {k: v for k, v in document.items() if k not in _VOLATILE_OWNERSHIP_FIELDS}
    canonical = json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _exists(path: Path) -> bool:
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    return storage.exists(to_artifact_key(path))


def build_ownership_document(
    slate_date: str, generated_at_utc: str, model_version: str, pool_path: str,
    pitcher_snapshot_path: Optional[str], batter_snapshot_path: Optional[str],
    projections: List[OwnershipProjection], team_popularity: Dict[str, TeamPopularity],
    normalization_report: dict, slate_id: Optional[str] = None,
) -> dict:
    return {
        "slate_date": slate_date,
        "slate_id": slate_id,
        "generated_at": generated_at_utc,
        **_timezone_metadata(generated_at_utc),
        "model_version": model_version,
        "source_dk_player_pool_path": str(pool_path),
        "pitcher_snapshot_reference": pitcher_snapshot_path,
        "batter_snapshot_reference": batter_snapshot_path,
        "player_count": len(projections),
        "players": [p.to_dict() for p in projections],
        "team_popularity": {team: stats.to_dict() for team, stats in team_popularity.items()},
        "normalization_checks": normalization_report,
    }


def _slate_folder(output_root: Path, slate_date: str, slate_id: Optional[str]) -> Path:
    folder = Path(output_root) / slate_date
    return folder / slate_id if slate_id else folder


def save_ownership_document(
    document: dict, slate_date: str, timestamp: str, output_root: Path = DEFAULT_OWNERSHIP_ROOT, slate_id: Optional[str] = None,
) -> Path:
    """Immutable, content-hash-qualified snapshot filename -- see this
    module's own top-of-file note on the real production race this
    replaced. If the exact same (timestamp, content) pair already
    exists, this is an idempotent duplicate (e.g. a retried/duplicate
    writer computing the identical real result): returns the existing
    path without writing again, never raises. A genuinely different
    result for the same timestamp lands at a different key -- no
    collision, both persisted, immutable history preserved."""
    content_hash = _content_hash(document)
    path = _slate_folder(output_root, slate_date, slate_id) / f"ownership_{timestamp}_{content_hash}.json"
    if _exists(path):
        return path
    save_json(path, document)
    return path


def list_ownership_snapshots(slate_date: str, output_root: Path = DEFAULT_OWNERSHIP_ROOT, slate_id: Optional[str] = None) -> List[Path]:
    folder = _slate_folder(output_root, slate_date, slate_id)
    if not folder.exists():
        return []
    return sorted(folder.glob("ownership_*.json"))


def load_latest_ownership_snapshot(slate_date: str, output_root: Path = DEFAULT_OWNERSHIP_ROOT, slate_id: Optional[str] = None) -> dict:
    import json
    snapshots = list_ownership_snapshots(slate_date, output_root, slate_id=slate_id)
    if not snapshots:
        scope = f"slate {slate_id!r} on {slate_date}" if slate_id else slate_date
        raise FileNotFoundError(f"No ownership snapshots found for {scope} under {output_root}/")
    with snapshots[-1].open("r", encoding="utf-8") as f:
        return json.load(f)
