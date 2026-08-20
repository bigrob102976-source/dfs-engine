"""Immutable, reproducible storage for FantasyPros projection snapshots --
mirrors research/prediction_snapshot.py's exact save discipline (new
timestamped file every run, FileExistsError instead of silent clobber)
and external_projections/persistence.py's directory-per-date layout.

    fantasypros_snapshots/
      YYYY-MM-DD/
        fantasypros_projection_<timestamp>.json

Never contains the API key or any request header -- see
fantasypros/client.py's module docstring.
"""

import json
from pathlib import Path
from typing import List, Optional

from fantasypros.models import FantasyProsSnapshot
from research.storage import save_json

DEFAULT_SNAPSHOT_ROOT = Path(__file__).resolve().parent.parent / "fantasypros_snapshots"


def timestamp_tag(iso_timestamp: str) -> str:
    from datetime import datetime

    dt = datetime.fromisoformat(iso_timestamp)
    return dt.strftime("%Y%m%dT%H%M%S")


def save_snapshot(snapshot: FantasyProsSnapshot, output_root: Path = DEFAULT_SNAPSHOT_ROOT) -> Path:
    ts = timestamp_tag(snapshot.retrieved_at)
    path = Path(output_root) / snapshot.slate_date / f"fantasypros_projection_{ts}.json"
    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing immutable snapshot: {path}. "
            f"(Two snapshots requested the same second -- this should be astronomically rare.)"
        )
    save_json(path, snapshot.to_dict())
    return path


def list_snapshots(slate_date: str, output_root: Path = DEFAULT_SNAPSHOT_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date
    if not folder.exists():
        return []
    return sorted(folder.glob("fantasypros_projection_*.json"))


def load_latest_snapshot(slate_date: str, output_root: Path = DEFAULT_SNAPSHOT_ROOT) -> Optional[dict]:
    snapshots = list_snapshots(slate_date, output_root)
    if not snapshots:
        return None
    with snapshots[-1].open("r", encoding="utf-8") as f:
        return json.load(f)
