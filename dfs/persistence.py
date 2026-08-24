"""Immutable, reproducible storage for one DraftKings import: an exact
copy of the raw CSV, the normalized player pool, and the match report --
all timestamped, never overwritten. Mirrors research/prediction_snapshot.py's
save discipline (new file every run, FileExistsError instead of silent
clobber) since DraftKings slate files can differ by contest/time of day
and every version matters.

    dfs_input/
      YYYY-MM-DD/
        raw/
          DKSalaries_<timestamp>.csv
        dk_player_pool_<timestamp>.json
        dk_match_report_<timestamp>.json
"""

import json
from pathlib import Path
from typing import List, Optional

from dfs.models import DFSPlayer
from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

DEFAULT_DFS_INPUT_ROOT = Path(__file__).resolve().parent.parent / "dfs_input"


def _no_overwrite(path: Path) -> None:
    # Milestone 33.2: storage-aware (see bluecollar/persistence.py's
    # identical comment for why this replaced a local path.exists() check).
    raise_if_exists(path)


def save_raw_csv(csv_path, slate_date: str, timestamp: str, output_root: Path = DEFAULT_DFS_INPUT_ROOT) -> Path:
    dest_dir = Path(output_root) / slate_date / "raw"
    dest = dest_dir / f"DKSalaries_{timestamp}.csv"
    resolve_artifact_storage(ARTIFACT_ROOT).copy_file(Path(csv_path), to_artifact_key(dest), allow_overwrite=False)
    return dest


def save_player_pool(players: List[DFSPlayer], pool_metadata: dict, slate_date: str, timestamp: str,
                      output_root: Path = DEFAULT_DFS_INPUT_ROOT) -> Path:
    path = Path(output_root) / slate_date / f"dk_player_pool_{timestamp}.json"
    _no_overwrite(path)
    doc = {**pool_metadata, "player_count": len(players), "players": [p.to_dict() for p in players]}
    save_json(path, doc)
    return path


def save_match_report(report: dict, slate_date: str, timestamp: str, output_root: Path = DEFAULT_DFS_INPUT_ROOT) -> Path:
    path = Path(output_root) / slate_date / f"dk_match_report_{timestamp}.json"
    _no_overwrite(path)
    save_json(path, report)
    return path


def list_player_pools(slate_date: str, output_root: Path = DEFAULT_DFS_INPUT_ROOT) -> List[Path]:
    """Every saved player-pool snapshot for a date, oldest first
    (filenames sort chronologically -- mirrors
    research/prediction_snapshot.py::list_snapshots)."""
    folder = Path(output_root) / slate_date
    if not folder.exists():
        return []
    return sorted(folder.glob("dk_player_pool_*.json"))


def load_latest_player_pool(
    slate_date: str, slate_id: Optional[str] = None, output_root: Path = DEFAULT_DFS_INPUT_ROOT,
) -> Optional[dict]:
    """Milestone 30.1: the most recently saved pool for this date, if
    any -- used to detect SCRATCHED players (a player who WAS
    STARTING_PITCHER/STARTING_HITTER in this snapshot but no longer is in
    the new build). Returns None (never raises) when no prior pool
    exists yet -- the normal state for a slate's first build.

    `slate_id`, when given, restricts the search to pools whose own
    `selected_slate_id` matches -- a date can have more than one slate
    (main, showdown, ...), each saved into the SAME dfs_input/<date>/
    directory (the filename doesn't encode slate_id, only the JSON body
    does), so comparing against the newest pool file regardless of which
    slate it belongs to would misattribute another slate's players as
    scratched/still-starting for this one."""
    pools = list_player_pools(slate_date, output_root)
    for path in reversed(pools):
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
        if slate_id is None or doc.get("selected_slate_id") == slate_id:
            return doc
    return None
