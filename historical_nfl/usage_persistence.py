"""NFL M6C Phase 4 -- immutable persistence for normalized NflUsageRecord
snapshots, separate from M6A's raw snapshots (never overwrites or
touches historical/nfl/raw/nflverse/...).

    historical/nfl/normalized/usage/{season}/{week}/
      nfl_usage_<timestamp>.json
"""

from pathlib import Path
from typing import List, Optional

from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from historical_nfl.usage_models import SCHEMA_VERSION, NflUsageRecord

DEFAULT_NORMALIZED_USAGE_ROOT = Path(__file__).resolve().parent.parent / "historical" / "nfl" / "normalized" / "usage"


def save_usage_snapshot(
    records: List[NflUsageRecord], season: int, week: int, timestamp: str,
    output_root: Path = DEFAULT_NORMALIZED_USAGE_ROOT,
) -> Path:
    path = Path(output_root) / str(season) / str(week) / f"nfl_usage_{timestamp}.json"
    raise_if_exists(path)
    document = {
        "sport": "NFL", "season": season, "week": week, "schema_version": SCHEMA_VERSION,
        "row_count": len(records), "records": [r.to_dict() for r in records],
    }
    save_json(path, document)
    return path


def list_usage_snapshots(season: int, week: int, output_root: Path = DEFAULT_NORMALIZED_USAGE_ROOT) -> List[Path]:
    folder = Path(output_root) / str(season) / str(week)
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    keys = storage.list_files(to_artifact_key(folder), prefix="nfl_usage_", ext=".json")
    return [ARTIFACT_ROOT / key for key in keys]


def load_latest_usage_snapshot(season: int, week: int, output_root: Path = DEFAULT_NORMALIZED_USAGE_ROOT) -> Optional[dict]:
    snapshots = list_usage_snapshots(season, week, output_root)
    if not snapshots:
        return None
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    return storage.read_json(to_artifact_key(snapshots[-1]))
