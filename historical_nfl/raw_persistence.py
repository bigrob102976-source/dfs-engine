"""NFL M6A Phase 3 -- immutable, timestamped local persistence for raw
nflverse snapshots. Mirrors nfl/game_context_persistence.py's (M5) exact
discipline: raise_if_exists() before every write, never overwrite.

    historical/nfl/raw/nflverse/
      schedules/{season}/nflverse_schedules_<timestamp>.json
      rosters/{season}/{week}/nflverse_rosters_<timestamp>.json
      weekly_player_stats/{season}/{week}/nflverse_weekly_player_stats_<timestamp>.json
      team_stats/{season}/{week}/nflverse_team_stats_<timestamp>.json
      play_by_play/{season}/{week}/nflverse_play_by_play_<timestamp>.json

schedules is season-grain (matches nflverse's own real fetch
granularity -- see nflverse_client.py). rosters is week-grain -- a real
Phase 1 finding overrides this milestone's original season-grain
assumption: nflreadpy's load_rosters_weekly() (not load_rosters()) is
the dataset that actually reconciles with weekly stats by GSIS ID, and
it is natively week-grain. weekly_player_stats/team_stats/play_by_play
are persisted per-week even though nflreadpy fetches them at season
grain, because that is the useful, bounded unit for a later per-week
model-training read (Phase 6).

NFL M6A scope: local disk only -- no production R2 writes (mirrors M5).
"""

from pathlib import Path
from typing import List, Optional

import polars as pl

from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from historical_nfl.raw_contract import NflverseRawSnapshotMetadata

DEFAULT_RAW_ROOT = Path(__file__).resolve().parent.parent / "historical" / "nfl" / "raw" / "nflverse"

_SEASON_GRAIN_DATASETS = {"schedules"}


def _snapshot_dir(dataset_name: str, season: int, week: Optional[int], output_root: Path) -> Path:
    base = Path(output_root) / dataset_name / str(season)
    if dataset_name in _SEASON_GRAIN_DATASETS:
        return base
    if week is None:
        raise ValueError(f"{dataset_name!r} snapshots must be persisted per-week (week is required).")
    return base / str(week)


def _json_safe_rows(df: pl.DataFrame) -> List[dict]:
    """Casts any Date/Datetime/Time column to its ISO-ish string form
    before serializing -- Python's json module cannot encode those types
    natively. This changes representation only (a real date becomes its
    string form, not a different value) -- no source semantics change."""
    temporal_cols = [name for name, dtype in df.schema.items() if dtype.base_type() in (pl.Date, pl.Datetime, pl.Time)]
    if temporal_cols:
        df = df.with_columns([pl.col(c).cast(pl.Utf8) for c in temporal_cols])
    return df.to_dicts()


def save_raw_snapshot(
    dataset_name: str, season: int, week: Optional[int], df: pl.DataFrame,
    metadata: NflverseRawSnapshotMetadata, timestamp: str, output_root: Path = DEFAULT_RAW_ROOT,
) -> Path:
    """`df` is persisted source-preserving (see _json_safe_rows) -- no
    feature engineering, no renamed fields."""
    directory = _snapshot_dir(dataset_name, season, week, output_root)
    path = directory / f"nflverse_{dataset_name}_{timestamp}.json"
    raise_if_exists(path)
    document = {"metadata": metadata.to_dict(), "rows": _json_safe_rows(df)}
    save_json(path, document)
    return path


def list_raw_snapshots(dataset_name: str, season: int, week: Optional[int] = None, output_root: Path = DEFAULT_RAW_ROOT) -> List[Path]:
    directory = _snapshot_dir(dataset_name, season, week, output_root)
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    keys = storage.list_files(to_artifact_key(directory), prefix=f"nflverse_{dataset_name}_", ext=".json")
    return [ARTIFACT_ROOT / key for key in keys]


def load_latest_raw_snapshot(dataset_name: str, season: int, week: Optional[int] = None, output_root: Path = DEFAULT_RAW_ROOT) -> Optional[dict]:
    snapshots = list_raw_snapshots(dataset_name, season, week, output_root)
    if not snapshots:
        return None
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    return storage.read_json(to_artifact_key(snapshots[-1]))
