"""NFL M8 -- immutable persistence for NflProjectionFeatures snapshots
(the DK-identity-joined feature record a future projection model would
consume). Mirrors historical_nfl/usage_persistence.py's exact
discipline.

    historical/nfl/features/{season}/{week}/
      nfl_projection_features_<timestamp>.json
"""

from pathlib import Path
from typing import List, Optional

from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from nfl.projection_features import NflProjectionFeatures

DEFAULT_FEATURES_ROOT = Path(__file__).resolve().parent.parent / "historical" / "nfl" / "features"


def save_projection_features_snapshot(
    features: List[NflProjectionFeatures], season: int, week: int, timestamp: str,
    output_root: Path = DEFAULT_FEATURES_ROOT,
) -> Path:
    path = Path(output_root) / str(season) / str(week) / f"nfl_projection_features_{timestamp}.json"
    raise_if_exists(path)
    document = {
        "sport": "NFL", "season": season, "week": week,
        "row_count": len(features), "features": [f.to_dict() for f in features],
    }
    save_json(path, document)
    return path


def list_projection_features_snapshots(season: int, week: int, output_root: Path = DEFAULT_FEATURES_ROOT) -> List[Path]:
    folder = Path(output_root) / str(season) / str(week)
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    keys = storage.list_files(to_artifact_key(folder), prefix="nfl_projection_features_", ext=".json")
    return [ARTIFACT_ROOT / key for key in keys]


def load_latest_projection_features_snapshot(season: int, week: int, output_root: Path = DEFAULT_FEATURES_ROOT) -> Optional[dict]:
    snapshots = list_projection_features_snapshots(season, week, output_root)
    if not snapshots:
        return None
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    return storage.read_json(to_artifact_key(snapshots[-1]))
