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

DISK INCIDENT (2026-09-01): this archive has NO retention policy and is
called on every real collection cycle (draftkings_unofficial/collector.py's
collect_sports/collect_sport_universe/collect_slate_detail, all
save_snapshot=True by default) -- confirmed to grow to 27.31 GB / 53,356
files in 12 days on the machine running the scheduled production
worker, filling its C: drive to 0 bytes free. Root cause: this local
archive was never the durable RAW record it looks like -- it
re-serializes already-parsed dicts (not exact provider bytes -- see
canonical_ingestion/raw_capture.py's own docstring for why a genuine
byte-exact RAW record now lives in R2 instead, as of M2), lives on one
machine's local disk only, and nothing ever pruned it.

FIX: dfs/providers/draftkings_unofficial_provider.py::get_slate() --
the ONE function the scheduled production worker actually calls --
now defaults this OFF (see local_raw_archive_enabled() below), since
R2 is the real durable RAW record. Direct use of collector.py's own
functions (ad-hoc scripts, tests, scripts/audit_draftkings_unofficial.py)
is UNCHANGED -- those still default to saving, exactly as before, for
local development/debugging. prune_local_raw_archive() below is an
additional, separately-invocable safety net (never auto-run) for
whoever explicitly re-enables local archiving for extended local
debugging.
"""

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional

DEFAULT_ARCHIVE_ROOT = Path("data/draftkings_unofficial")

RAW_CATEGORIES = ("sports", "contests", "draftgroups", "draftables", "rules", "events")

# Explicit opt-in/opt-out for the LOCAL disk archive, independent of
# save_snapshot's own per-call default (which stays True at the
# collector.py layer -- see this module's own docstring). Truthy values
# ("true"/"1"/"yes", case-insensitive) enable it; explicit falsy values
# ("false"/"0"/"no") disable it; unset falls back to whatever the
# caller's own `default` says.
LOCAL_RAW_ARCHIVE_ENV_VAR = "DK_UNOFFICIAL_LOCAL_RAW_ARCHIVE_ENABLED"
_TRUTHY = {"true", "1", "yes"}
_FALSY = {"false", "0", "no"}


def local_raw_archive_enabled(default: bool) -> bool:
    """Resolves whether the local raw archive should be written to,
    honoring LOCAL_RAW_ARCHIVE_ENV_VAR as an explicit override in either
    direction; `default` applies only when the var is unset or empty."""
    value = os.environ.get(LOCAL_RAW_ARCHIVE_ENV_VAR, "").strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    return default


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


def prune_local_raw_archive(
    max_age_days: int = 3, archive_root: Path = DEFAULT_ARCHIVE_ROOT, now: Optional[datetime] = None,
) -> List[Path]:
    """Deletes date-partitioned subdirectories (both raw/YYYY-MM-DD and
    normalized/YYYY-MM-DD) older than `max_age_days`. A safety net for
    whoever explicitly re-enables local archiving for extended local
    debugging (see local_raw_archive_enabled()) -- NEVER called
    automatically by save_raw/save_normalized/collector.py; a caller
    (a dev script, a scheduled cleanup task someone sets up deliberately)
    must invoke this explicitly.

    Every directory this function would remove is verified, via
    Path.resolve() + relative_to(), to actually live inside
    `archive_root` before any deletion happens -- a date-like name that
    somehow resolves outside the archive root (e.g. through a symlink)
    is skipped, never deleted. Returns the list of directories actually
    removed."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    resolved_root = Path(archive_root).resolve()

    removed: List[Path] = []
    for section in ("raw", "normalized"):
        section_dir = Path(archive_root) / section
        if not section_dir.is_dir():
            continue
        for date_dir in sorted(section_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            # Only ever acts on genuine YYYY-MM-DD-named directories --
            # anything else under here is left alone rather than guessed at.
            try:
                datetime.strptime(date_dir.name, "%Y-%m-%d")
            except ValueError:
                continue
            if date_dir.name >= cutoff:
                continue  # within the retention window -- keep it

            resolved_date_dir = date_dir.resolve()
            try:
                resolved_date_dir.relative_to(resolved_root)
            except ValueError:
                continue  # would escape archive_root -- refuse to touch it

            shutil.rmtree(resolved_date_dir)
            removed.append(date_dir)

    return removed
