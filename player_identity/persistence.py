"""Persistence for the canonical MLB player identity crosswalk.

Two distinct artifacts, deliberately different lifecycles:

1. An IMMUTABLE, timestamped audit snapshot per refresh
   (player_identity_snapshots/<date>/identity_refresh_<timestamp>.json)
   -- mirrors bluecollar/persistence.py's no-overwrite discipline, so
   "what did the refresh actually see on this date" is always
   reproducible.

2. A single MUTABLE, rolling crosswalk file
   (player_identity_crosswalk/canonical_crosswalk.json) -- the
   accumulated, best-known identity for every player ever observed by a
   refresh, keyed by mlb_player_id. This one IS overwritten on every
   refresh (that's the point: "Persist the crosswalk so subsequent
   refreshes can reuse known MLB IDs" -- a team whose roster fetch fails
   on a given day still has its most-recently-known identities
   available rather than losing them for the day).
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from research.storage import save_json

from player_identity.models import CanonicalIdentity

DEFAULT_IDENTITY_SNAPSHOT_ROOT = Path(__file__).resolve().parent.parent / "player_identity_snapshots"
DEFAULT_CROSSWALK_PATH = Path(__file__).resolve().parent.parent / "player_identity_crosswalk" / "canonical_crosswalk.json"


def _no_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing identity refresh snapshot: {path}")


def save_identity_refresh_snapshot(document: dict, slate_date: str, timestamp: str, output_root: Path = DEFAULT_IDENTITY_SNAPSHOT_ROOT) -> Path:
    path = Path(output_root) / slate_date / f"identity_refresh_{timestamp}.json"
    _no_overwrite(path)
    save_json(path, document)
    return path


def load_crosswalk(path: Path = DEFAULT_CROSSWALK_PATH) -> Dict[str, CanonicalIdentity]:
    """{mlb_player_id: CanonicalIdentity} from the rolling crosswalk
    file. Returns {} (never raises) when the file doesn't exist yet or
    is unreadable -- a first-ever refresh has nothing to load, which is
    a normal, expected state, not an error."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
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


def save_crosswalk(records: Dict[str, CanonicalIdentity], generated_at: str, path: Path = DEFAULT_CROSSWALK_PATH) -> Path:
    path = Path(path)
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
