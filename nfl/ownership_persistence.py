"""NFL M12 -- immutable, timestamped persistence for Big Money Native
NFL ownership snapshots. Mirrors nfl/projection_persistence.py's exact
discipline -- new file every save, FileExistsError instead of silent
clobber, routed through research/storage.py's save_json.

Sport-isolated path, never colliding with MLB ownership or NFL
projections:

    ownership_predictions/nfl/
      YYYY-MM-DD/
        {draft_group_id}/
          nfl_ownership_<timestamp>.json

NFL M12 scope: local disk only -- no production R2 writes.
"""

from pathlib import Path
from typing import List, Optional

from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from nfl.ownership_models import NflOwnershipSnapshot

DEFAULT_NFL_OWNERSHIP_ROOT = Path(__file__).resolve().parent.parent / "ownership_predictions" / "nfl"


def save_nfl_ownership_snapshot(snapshot: NflOwnershipSnapshot, timestamp: str, output_root: Path = DEFAULT_NFL_OWNERSHIP_ROOT) -> Path:
    path = Path(output_root) / snapshot.slate_date / str(snapshot.draft_group_id) / f"nfl_ownership_{timestamp}.json"
    raise_if_exists(path)
    save_json(path, snapshot.to_dict())
    return path


def list_nfl_ownership_snapshots(slate_date: str, draft_group_id: int, output_root: Path = DEFAULT_NFL_OWNERSHIP_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date / str(draft_group_id)
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    keys = storage.list_files(to_artifact_key(folder), prefix="nfl_ownership_", ext=".json")
    return [ARTIFACT_ROOT / key for key in keys]


def load_latest_nfl_ownership_snapshot(slate_date: str, draft_group_id: int, output_root: Path = DEFAULT_NFL_OWNERSHIP_ROOT) -> Optional[dict]:
    snapshots = list_nfl_ownership_snapshots(slate_date, draft_group_id, output_root)
    if not snapshots:
        return None
    path = snapshots[-1]
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    return storage.read_json(to_artifact_key(path))
