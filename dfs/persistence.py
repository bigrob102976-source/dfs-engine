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

import shutil
from pathlib import Path
from typing import List

from dfs.models import DFSPlayer
from research.storage import save_json

DEFAULT_DFS_INPUT_ROOT = Path(__file__).resolve().parent.parent / "dfs_input"


def _no_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing DFS import artifact: {path}")


def save_raw_csv(csv_path, slate_date: str, timestamp: str, output_root: Path = DEFAULT_DFS_INPUT_ROOT) -> Path:
    dest_dir = Path(output_root) / slate_date / "raw"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"DKSalaries_{timestamp}.csv"
    _no_overwrite(dest)
    shutil.copyfile(Path(csv_path), dest)
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
