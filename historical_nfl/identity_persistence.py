"""NFL M6B Phase 8 -- immutable-versioned-snapshot persistence for the
DK<->GSIS crosswalk, mirroring player_identity/persistence.py's exact
pattern (never overwrite a prior version; "latest" resolved by listing;
a microsecond-resolution timestamp + nonce so same-second writes never
collide).

Deliberate deviation from player_identity/persistence.py::merge_crosswalk:
that function always lets the newest observation win (correct for MLB's
"current_team" tracking, where drift is normal and expected). A DK<->GSIS
identity mapping is NOT supposed to drift -- Phase 8 explicitly requires
conflict detection instead: merging a new AUTO_APPROVED/REVIEWED_APPROVED
row whose gsis_id disagrees with an existing APPROVED row for the same
draftkings_player_id raises CrosswalkConflictError rather than silently
picking one."""

import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from research.artifact_storage import ARTIFACT_ROOT, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from historical_nfl.identity_models import REVIEW_AUTO_APPROVED, REVIEW_REVIEWED_APPROVED, CrosswalkConflictError, NflCrosswalkRow

DEFAULT_CROSSWALK_ROOT = Path(__file__).resolve().parent.parent / "historical" / "nfl" / "identity" / "crosswalk"

_APPROVED_STATES = (REVIEW_AUTO_APPROVED, REVIEW_REVIEWED_APPROVED)


def _microsecond_timestamp_tag(generated_at: str) -> str:
    dt = datetime.fromisoformat(generated_at)
    return dt.strftime("%Y%m%dT%H%M%S%f")


def _list_crosswalk_version_keys(output_root: Path) -> List[str]:
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    dir_key = to_artifact_key(Path(output_root))
    return storage.list_files(dir_key, prefix="nfl_crosswalk_", ext=".json")


def load_crosswalk(output_root: Path = DEFAULT_CROSSWALK_ROOT) -> Dict[str, NflCrosswalkRow]:
    """{draftkings_player_id: NflCrosswalkRow} from the latest version.
    Returns {} (never raises) when no version exists yet."""
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    versions = _list_crosswalk_version_keys(output_root)
    if not versions:
        return {}
    raw = storage.read_json(versions[-1])
    if not raw:
        return {}
    result: Dict[str, NflCrosswalkRow] = {}
    for record in raw.get("players", []):
        try:
            row = NflCrosswalkRow(**{k: v for k, v in record.items() if k in NflCrosswalkRow.__dataclass_fields__})
        except TypeError:
            continue
        if row.draftkings_player_id:
            result[row.draftkings_player_id] = row
    return result


def merge_crosswalk(existing: Dict[str, NflCrosswalkRow], new_rows: List[NflCrosswalkRow]) -> Dict[str, NflCrosswalkRow]:
    """Merges freshly-resolved rows into the existing crosswalk.

    - A brand-new draftkings_player_id is simply added.
    - A row matching an EXISTING APPROVED row's gsis_id (including both
      being None) is a no-op reaffirmation.
    - A row whose gsis_id DISAGREES with an existing APPROVED row's
      gsis_id for the same draftkings_player_id raises
      CrosswalkConflictError -- never silently overwritten.
    - A row for a draftkings_player_id whose existing entry is NOT yet
      approved (NEEDS_REVIEW) is freely replaced -- there is nothing
      "approved" yet to conflict with.
    """
    merged = dict(existing)
    for row in new_rows:
        if not row.draftkings_player_id:
            continue
        prior = merged.get(row.draftkings_player_id)
        if prior is not None and prior.review_status in _APPROVED_STATES:
            if prior.gsis_id != row.gsis_id:
                raise CrosswalkConflictError(
                    f"draftkings_player_id={row.draftkings_player_id!r}: existing approved gsis_id={prior.gsis_id!r} "
                    f"conflicts with newly resolved gsis_id={row.gsis_id!r} (name={row.name!r}). Never silently overwritten -- "
                    "resolve by human review before merging."
                )
            continue  # identical -- no-op reaffirmation, keep the existing row (preserves its original created_at)
        merged[row.draftkings_player_id] = row
    return merged


def save_crosswalk(records: Dict[str, NflCrosswalkRow], generated_at: str, output_root: Path = DEFAULT_CROSSWALK_ROOT) -> Path:
    ts = _microsecond_timestamp_tag(generated_at)
    nonce = secrets.token_hex(4)
    path = Path(output_root) / f"nfl_crosswalk_{ts}_{nonce}.json"
    document = {
        "generated_at": generated_at,
        "player_count": len(records),
        "players": [r.to_dict() for r in records.values()],
    }
    save_json(path, document)
    return path
