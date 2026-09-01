"""M2F -- canonical NORMALIZED R2 artifact storage.

Writes CanonicalSlateArtifact (canonical/models.py) as an immutable,
timestamped, never-overwritten object under:

    normalized/{sport}/{slateDate}/{provider}/{providerSlateId}/{timestamp}.json

DESIGN CHOICE -- semantic duplicates (documented per M2F's explicit
"choose the cleaner approach and document it" instruction): this module
RETAINS every capture (never skips a write) but marks a new artifact
with `isSemanticDuplicate: true` + `duplicateOfKey` when its
normalizedHash matches the immediately preceding artifact for the same
provider slate. Chosen over skipping the write because:
  1. it matches this codebase's dominant existing convention -- EVERY
     other snapshot family here (provider_slate_*.json, native/AI
     projection snapshots, identity crosswalk versions, ...) is an
     always-append, immutable, timestamped history; none of them skip a
     write merely because content matches the prior version.
  2. an unbroken, always-appended history is itself useful evidence
     ("we re-fetched at 14:32 and confirmed nothing changed") --
     skipping the write would silently lose proof the pipeline ran.
  3. these are small JSON artifacts; the storage cost of retaining
     semantic duplicates is negligible.
Downstream consumers (the Postgres promotion step) are the ones that
actually act on `isSemanticDuplicate` to avoid unnecessary work (M2G
rule 10), not this storage layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from canonical.models import CanonicalSlateArtifact
from research.artifact_storage import ArtifactStorage


def _timestamp_tag(fetched_at: str) -> str:
    dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    return dt.strftime("%Y%m%dT%H%M%S%f")


def normalized_base_dir(sport: str, slate_date: str, provider: str, provider_slate_id: str) -> str:
    return f"normalized/{sport}/{slate_date}/{provider}/{provider_slate_id}"


def find_latest_normalized(storage: ArtifactStorage, sport: str, slate_date: str, provider: str, provider_slate_id: str) -> Optional[Dict[str, Any]]:
    """Best-effort lookup of the most recently written NORMALIZED
    artifact for this exact provider slate (by filename/timestamp
    ordering, same "list and take the newest" convention as every other
    artifact family in this project). Returns None, never raises, if
    none exists yet. The returned dict includes its own storage key
    under "_key" so callers can trace a semantic-duplicate back to it."""
    directory = normalized_base_dir(sport, slate_date, provider, provider_slate_id)
    try:
        keys = storage.list_files(directory, prefix="", ext=".json")
    except Exception:  # noqa: BLE001
        return None
    if not keys:
        return None
    latest_key = sorted(keys)[-1]
    document = storage.read_json(latest_key)
    if document is None:
        return None
    document = dict(document)
    document["_key"] = latest_key
    return document


def write_normalized_artifact(storage: ArtifactStorage, artifact: CanonicalSlateArtifact) -> Dict[str, Any]:
    """Writes `artifact` immutably, marking it as a semantic duplicate of
    the immediately preceding artifact (same provider slate) when its
    normalizedHash is unchanged. Returns a dict with the written key and
    duplicate-detection outcome -- never mutates `artifact` itself."""
    slate = artifact.slate
    previous = find_latest_normalized(storage, slate.sport, slate.slate_date, slate.provider, slate.provider_slate_id)
    is_duplicate = bool(previous) and previous.get("normalizedHash") == artifact.normalized_hash

    document = artifact.to_dict()
    document["isSemanticDuplicate"] = is_duplicate
    document["duplicateOfKey"] = previous.get("_key") if (is_duplicate and previous) else None

    ts = _timestamp_tag(slate.fetched_at or "1970-01-01T00:00:00Z")
    key = f"{normalized_base_dir(slate.sport, slate.slate_date, slate.provider, slate.provider_slate_id)}/{ts}.json"
    storage.write_json(key, document, allow_overwrite=False)

    return {"key": key, "isSemanticDuplicate": is_duplicate, "normalizedHash": artifact.normalized_hash}
