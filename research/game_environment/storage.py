"""Immutable, reproducible storage for Game Environment reports.
Mirrors research/prediction_snapshot.py's save discipline exactly:
every save writes a NEW timestamped file, nothing here ever opens an
existing snapshot file in write mode.

    game_environment_snapshots/
      YYYY-MM-DD/
        environment_<timestamp>.json
"""

import json
from pathlib import Path
from typing import List, Optional

from research.prediction_snapshot import timestamp_tag

DEFAULT_ENVIRONMENT_SNAPSHOT_ROOT = Path(__file__).resolve().parent.parent.parent / "game_environment_snapshots"


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_environment_report(document: dict, output_root: Path = DEFAULT_ENVIRONMENT_SNAPSHOT_ROOT) -> Path:
    """`document` must already contain slate_date and generated_at
    (SlateEnvironmentReport.to_dict() always does)."""
    slate_date = document["slate_date"]
    ts = timestamp_tag(document["generated_at"])
    path = Path(output_root) / slate_date / f"environment_{ts}.json"
    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing immutable snapshot: {path}. "
            f"(Two snapshots requested the same second -- this should be astronomically rare.)"
        )
    save_json(path, document)
    return path


def list_environment_reports(slate_date: str, output_root: Path = DEFAULT_ENVIRONMENT_SNAPSHOT_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date
    if not folder.exists():
        return []
    return sorted(folder.glob("environment_*.json"))


def load_latest_environment_report(slate_date: str, output_root: Path = DEFAULT_ENVIRONMENT_SNAPSHOT_ROOT) -> Optional[dict]:
    reports = list_environment_reports(slate_date, output_root)
    if not reports:
        return None
    return load_environment_report(reports[-1])


def load_environment_report(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)
