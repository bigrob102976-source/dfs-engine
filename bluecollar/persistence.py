"""Immutable, reproducible storage for one BlueCollar projection fetch.
Mirrors ownership/persistence.py's slate-scoped save discipline -- a new
timestamped file every run, FileExistsError instead of silent overwrite.

    bluecollar_projection_snapshots/
      YYYY-MM-DD/
        <dk_slate_id>/
          bluecollar_projection_<timestamp>.json

Always slate-scoped (unlike FantasyPros, which is date-only) --
BlueCollar's own data is genuinely per-slate (Main/Turbo/Afternoon each
have a different player pool), so a snapshot must never be ambiguous
about which DK slate it was matched against.

Never persists the API key -- the snapshot document
(bluecollar/models.py::BlueCollarSnapshot) has no field for it at all.
"""

import json
from pathlib import Path
from typing import List, Optional

from research.storage import save_json

DEFAULT_BLUECOLLAR_ROOT = Path(__file__).resolve().parent.parent / "bluecollar_projection_snapshots"


def _no_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing BlueCollar snapshot: {path}")


def _slate_folder(output_root: Path, slate_date: str, dk_slate_id: str) -> Path:
    return Path(output_root) / slate_date / dk_slate_id


def save_bluecollar_snapshot(document: dict, slate_date: str, dk_slate_id: str, timestamp: str, output_root: Path = DEFAULT_BLUECOLLAR_ROOT) -> Path:
    path = _slate_folder(output_root, slate_date, dk_slate_id) / f"bluecollar_projection_{timestamp}.json"
    _no_overwrite(path)
    save_json(path, document)
    return path


def list_bluecollar_snapshots(slate_date: str, dk_slate_id: str, output_root: Path = DEFAULT_BLUECOLLAR_ROOT) -> List[Path]:
    folder = _slate_folder(output_root, slate_date, dk_slate_id)
    if not folder.exists():
        return []
    return sorted(folder.glob("bluecollar_projection_*.json"))


def load_latest_bluecollar_snapshot(slate_date: str, dk_slate_id: str, output_root: Path = DEFAULT_BLUECOLLAR_ROOT) -> Optional[dict]:
    snapshots = list_bluecollar_snapshots(slate_date, dk_slate_id, output_root)
    if not snapshots:
        return None
    with snapshots[-1].open("r", encoding="utf-8") as f:
        return json.load(f)
