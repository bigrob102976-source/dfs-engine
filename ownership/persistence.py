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

from pathlib import Path
from typing import Dict, List, Optional

# Reuses the exact same UTC/local/timezone metadata helper the Pitcher,
# Batter, and lineup-set outputs already use (America/Chicago,
# tzdata-backed) instead of re-deriving the same logic a fourth time.
from research.artifact_storage import raise_if_exists
from research.prediction_snapshot import _timezone_metadata
from research.storage import save_json

from ownership.models import OwnershipProjection, TeamPopularity

DEFAULT_OWNERSHIP_ROOT = Path(__file__).resolve().parent.parent / "ownership_predictions"


def _no_overwrite(path: Path) -> None:
    # Milestone 33.2: storage-aware (see bluecollar/persistence.py's
    # identical comment for why this replaced a local path.exists() check).
    raise_if_exists(path)


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
    path = _slate_folder(output_root, slate_date, slate_id) / f"ownership_{timestamp}.json"
    _no_overwrite(path)
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
