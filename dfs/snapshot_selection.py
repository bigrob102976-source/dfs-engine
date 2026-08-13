"""Selects which pregame prediction snapshot (Pitcher or Batter) to join
salary data against. We may have multiple snapshots for the same slate
date (e.g. a morning run and a pre-lock run), so this is never implicit
-- callers must be told exactly which file was used.
"""

from pathlib import Path
from typing import Optional, Tuple

from research.prediction_snapshot import list_snapshots, load_snapshot


def select_snapshot(
    explicit_path: Optional[str], slate_date: str, predictions_root, filename_prefix: str,
) -> Tuple[Optional[dict], Optional[str]]:
    """Returns (snapshot_dict, path_str). If `explicit_path` is given, it
    is loaded directly (no "latest" search). Otherwise the most recent
    snapshot for `slate_date` under `predictions_root` is used. Returns
    (None, None) -- not an exception -- when no snapshot exists at all,
    since a DFS pool can still be built with only one of the two agent
    types available (the other side's players just carry no projection)."""
    if explicit_path:
        return load_snapshot(Path(explicit_path)), str(explicit_path)

    snapshots = list_snapshots(slate_date, output_root=predictions_root, filename_prefix=filename_prefix)
    if not snapshots:
        return None, None
    path = snapshots[-1]
    return load_snapshot(path), str(path)
