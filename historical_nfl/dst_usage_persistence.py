"""NFL M8 -- immutable persistence for NflDstUsageRecord snapshots.
Mirrors historical_nfl/usage_persistence.py's exact discipline, kept in
its own sibling path so DST (team-level) never collides with offensive
(player-level) usage snapshots.

    historical/nfl/normalized/dst_usage/{season}/{week}/
      nfl_dst_usage_<timestamp>.json
"""

from pathlib import Path
from typing import List, Optional

from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from historical_nfl.dst_usage_models import DST_SCHEMA_VERSION, NflDstUsageRecord

DEFAULT_DST_USAGE_ROOT = Path(__file__).resolve().parent.parent / "historical" / "nfl" / "normalized" / "dst_usage"


def save_dst_usage_snapshot(
    records: List[NflDstUsageRecord], season: int, week: int, timestamp: str,
    output_root: Path = DEFAULT_DST_USAGE_ROOT,
) -> Path:
    path = Path(output_root) / str(season) / str(week) / f"nfl_dst_usage_{timestamp}.json"
    raise_if_exists(path)
    document = {
        "sport": "NFL", "season": season, "week": week, "schema_version": DST_SCHEMA_VERSION,
        "row_count": len(records), "records": [r.to_dict() for r in records],
    }
    save_json(path, document)
    return path


def list_dst_usage_snapshots(season: int, week: int, output_root: Path = DEFAULT_DST_USAGE_ROOT) -> List[Path]:
    folder = Path(output_root) / str(season) / str(week)
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    keys = storage.list_files(to_artifact_key(folder), prefix="nfl_dst_usage_", ext=".json")
    return [ARTIFACT_ROOT / key for key in keys]


def load_latest_dst_usage_snapshot(season: int, week: int, output_root: Path = DEFAULT_DST_USAGE_ROOT) -> Optional[dict]:
    snapshots = list_dst_usage_snapshots(season, week, output_root)
    if not snapshots:
        return None
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    return storage.read_json(to_artifact_key(snapshots[-1]))
