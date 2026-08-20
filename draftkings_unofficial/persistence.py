"""Immutable raw + normalized snapshot persistence for the unofficial
DraftKings provider. Mirrors research/prediction_snapshot.py's
no-overwrite pattern exactly (refuses to overwrite an existing
timestamped file -- FileExistsError semantics), applied to a wider set
of categories since this provider spans many endpoint types and sports.

Layout (see this milestone's suggested archive layout):

    data/draftkings_unofficial/
      raw/YYYY-MM-DD/{sports,contests,draftgroups,draftables,rules,events}/*.json
      normalized/YYYY-MM-DD/*.json

The entire data/draftkings_unofficial/ tree is gitignored -- see
.gitignore. This archive exists so an undocumented-API schema change
can be debugged against exactly what DraftKings returned at capture
time, and so tests/fixtures can be built from real captures without
needing DraftKings to be reachable.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

DEFAULT_ARCHIVE_ROOT = Path("data/draftkings_unofficial")

RAW_CATEGORIES = ("sports", "contests", "draftgroups", "draftables", "rules", "events")


def _timestamp_tag(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S")


def _today(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d")


def save_raw(category: str, name: str, payload: Any, archive_root: Path = DEFAULT_ARCHIVE_ROOT, date: Optional[str] = None) -> Path:
    """Saves one raw API response, immutably. `category` must be one of
    RAW_CATEGORIES; `name` is a short, filesystem-safe label (e.g. a
    sport code or draft group id) used in the filename."""
    if category not in RAW_CATEGORIES:
        raise ValueError(f"Unknown raw category {category!r}; expected one of {RAW_CATEGORIES}")
    date = date or _today()
    directory = archive_root / "raw" / date / category
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}_{_timestamp_tag()}.json"
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing raw snapshot: {path}")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return path


def save_normalized(name: str, payload: Any, archive_root: Path = DEFAULT_ARCHIVE_ROOT, date: Optional[str] = None) -> Path:
    date = date or _today()
    directory = archive_root / "normalized" / date
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}_{_timestamp_tag()}.json"
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing normalized snapshot: {path}")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return path


def list_raw_snapshots(category: str, date: str, archive_root: Path = DEFAULT_ARCHIVE_ROOT) -> List[Path]:
    directory = archive_root / "raw" / date / category
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def list_normalized_snapshots(date: str, archive_root: Path = DEFAULT_ARCHIVE_ROOT) -> List[Path]:
    directory = archive_root / "normalized" / date
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def load_latest_raw(category: str, name_prefix: str, date: str, archive_root: Path = DEFAULT_ARCHIVE_ROOT) -> Optional[Any]:
    """Reads the most recent raw snapshot for `category` whose filename
    starts with `name_prefix` -- used by tests/development to replay a
    real capture without a live call. Returns None (never raises) when
    nothing has been captured yet."""
    candidates = [p for p in list_raw_snapshots(category, date, archive_root) if p.name.startswith(name_prefix)]
    if not candidates:
        return None
    with open(candidates[-1], "r", encoding="utf-8") as f:
        return json.load(f)
