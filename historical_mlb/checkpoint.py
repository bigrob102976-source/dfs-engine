"""Milestone 32.1, Part 5 -- resumable per-date collection checkpoints.

One checkpoint file per COMPLETED date (state/checkpoints/<date>.json).
A date is checkpointed ONLY after this milestone's explicit four-step
guarantee (Part 5):
  1. required source collection succeeds
  2. records validate (quality gates pass for that date)
  3. data writes successfully (appended into the processed Parquet)
  4. checkpoint writes successfully -- LAST, atomically

If the process dies between steps 3 and 4, the date has no checkpoint
and is simply reprocessed on the next run -- reprocessing an
already-fully-written date is idempotent (the processed-data writer
de-dupes by game_pk/player_id, see warehouse_builder.py), so this is
safe, not just "probably fine."
"""

import json
from pathlib import Path
from typing import List, Optional

from historical_mlb.cache import atomic_write_text
from historical_mlb.paths import CHECKPOINTS_DIR


def checkpoint_path(date: str) -> Path:
    return CHECKPOINTS_DIR / f"{date}.json"


def is_date_complete(date: str) -> bool:
    return checkpoint_path(date).exists()


def mark_date_complete(date: str, summary: dict) -> None:
    payload = {"date": date, **summary}
    atomic_write_text(checkpoint_path(date), json.dumps(payload, indent=2, default=str))


def read_checkpoint(date: str) -> Optional[dict]:
    path = checkpoint_path(date)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def list_completed_dates() -> List[str]:
    if not CHECKPOINTS_DIR.exists():
        return []
    return sorted(p.stem for p in CHECKPOINTS_DIR.glob("*.json"))


def last_completed_date() -> Optional[str]:
    dates = list_completed_dates()
    return dates[-1] if dates else None


def resolve_effective_start(requested_start: str, resume: bool) -> str:
    """Deliberately ALWAYS returns requested_start unchanged, for both
    --resume and a plain rerun.

    An earlier version of this function tried to "jump ahead" to the
    day after last_completed_date() -- but last_completed_date() is the
    MAX date across every checkpoint ever written, regardless of which
    requested range produced it. In practice this project's small
    integration build (Part 33, a LATER date range) gets run before the
    full historical build (an EARLIER, wider range) -- so "jump to the
    day after the max checkpoint" would silently skip the ENTIRE
    earlier range instead of resuming it. This was caught live during
    this milestone's own full-build attempt before any real damage was
    done (see this milestone's final report) and fixed by removing the
    unsafe shortcut entirely.

    The real, safe resumability guarantee lives in warehouse_builder.py's
    main loop instead: every date in [requested_start, requested_end] is
    checked individually against checkpoint.is_date_complete() and
    skipped (near-zero cost -- one file-existence check, no network
    call) if already done. That per-date check is correct regardless of
    what order previous runs processed dates in, which a single
    "resume point" can never guarantee. `resume` is kept as a CLI
    parameter (and this function keeps its signature) for interface
    stability and because a future caller may want to branch on it, but
    it deliberately no longer changes the iterated range."""
    return requested_start
