"""Immutable, reproducible storage for one ownership projection run.
Mirrors dfs/persistence.py's and optimizer/persistence.py's save
discipline -- a new timestamped file every run, FileExistsError instead
of silent overwrite.

    ownership_predictions/
      YYYY-MM-DD/
        ownership_<timestamp>.json

The document is structured so ACTUAL contest ownership can later be
joined by dk_player_id / mlb_player_id / slate_date (and a contest
identifier, once one exists) without rebuilding this snapshot -- see
the milestone's "Ownership Snapshot Evaluation Foundation" note. No
evaluator is built yet; this only preserves enough provenance for one
to exist later.
"""

from pathlib import Path
from typing import Dict, List, Optional

# Reuses the exact same UTC/local/timezone metadata helper the Pitcher,
# Batter, and lineup-set outputs already use (America/Chicago,
# tzdata-backed) instead of re-deriving the same logic a fourth time.
from research.prediction_snapshot import _timezone_metadata
from research.storage import save_json

from ownership.models import OwnershipProjection, TeamPopularity

DEFAULT_OWNERSHIP_ROOT = Path(__file__).resolve().parent.parent / "ownership_predictions"


def _no_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing ownership snapshot: {path}")


def build_ownership_document(
    slate_date: str, generated_at_utc: str, model_version: str, pool_path: str,
    pitcher_snapshot_path: Optional[str], batter_snapshot_path: Optional[str],
    projections: List[OwnershipProjection], team_popularity: Dict[str, TeamPopularity],
    normalization_report: dict,
) -> dict:
    return {
        "slate_date": slate_date,
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


def save_ownership_document(document: dict, slate_date: str, timestamp: str, output_root: Path = DEFAULT_OWNERSHIP_ROOT) -> Path:
    path = Path(output_root) / slate_date / f"ownership_{timestamp}.json"
    _no_overwrite(path)
    save_json(path, document)
    return path


def list_ownership_snapshots(slate_date: str, output_root: Path = DEFAULT_OWNERSHIP_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date
    if not folder.exists():
        return []
    return sorted(folder.glob("ownership_*.json"))


def load_latest_ownership_snapshot(slate_date: str, output_root: Path = DEFAULT_OWNERSHIP_ROOT) -> dict:
    import json
    snapshots = list_ownership_snapshots(slate_date, output_root)
    if not snapshots:
        raise FileNotFoundError(f"No ownership snapshots found for {slate_date} under {output_root}/")
    with snapshots[-1].open("r", encoding="utf-8") as f:
        return json.load(f)
