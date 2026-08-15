"""Immutable, reproducible storage for AI Projection Engine snapshots,
plus thin loader wrappers around every upstream snapshot this engine
reads. Mirrors research/prediction_snapshot.py's save discipline: every
save writes a NEW timestamped file, nothing here ever opens an existing
snapshot file in write mode.

    ai_projection_snapshots/
      YYYY-MM-DD/
        ai_projection_<timestamp>.json
"""

import json
from pathlib import Path
from typing import List, Optional

from external_projections.persistence import load_latest_adjusted_snapshot
from ownership.persistence import load_latest_ownership_snapshot
from research.game_environment.storage import load_latest_environment_report
from research.prediction_snapshot import load_latest_snapshot as _load_latest_research_snapshot
from research.prediction_snapshot import timestamp_tag
from research.storage import save_json

DEFAULT_AI_PROJECTION_ROOT = Path(__file__).resolve().parent.parent / "ai_projection_snapshots"
DEFAULT_DFS_INPUT_ROOT = Path(__file__).resolve().parent.parent / "dfs_input"


def _no_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing immutable snapshot: {path}. "
            f"(Two snapshots requested the same second -- this should be astronomically rare.)"
        )


# ----------------------------------------------------------------------------
# Upstream loaders -- thin wrappers so scoring.py/scripts don't need to
# know five different modules' import paths. The two REQUIRED sources
# (pitcher/batter boards, the Independent Projection baseline) raise
# FileNotFoundError when missing, since an AI Projection with no
# baseline to start from is not a partial result -- it's nothing. Every
# OPTIONAL source (environment/ownership/adjusted/pool) returns None
# rather than raising, since the engine must degrade gracefully -- a
# missing signal source just means fewer signals fire.
# ----------------------------------------------------------------------------


def load_latest_pitcher_snapshot(slate_date: str) -> dict:
    return _load_latest_research_snapshot(slate_date, filename_prefix="pitcher_board")


def load_latest_batter_snapshot(slate_date: str) -> dict:
    return _load_latest_research_snapshot(slate_date, filename_prefix="batter_board")


def load_latest_environment(slate_date: str) -> Optional[dict]:
    return load_latest_environment_report(slate_date)


def load_latest_ownership(slate_date: str) -> Optional[dict]:
    try:
        return load_latest_ownership_snapshot(slate_date)
    except FileNotFoundError:
        return None


def load_latest_adjusted(slate_date: str) -> Optional[dict]:
    return load_latest_adjusted_snapshot(slate_date)


def load_latest_dfs_pool(slate_date: str, output_root: Path = DEFAULT_DFS_INPUT_ROOT) -> Optional[dict]:
    """Salary/mlb_player_id lookup only -- board snapshots don't carry
    salary. Mirrors dfs_input/<date>/dk_player_pool_<timestamp>.json's
    own naming convention (dfs/persistence.py) without importing dfs/
    (would pull in DK ingestion internals the AI engine has no business
    depending on for a simple salary lookup)."""
    folder = Path(output_root) / slate_date
    if not folder.exists():
        return None
    files = sorted(folder.glob("dk_player_pool_*.json"))
    if not files:
        return None
    with files[-1].open("r", encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------------
# AI Projection snapshot save/load
# ----------------------------------------------------------------------------


def save_ai_projection_snapshot(document: dict, output_root: Path = DEFAULT_AI_PROJECTION_ROOT) -> Path:
    """`document` must already contain slate_date and generated_at."""
    slate_date = document["slate_date"]
    ts = timestamp_tag(document["generated_at"])
    path = Path(output_root) / slate_date / f"ai_projection_{ts}.json"
    _no_overwrite(path)
    save_json(path, document)
    return path


def list_ai_projection_snapshots(slate_date: str, output_root: Path = DEFAULT_AI_PROJECTION_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date
    if not folder.exists():
        return []
    return sorted(folder.glob("ai_projection_*.json"))


def load_latest_ai_projection_snapshot(slate_date: str, output_root: Path = DEFAULT_AI_PROJECTION_ROOT) -> Optional[dict]:
    snapshots = list_ai_projection_snapshots(slate_date, output_root)
    if not snapshots:
        return None
    with snapshots[-1].open("r", encoding="utf-8") as f:
        return json.load(f)
