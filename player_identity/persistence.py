"""Persistence for the canonical MLB player identity crosswalk.

Two distinct artifacts, BOTH immutable, timestamped snapshots -- the
rolling crosswalk was, until Milestone 33.2, the single mutable
read-modify-overwrite shared file Milestone 33.0's audit identified as
the highest concurrency/data-integrity risk in this codebase (two
refreshes racing on the same file could silently clobber one another's
additions, and once object storage replaces local disk there is no
portable atomic-overwrite primitive to rely on across S3-compatible
providers). Milestone 33.2 converts it to the same
immutable-versioned-snapshot + latest-by-listing pattern already used by
every other artifact in this project:

1. player_identity_snapshots/<date>/identity_refresh_<timestamp>.json
   -- raw audit record of what one refresh actually observed.

2. player_identity_crosswalk/crosswalk_<timestamp>_<nonce>.json
   -- the accumulated, best-known identity for every player ever
   observed by a refresh, keyed by mlb_player_id. Every refresh reads
   the LATEST existing version, merges in its own fresh observations
   (see merge_crosswalk), and writes a NEW versioned file. It never
   overwrites a prior version.

   The `<nonce>` suffix exists specifically so two refreshes racing in
   the same second each get a distinct filename instead of one raising
   FileExistsError against the other -- both versions are preserved
   rather than one being lost or a writer being forced into a retry
   loop.

   Concurrency note: if two refreshes both read version N and each
   writes their own successor (N+1a, N+1b), whichever version a later
   reader doesn't pick as "latest" is not lost -- it stays on disk/in
   the bucket, and any identity additions unique to it reappear
   automatically the next time a refresh re-observes the same players
   from the live roster fetch (this crosswalk is a cache of
   re-derivable observations, not the sole source of truth for
   identity -- see player_identity/refresh.py). This is a documented,
   low-consequence residual race, not full mutual exclusion. Full
   exclusion would require either a Postgres row lock (a new
   Python-to-Postgres dependency this milestone deliberately avoids
   adding -- see the M33.2 final report's Part 9 discussion) or S3
   conditional-write semantics that are not portably guaranteed across
   S3-compatible providers -- both out of scope for storage
   infrastructure alone.
"""

import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from player_identity.models import CanonicalIdentity

DEFAULT_IDENTITY_SNAPSHOT_ROOT = Path(__file__).resolve().parent.parent / "player_identity_snapshots"
DEFAULT_CROSSWALK_ROOT = Path(__file__).resolve().parent.parent / "player_identity_crosswalk"

# Milestone 33.2: a crosswalk written before this migration lived at a
# single fixed "canonical_crosswalk.json" file inside its output_root,
# overwritten on every refresh. load_crosswalk() falls back to reading
# that file (relative to whichever output_root it was called with, not
# always the default -- so an isolated/test output_root never sees the
# real project's legacy file) so it isn't silently lost.
_LEGACY_CROSSWALK_FILENAME = "canonical_crosswalk.json"


def _microsecond_timestamp_tag(generated_at: str) -> str:
    """'2026-08-11T16:55:00.123456+00:00' -> '20260811T165500123456' --
    same fixed-width, filesystem-safe, lexicographically-sortable shape
    as research/prediction_snapshot.py's timestamp_tag(), extended to
    microsecond resolution (see save_crosswalk's docstring for why)."""
    dt = datetime.fromisoformat(generated_at)
    return dt.strftime("%Y%m%dT%H%M%S%f")


def _no_overwrite(path: Path) -> None:
    # Milestone 33.2: storage-aware (see bluecollar/persistence.py's
    # identical comment for why this replaced a local path.exists() check).
    raise_if_exists(path)


def save_identity_refresh_snapshot(document: dict, slate_date: str, timestamp: str, output_root: Path = DEFAULT_IDENTITY_SNAPSHOT_ROOT) -> Path:
    path = Path(output_root) / slate_date / f"identity_refresh_{timestamp}.json"
    _no_overwrite(path)
    save_json(path, document)
    return path


def _list_crosswalk_version_keys(output_root: Path = DEFAULT_CROSSWALK_ROOT) -> List[str]:
    """Object-storage keys of every crosswalk version, ascending
    (oldest first) -- filenames sort chronologically since the timestamp
    prefix is fixed-width and left-to-right significant, same as every
    other snapshot family in this project."""
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    dir_key = to_artifact_key(Path(output_root))
    return storage.list_files(dir_key, prefix="crosswalk_", ext=".json")


def load_crosswalk(path: Optional[Path] = None, output_root: Path = DEFAULT_CROSSWALK_ROOT) -> Dict[str, CanonicalIdentity]:
    """{mlb_player_id: CanonicalIdentity} from the latest crosswalk
    version. Returns {} (never raises) when no version exists yet -- a
    first-ever refresh has nothing to load, which is a normal, expected
    state, not an error.

    `path`, when given explicitly, loads exactly that one version file
    (used by tests, and by anything auditing a specific past version)
    instead of resolving "latest"."""
    storage = resolve_artifact_storage(ARTIFACT_ROOT)

    if path is not None:
        return _parse_crosswalk_document(storage.read_json(to_artifact_key(Path(path))))

    versions = _list_crosswalk_version_keys(output_root)
    if versions:
        return _parse_crosswalk_document(storage.read_json(versions[-1]))

    legacy_path = Path(output_root) / _LEGACY_CROSSWALK_FILENAME
    return _parse_crosswalk_document(storage.read_json(to_artifact_key(legacy_path)))


def _parse_crosswalk_document(raw: Optional[dict]) -> Dict[str, CanonicalIdentity]:
    if not raw:
        return {}
    result: Dict[str, CanonicalIdentity] = {}
    for record in raw.get("players", []):
        try:
            result[record["mlb_player_id"]] = CanonicalIdentity(**{
                k: v for k, v in record.items() if k in CanonicalIdentity.__dataclass_fields__
            })
        except (KeyError, TypeError):
            continue
    return result


def save_crosswalk(records: Dict[str, CanonicalIdentity], generated_at: str, output_root: Path = DEFAULT_CROSSWALK_ROOT) -> Path:
    """Writes a NEW versioned crosswalk file -- never overwrites a prior
    version (see module docstring for the concurrency reasoning).

    Unlike every other snapshot family in this project (which use
    timestamp_tag()'s second-resolution filenames, safe because those
    are one-per-run artifacts), the crosswalk can plausibly be refreshed
    more than once per second by an automated pipeline -- "latest by
    listing" needs the filename ordering to reflect real write order at
    that resolution, so this uses microsecond resolution instead. The
    trailing nonce still exists for the (now even more remote) case of
    two writes landing in the exact same microsecond."""
    ts = _microsecond_timestamp_tag(generated_at)
    nonce = secrets.token_hex(4)
    path = Path(output_root) / f"crosswalk_{ts}_{nonce}.json"
    document = {
        "generated_at": generated_at,
        "player_count": len(records),
        "players": [r.to_dict() for r in records.values()],
    }
    save_json(path, document)
    return path


def merge_crosswalk(existing: Dict[str, CanonicalIdentity], new_records: List[CanonicalIdentity]) -> Dict[str, CanonicalIdentity]:
    """Merges freshly-fetched identities into the existing rolling
    crosswalk. A player seen in `new_records` always overwrites their
    prior entry (the newest live roster fetch is always the most
    authoritative source for current_team -- see this module's own
    docstring); a player NOT re-observed today simply keeps their prior,
    still-useful entry rather than being dropped."""
    merged = dict(existing)
    for record in new_records:
        merged[record.mlb_player_id] = record
    return merged
